# -*- coding: utf-8 -*-
"""Фоновий моніторинг: опитування інвертора, визначення подій, статистика, Telegram."""
import datetime as dt
import logging
import random
import threading
import time
import urllib.error

from PySide6.QtCore import QObject, Signal

from . import messages as M
from .core import SolarmanV5, Telegram, discover

log = logging.getLogger("deyewatch")


class Monitor(QObject):
    data = Signal(dict)          # нові дані інвертора
    note = Signal(object)        # Note для спливаючого вікна
    status = Signal(str, str)    # (стан: ok|outage|offline|unknown, текст)
    cloud = Signal(bool, str)    # результат синхронізації з Deye Cloud
    syncing = Signal(bool)       # синхронізація з хмарою почалась / закінчилась

    def __init__(self, cfg, store):
        super().__init__()
        self.cfg, self.store = cfg, store
        self.last = None
        self.fail = 0
        self.offline = False
        self.pending_ts, self.pending_n = None, 0
        o = store.open_outage()
        self.grid_ok = None if store.get("grid_known") is None else (o is None)
        self.since = o[1] if o else (store.last_outage_end() or float(store.get("since", time.time())))
        self.soc_warned = set()
        self.v_bad_since, self.v_alerted = None, False
        self.minute = None
        self.acc = []
        self.wake = threading.Event()
        self.stop_ev = threading.Event()
        self.lock = threading.Lock()
        self.fresh = True             # перше опитування після запуску
        self.cloud_now = threading.Event()
        self.cloud_lock = threading.Lock()
        self.gen_on = store.get("gen_on") == "1"
        self.gen_since = float(store.get("gen_since", 0) or 0)
        self.gen_pending = 0
        self.first_poll = threading.Event()
        self.sync_pending = False
        self.sync_reason = "запуск"

    # ---------------------------------------------------------------- запуск
    def start(self):
        for fn in (self._poll_loop, self._send_loop, self._updates_loop, self._daily_loop, self._cloud_loop):
            threading.Thread(target=fn, daemon=True).start()

    # ---------------------------------------------------------------- хмара
    def request_sync(self, reason=""):
        """Позачергова синхронізація з хмарою (запуск, пробудження, повернення зв'язку…)."""
        self.sync_reason = reason
        self.cloud_now.set()

    def sync_age(self):
        try:
            return time.time() - float(self.store.get("cloud_last", 0))
        except (TypeError, ValueError):
            return 1e9

    def _cloud_loop(self):
        # одразу після запуску: чекаємо лише перше опитування інвертора (до 15 с),
        # щоб поточний стан і хмара не перебудовували відключення одночасно
        self.first_poll.wait(15)
        fails = 0
        while not self.stop_ev.is_set():
            self.cloud_now.clear()
            ok = True
            if self.cfg["cloud_enabled"]:
                ok = self.cloud_sync()
            fails = 0 if ok else fails + 1
            if ok and self.sync_pending:
                # свіжий пропуск ще не дійшов у хмару — повторюємо через 10 хв, а не через 30
                self.cloud_now.wait(600)
                continue
            # після збою (напр. Wi-Fi ще не піднявся після сну) — 1, 2, 4… хв, не більше 5; інакше раз на 30 хв
            self.cloud_now.wait(1800 if ok else min(300, 60 * 2 ** (fails - 1)))

    def cloud_sync(self):
        from .cloud import CloudError, DeyeCloud, sync
        if not self.cloud_lock.acquire(blocking=False):
            return True
        self.syncing.emit(True)
        try:
            rep = sync(DeyeCloud(self.cfg, self.store), self.cfg, self.store)
            self.sync_pending = rep.get("pending", False)
            o = self.store.open_outage()
            live_ok = self.last is not None and self.last["grid_voltage"] >= self.cfg["grid_min_voltage"]
            if o and live_ok:
                # хмара бачила відключення до своєї останньої точки, а інвертор уже показує світло
                self.store.end_outage(time.time())
            elif o:
                # за даними хмари відключення триває — стан і його початок беремо звідти
                self.grid_ok, self.since = False, o[1]
                self.pending_ts = None
            elif self.grid_ok:
                self.since = max(self.store.last_outage_end() or 0, min(self.since, time.time())) or self.since
            self.store.put("cloud_last", time.time())
            self.store.put("cloud_last_msg", "")
            self.cloud.emit(True, "Синхронізовано: %d точок з хмари, днів енергії %d" % (rep["samples"], rep["days"]))
            return True
        except CloudError as e:
            self.store.put("cloud_last_msg", str(e))
            self.cloud.emit(False, str(e))
        except Exception as e:
            log.warning("Deye Cloud: %s", e)
            self.store.put("cloud_last_msg", str(e))
            self.cloud.emit(False, "немає зв'язку з хмарою: %s" % e)
        finally:
            self.cloud_lock.release()
            self.syncing.emit(False)
        return False

    def poke(self):
        """Негайне опитування (після зміни налаштувань)."""
        self.wake.set()

    # ---------------------------------------------------------------- опитування
    def _poll_loop(self):
        prev = time.time()
        while not self.stop_ev.is_set():
            c = self.cfg
            now = time.time()
            # годинник стрибнув (сон / глибокий сон / зміна часу) — дані за проміжок беремо з хмари
            if abs(now - prev) > max(3, c["poll_interval_sec"]) + 90:
                self.fresh = True
                self.request_sync("пробудження")
            prev = now
            d = None
            try:
                if not self._configured():
                    raise OSError("стік ще не налаштовано")
                inv = SolarmanV5(c["logger_ip"], c["logger_serial"], c["logger_port"])
                try:
                    d = inv.read_all()
                except OSError:
                    time.sleep(1 + random.random())   # стік міг бути зайнятий іншим клієнтом
                    d = inv.read_all()
            except Exception as e:
                try:
                    self._on_fail(str(e) or e.__class__.__name__)
                except Exception:
                    log.exception("обробка збою зв'язку")
            if d is not None:
                # помилка в обробці (база, сповіщення) — не привід казати «немає зв'язку з інвертором»
                try:
                    self._on_data(d)
                except Exception:
                    log.exception("обробка даних інвертора")
            self.first_poll.set()
            prev = time.time()
            self.wake.wait(max(3, c["poll_interval_sec"]))
            self.wake.clear()

    def _configured(self):
        return bool(self.cfg["logger_ip"]) and bool(int(self.cfg["logger_serial"] or 0))

    def _first_setup(self):
        """Перший запуск: стік ще не вказано — шукаємо його в мережі й беремо перший знайдений."""
        try:
            for f in discover():
                if f["serial"]:
                    self.cfg["logger_ip"], self.cfg["logger_serial"] = f["ip"], f["serial"]
                    self.cfg.save()
                    self.store.add_event("ip_change", 0, f["ip"])
                    self.wake.set()
                    return True
        except Exception:
            pass
        return False

    def _on_fail(self, err):
        self.fail += 1
        if not self._configured():
            if self.fail % 6 == 1 and self._first_setup():
                return
            self.status.emit("unknown", "Шукаю WiFi-стік інвертора в мережі…")
            return
        if self.fail % 6 == 3:   # стік міг отримати нову IP-адресу — шукаємо за серійним номером
            try:
                for f in discover():
                    if f["serial"] == int(self.cfg["logger_serial"]) and f["ip"] != self.cfg["logger_ip"]:
                        self.cfg["logger_ip"] = f["ip"]
                        self.cfg.save()
                        self.store.add_event("ip_change", 0, f["ip"])
                        self.wake.set()
                        break
            except Exception:
                pass
        if self.fail >= self.cfg["offline_alert_polls"] and not self.offline:
            self.offline = True
            self.store.add_event("offline", 0, err)
            self.status.emit("offline", "Немає зв'язку з інвертором")
            if self.cfg["notify_offline"]:
                self.dispatch(M.note_offline(self.cfg["name"], err))
        elif not self.offline and self.last is None:
            self.status.emit("unknown", "Підключення… (%s)" % err)

    def _on_data(self, d):
        now = d["ts"]
        c = self.cfg
        self.last, self.fail = d, 0
        if self.offline:
            self.offline = False
            self.store.add_event("online", 0, "")
            self.request_sync("зв'язок відновлено")
            if c["notify_offline"]:
                self.dispatch(M.note_online(c["name"]))

        ok = d["grid_voltage"] >= c["grid_min_voltage"]
        if self.fresh and self.grid_ok is not None and ok != self.grid_ok:
            # стан змінився, поки програма була закрита: точного часу не знаємо —
            # світло повернулося → закриваємо відключення останнім відомим моментом (хмара уточнить)
            last = self.store.q("SELECT max(ts) FROM samples")[0][0] or now
            if ok:
                self.store.end_outage(max(last, self.since))
                self.grid_ok, self.since = True, now
                self.store.put("since", now)
                self.pending_ts = None
            else:
                # світло зникло, поки програма не працювала: відключення почалося не раніше
                # останніх відомих даних — від них і рахуємо (хмара уточнить), а не від моменту запуску
                start = min(now, max(last + 60, self.since))
                self.store.start_outage(start)
                self.grid_ok, self.since = False, start
                self.store.put("since", start)
                self.pending_ts = None
                self.soc_warned = set()
        self.fresh = False
        if self.grid_ok is None:
            self.grid_ok = ok
            self.store.put("grid_known", 1)
            if not ok:
                self.store.start_outage(now)
                self.since = now
        elif ok != self.grid_ok:
            if self.pending_ts is None:
                self.pending_ts, self.pending_n = now, 0
            self.pending_n += 1
            if self.pending_n >= c["confirm_polls"]:
                self._grid_change(ok, self.pending_ts, d)
                self.pending_ts = None
        else:
            self.pending_ts = None

        if not self.grid_ok:
            self._check_soc(d)
        else:
            self._check_voltage(d)
        self._check_gen(d)

        d["grid_ok"] = self.grid_ok
        d["since"] = self.since
        d["autonomy_h"] = self.autonomy_hours(d)
        d["gen_on"], d["gen_since"] = self.gen_on, self.gen_since
        if c["stats_enabled"]:
            try:
                self._record(d)
            except Exception:       # напр., диск заповнений — сповіщення мають працювати й далі
                log.exception("запис історії")
        self.data.emit(d)
        self.status.emit("ok" if self.grid_ok else "outage",
                         ("Світло є" if self.grid_ok else "Світла немає") + " · " + M.fmt_dur(now - self.since)
                         + (" · працює генератор" if self.gen_on else ""))

    def _grid_change(self, ok, ts, d):
        c = self.cfg
        prev = self.since
        self.grid_ok, self.since = ok, ts
        self.store.put("since", ts)
        if not ok:
            self.store.start_outage(ts)
            self.soc_warned = set()
            if c["notify_outage"]:
                self.dispatch(M.note_outage(c["name"], ts, ts - prev, d, self.autonomy_hours(d)))
        else:
            dur = self.store.end_outage(ts)
            self.v_bad_since, self.v_alerted = None, False
            if c["notify_restore"]:
                self.dispatch(M.note_restore(c["name"], ts, dur if dur is not None else ts - prev, d))

    def _check_gen(self, d):
        """Генератор на порту GEN: запуск / зупинка з підтвердженням (як і для мережі)."""
        c = self.cfg
        w = d.get("gen_power") or 0
        on = w >= c["gen_min_power"]
        if on and not c["has_gen"]:          # інвертор уперше показав генератор — вмикаємо його підтримку
            c["has_gen"] = True
            c.save()
        if on == self.gen_on:
            self.gen_pending = 0
            return
        self.gen_pending += 1
        if self.gen_pending < c["confirm_polls"]:
            return
        self.gen_pending = 0
        ts = d["ts"]
        self.gen_on = on
        self.store.put("gen_on", "1" if on else "0")
        if on:
            self.gen_since = ts
            self.store.put("gen_since", ts)
            self.store.add_event("gen_on", w, "")
            if c["notify_gen"]:
                self.dispatch(M.note_gen_start(c["name"], ts, d, None if self.grid_ok else ts - self.since))
        else:
            run = ts - self.gen_since if self.gen_since else 0
            kwh = self.store.gen_stats(self.gen_since, c["gen_min_power"])[1] if self.gen_since else 0
            self.store.add_event("gen_off", run, "")
            if c["notify_gen"]:
                self.dispatch(M.note_gen_stop(c["name"], ts, run, kwh, d))

    def _check_soc(self, d):
        soc = d["batt_soc"]
        crossed = [t for t in self.cfg["low_soc_thresholds"] if soc <= t and t not in self.soc_warned]
        if crossed:
            self.soc_warned.update(crossed)
            if self.cfg["notify_low_soc"]:
                self.dispatch(M.note_low_soc(self.cfg["name"], soc, min(crossed), d["ts"] - self.since,
                                             d, self.autonomy_hours(d)))

    def _check_voltage(self, d):
        c = self.cfg
        v = d["grid_voltage"]
        bad = v < c["v_low"] or v > c["v_high"]
        if not bad:
            self.v_bad_since, self.v_alerted = None, False
            return
        if self.v_bad_since is None:
            self.v_bad_since = d["ts"]
        if not self.v_alerted and d["ts"] - self.v_bad_since >= c["v_alert_minutes"] * 60:
            self.v_alerted = True
            kind = "high" if v > c["v_high"] else "low"
            self.store.add_event("v_" + kind, v, "")
            if c["notify_voltage"]:
                self.dispatch(M.note_voltage(c["name"], kind, v, c["v_low"], c["v_high"]))

    def autonomy_hours(self, d):
        """Скільки годин протримається батарея до мінімального заряду при поточному розряді."""
        cap = float(self.cfg["battery_kwh"] or 0)
        if cap <= 0:
            return None
        if d["batt_power"] < -20:      # батарея зараз заряджається (сонце / генератор) — прогноз не має сенсу
            return None
        usable = (d["batt_soc"] - self.cfg["battery_min_soc"]) / 100 * cap * 1000
        if usable <= 0:
            return 0
        w = self.store.recent_discharge_w(10) or 0
        w = max(w, d["batt_power"] if d["batt_power"] > 0 else 0)
        if w < 30:
            w = d["load_power"] - d["pv_power"]
        if w < 30:
            return None
        return usable / w

    # ---------------------------------------------------------------- статистика
    def _record(self, d):
        m = int(d["ts"] // 60) * 60
        if self.minute is not None and m != self.minute and self.acc:
            a = self.acc
            vs = [x["grid_voltage"] for x in a]
            self.store.add_sample({
                "ts": self.minute, "grid_ok": int(all(x["grid_ok"] for x in a)),
                "v_avg": sum(vs) / len(vs), "v_min": min(vs), "v_max": max(vs),
                "freq": sum(x["grid_freq"] for x in a) / len(a),
                "grid_p": round(sum(x["grid_power"] for x in a) / len(a)),
                "load_p": round(sum(x["load_power"] for x in a) / len(a)),
                "pv_p": round(sum(x["pv_power"] for x in a) / len(a)),
                "batt_p": round(sum(x["batt_power"] for x in a) / len(a)),
                "gen_p": round(sum(x.get("gen_power") or 0 for x in a) / len(a)),
                "soc": a[-1]["batt_soc"], "batt_v": a[-1]["batt_voltage"],
                "batt_t": a[-1]["batt_temp"], "dc_t": a[-1]["dc_temp"]})
            self.store.update_daily(a[-1])
            self.acc = []
        self.minute = m
        self.acc.append(d)

    def _daily_loop(self):
        while not self.stop_ev.is_set():
            try:
                self.store.purge(self.cfg["keep_days"])
                if self.cfg["notify_daily_summary"]:
                    now = dt.datetime.now()
                    key = now.date().isoformat()
                    if now.hour >= 21 and self.store.get("summary_day") != key:
                        self.store.put("summary_day", key)
                        self.dispatch(self.summary_note())
            except Exception:
                log.exception("щоденні задачі")
            time.sleep(300)

    def summary_note(self):
        st = self.store.outage_stats(1)
        day = self.store.daily(1)[-1][1]
        rows = [("🕯", "Відключень", "%d · %s без світла" % (st["count"], M.fmt_dur(st["total"])))]
        if self.cfg["has_pv"]:
            rows.append(("☀️", "СЕС виробила", "%.1f кВт·год" % day[0]))
        rows += [("🏠", "Спожито", "%.1f кВт·год" % day[1]),
                 ("🔌", "З мережі", "%.1f кВт·год" % day[2])]
        if self.cfg["has_gen"]:
            midnight = time.mktime(dt.date.today().timetuple())
            h, kwh = self.store.gen_stats(midnight, self.cfg["gen_min_power"])
            if h:
                rows.append(("⚙️", "Генератор", "%s · %.1f кВт·год" % (M.fmt_dur(h * 3600), kwh)))
        return M.Note("summary", "Підсумок дня", "%s · %s" % (self.cfg["name"], M.fmt_date(time.time())),
                      rows, self.last["batt_soc"] if self.last else None, "📊")

    # ---------------------------------------------------------------- доставка
    def dispatch(self, note):
        if self.cfg["desktop_notify"]:
            self.note.emit(note)
        if self.cfg["telegram_enabled"] and self.cfg["telegram_token"]:
            for cid in self.cfg.chat_ids():
                self.store.outbox_add(cid, note.telegram_html())
            self.store.add_event("tg", 0, note.title)

    def _send_loop(self):
        while not self.stop_ev.is_set():
            item = self.store.outbox_first()
            if not item or not self.cfg["telegram_token"]:
                time.sleep(3)
                continue
            try:
                Telegram(self.cfg["telegram_token"]).send(item[1], item[2])
                self.store.outbox_del(item[0])
            except urllib.error.HTTPError as e:
                if 400 <= e.code < 500 and e.code != 429:
                    self.store.outbox_del(item[0])
                else:
                    time.sleep(20)
            except Exception as e:
                log.warning("Telegram: %s", e)
                time.sleep(20)   # немає інтернету — повторимо пізніше

    def _updates_loop(self):
        offset = int(self.store.get("tg_offset", 0))
        while not self.stop_ev.is_set():
            c = self.cfg
            # команди працюють і до ввімкнення розсилки — щоб нові отримувачі могли дізнатися свій chat_id
            if not (c["telegram_commands"] and c["telegram_token"]):
                time.sleep(5)
                continue
            try:
                tg = Telegram(c["telegram_token"])
                ups = tg.call("getUpdates", {"offset": offset, "timeout": 25,
                                             "allowed_updates": ["message"]}, timeout=35)
                for u in ups:
                    offset = u["update_id"] + 1
                    self.store.put("tg_offset", offset)
                    msg = u.get("message") or {}
                    text = (msg.get("text") or "").strip()
                    cid = str(msg.get("chat", {}).get("id", ""))
                    if not text.startswith("/") or not cid:
                        continue
                    cmd = text.split()[0].split("@")[0].lower()
                    if cid not in c.chat_ids():
                        tg.send(cid, "🔒 Доступ не надано.\nВаш chat_id: <code>%s</code>" % cid)
                    elif cmd in ("/status", "/s"):
                        tg.send(cid, self.status_html())
                    elif cmd in ("/stats", "/history"):
                        tg.send(cid, self.stats_html())
                    else:
                        tg.send(cid, "⚡ <b>DeyeWatch</b>\n\n/status — стан зараз\n/stats — статистика відключень")
            except Exception:
                time.sleep(15)

    def status_html(self):
        d = self.last
        if not d:
            return "📡 Даних з інвертора ще немає."
        ok = self.grid_ok
        n = M.Note("status", "Світло є" if ok else "Світла немає",
                   "%s · %s %s" % (self.cfg["name"], "уже" if ok else "вже", M.fmt_dur(time.time() - self.since)),
                   [("⚡", "Мережа", "%.0f В · %.2f Гц" % (d["grid_voltage"], d["grid_freq"])),
                    ("🏠", "Споживання", M.fmt_power(d["load_power"]))]
                   + ([("☀️", "СЕС", M.fmt_power(d["pv_power"]))] if self.cfg["has_pv"] else [])
                   + [("🔋", "Батарея", "%s %s" % (M.fmt_power(abs(d["batt_power"])),
                                                  "розряд" if d["batt_power"] > 0 else "заряд" if d["batt_power"] < 0 else ""))]
                   + ([("⚙️", "Генератор", "%s · працює %s" % (M.fmt_power(d.get("gen_power")),
                                                              M.fmt_dur(time.time() - self.gen_since)))]
                      if self.gen_on else [])
                   + ([("⏳", "Вистачить", M.autonomy_text(d.get("autonomy_h")))] if not ok and d.get("autonomy_h") else []),
                   d["batt_soc"], "🟢" if ok else "🔴")
        return n.telegram_html()

    def stats_html(self):
        rows = []
        for days, label in ((1, "Доба"), (7, "Тиждень"), (30, "Місяць")):
            s = self.store.outage_stats(days)
            rows.append(("📅", label, "%d відкл. · %s" % (s["count"], M.fmt_dur(s["total"]))))
        rec = self.store.recent_outages(5)
        n = M.Note("summary", "Статистика відключень", self.cfg["name"], rows, None, "📊")
        txt = n.telegram_html()
        if rec:
            txt += "\n\n<b>Останні:</b>"
            for s, e in rec:
                txt += "\n• %s %s → %s  <i>%s</i>" % (M.fmt_date(s), M.fmt_clock(s),
                                                      M.fmt_clock(e) if e else "зараз",
                                                      M.fmt_dur((e or time.time()) - s))
        return txt
