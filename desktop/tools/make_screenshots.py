# -*- coding: utf-8 -*-
"""Скріншоти DeyeWatch для документації та сайту — на вигаданих (демонстраційних) даних.

Створює тимчасову теку налаштувань із синтетичною історією за 35 днів (відключення за графіком,
сонячна генерація, генератор, батарея), запускає програму без опитування інвертора і зберігає
знімки всіх розділів у світлій і темній темі.

    python tools/make_screenshots.py [тека_для_знімків]      # типово: ../docs/assets/screenshots

Жодних реальних даних (IP, серійних номерів, історії) у знімках немає.
"""
import datetime as dt
import json
import math
import os
import random
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(APP_DIR, "..", "docs", "assets", "screenshots"))
HOME = tempfile.mkdtemp(prefix="deyewatch-demo-")
os.environ["DEYEWATCH_HOME"] = HOME
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform.startswith("win"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
os.environ.setdefault("QT_SCALE_FACTOR", "2")      # чіткі знімки для екранів високої щільності
sys.path.insert(0, APP_DIR)

DEMO_CFG = {
    "name": "Дім", "logger_ip": "192.168.1.50", "logger_serial": 1234567890,
    "battery_kwh": 10.0, "battery_min_soc": 15, "has_pv": True, "has_gen": True,
    "cloud_enabled": False, "telegram_enabled": False, "onboarding_done": True, "_battery_checked": True,
    "autostart": True, "_tray_hint_shown": True, "theme": "light",
}


# --------------------------------------------------------------------------- синтетична історія
def outage_plan(day_index):
    """Графік відключень: 2–3 блоки на добу, зсуваються день у день (як черги в Україні)."""
    rnd = random.Random(day_index * 7919)
    shift = (day_index * 4) % 12
    blocks = []
    for base in (1, 9, 17):
        if rnd.random() < 0.82:
            start = (base + shift % 8 + rnd.choice((0, 0.5, 1))) % 24
            blocks.append((start, rnd.choice((2, 2.5, 3, 3.5, 4))))
    return blocks


def build_history(store, days=35):
    rnd = random.Random(42)
    now = time.time()
    t0 = int((now - days * 86400) // 60 * 60)
    soc, rows, outages, cur_out = 70.0, [], [], None
    gen_runs = set()
    day_cloud = {}
    for minute_ts in range(t0, int(now // 60 * 60), 60):
        lt = time.localtime(minute_ts)
        di = (minute_ts - t0) // 86400
        h = lt.tm_hour + lt.tm_min / 60
        off = any(((h - s) % 24) < d for s, d in outage_plan(di))
        if off and cur_out is None:
            cur_out = minute_ts
            if rnd.random() < 0.3:
                gen_runs.add(cur_out)
        if not off and cur_out is not None:
            outages.append((cur_out, minute_ts))
            cur_out = None
        cl = day_cloud.setdefault(di, rnd.uniform(0.25, 1.0))
        pv = max(0.0, math.sin(math.pi * (h - 7.6) / 9.0)) * 3600 * cl * rnd.uniform(.85, 1.0) if 7.6 < h < 16.6 else 0
        load = 330 + (650 if 18 <= h < 22.5 else 180 if 7 <= h < 9 else 0) + rnd.gauss(0, 35)
        if rnd.random() < 0.012:
            load += rnd.choice((1800, 2100, 1200))
        gen = 0
        if cur_out in gen_runs and (minute_ts - cur_out) < 100 * 60 and (minute_ts - cur_out) > 20 * 60:
            gen = 2200 + rnd.gauss(0, 40)
        if off:
            net = load - pv - gen                       # + розряд батареї
            batt = max(-2500, net) if soc > 15 or net < 0 else 0
            grid, v, f = 0, None, None
        else:
            want = 2500 if soc < 100 else 0
            charge = min(want, max(0, pv - load) + (1800 if soc < 95 else 300))
            batt = -charge if soc < 100 else 0
            grid = round(load - pv + charge)
            v = 227 + 4 * math.sin(minute_ts / 5400) - (12 if 18.5 <= h < 21.5 else 0) + rnd.gauss(0, 1.6)
            f = 50 + rnd.gauss(0, .02)
        soc = max(15, min(100, soc - batt / 60 / 10000 * 100))
        rows.append({
            "ts": minute_ts, "grid_ok": 0 if off else 1,
            "v_avg": v, "v_min": None if v is None else v - abs(rnd.gauss(0, 1.5)),
            "v_max": None if v is None else v + abs(rnd.gauss(0, 1.5)), "freq": f,
            "grid_p": grid, "load_p": round(load), "pv_p": round(pv), "batt_p": round(batt), "soc": round(soc),
            "batt_v": 49 + soc / 100 * 4.5, "batt_t": 21.5, "dc_t": 40, "gen_p": round(gen)})
    cols = ["ts", "grid_ok", "v_avg", "v_min", "v_max", "freq", "grid_p", "load_p", "pv_p", "batt_p", "soc",
            "batt_v", "batt_t", "dc_t", "gen_p"]
    with store.lock:            # одним пакетом: 50 тис. окремих комітів — це хвилини
        store.db.executemany("INSERT OR REPLACE INTO samples(%s) VALUES(%s)" % (",".join(cols), ",".join("?" * len(cols))),
                             [tuple(r[c] for c in cols) for r in rows])
        store.db.commit()
    for s, e in outages:
        store.x("INSERT INTO outages(start,end) VALUES(?,?)", (s, e))
    if cur_out is not None:
        store.x("INSERT INTO outages(start,end) VALUES(?,NULL)", (cur_out,))
    # підсумки по днях
    byday = {}
    for r in rows:
        d = dt.date.fromtimestamp(r["ts"]).isoformat()
        a = byday.setdefault(d, [0, 0, 0, 0, 0, 0])
        a[0] += r["pv_p"] / 60000
        a[1] += r["load_p"] / 60000
        a[2] += max(0, r["grid_p"]) / 60000
        a[4] += max(0, -r["batt_p"]) / 60000
        a[5] += max(0, r["batt_p"]) / 60000
    for d, a in byday.items():
        store.x("INSERT OR REPLACE INTO daily VALUES(?,?,?,?,?,?,?)", (d, *[round(x, 2) for x in a]))
    for k in range(4):
        ts = now - rnd.uniform(1, 20) * 86400
        store.add_event("v_low", rnd.choice((201, 203, 205)), "", ts)
    store.add_event("v_high", 256, "", now - 3.3 * 86400)
    store.put("grid_known", 1)
    return rows[-1], cur_out


# --------------------------------------------------------------------------- знімки
def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(HOME, "settings.json"), "w", encoding="utf-8") as f:
        json.dump(DEMO_CFG, f, ensure_ascii=False)
    from dw.monitor import Monitor
    Monitor.start = lambda self: None              # без опитування справжнього інвертора та хмари
    from dw.store import Store
    store = Store(os.path.join(HOME, "history.sqlite3"))
    last, cur_out = build_history(store)
    store.db.close()

    from PySide6.QtCore import QTimer
    from dw import app as A
    from dw import messages as M
    a = A.App(["deyewatch"])
    a.win.resize(1280, 800)
    a.win.show()
    a.win.pages["settings"].path_lbl.setText("DeyeWatch · налаштування та історія: %APPDATA%\\DeyeWatch")
    m = a.monitor
    now = time.time()

    def live(outage):
        d = {"ts": now, "grid_voltage": 0.0 if outage else 229.4, "grid_freq": 0.0 if outage else 50.01,
             "grid_power": 0 if outage else 420, "load_power": 610, "pv_power": 1340 if not outage else 860,
             "batt_power": -1450 if outage else -910, "batt_soc": 64 if outage else 82, "batt_voltage": 52.1,
             "batt_temp": 21.5, "dc_temp": 41, "running_status": 2, "day_pv": 6.4, "day_load": 8.9,
             "day_bought": 3.1, "day_sold": 0.0, "day_batt_charge": 4.2, "day_batt_dis": 3.3,
             "gen_power": 2210 if outage else 0}
        m.grid_ok = not outage
        m.since = (cur_out or now - 2 * 3600) if outage else now - 3 * 3600 - 25 * 60
        m.gen_on, m.gen_since = outage, now - 47 * 60
        d.update(grid_ok=m.grid_ok, since=m.since, gen_on=m.gen_on, gen_since=m.gen_since,
                 autonomy_h=None if d["batt_power"] < 0 else 8.2)
        m.last = d
        a.on_data(d)
        a.on_status("outage" if outage else "ok", "")

    def settle():
        for _ in range(12):
            a.qapp.processEvents()
            time.sleep(0.03)

    def shot(name, page, theme="light", outage=False, scroll=0):
        a.cfg["theme"] = theme
        a.retheme()
        live(outage)
        a.win.show_page(page)
        a.periodic(all_pages=True)
        p = a.win.pages[page]
        p.verticalScrollBar().setValue(scroll)
        settle()
        a.win.grab().save(os.path.join(OUT, name + ".png"))
        print("  ✓", name)

    def go():
        try:
            shot("overview-outage", "overview", outage=True)
            shot("overview", "overview")
            shot("overview-dark", "overview", "dark")
            shot("outages", "outages")
            shot("outages-dark", "outages", "dark")
            shot("grid", "grid")
            shot("energy", "energy")
            shot("energy-dark", "energy", "dark")
            shot("battery", "battery")
            shot("settings", "settings")
            shot("settings-cloud", "settings", scroll=a.win.pages["settings"].cards["cloud"].y() - 20)
            # сповіщення
            a.cfg["theme"] = "light"
            a.retheme()
            d = m.last
            for kind, note in (("toast-outage", M.note_outage("Дім", now, 5 * 3600 + 12 * 60, d, 7.6)),
                               ("toast-restore", M.note_restore("Дім", now, 3 * 3600 + 40 * 60,
                                                                dict(d, grid_voltage=229, grid_freq=50.0))),
                               ("toast-generator", M.note_gen_start("Дім", now, d, 45 * 60))):
                note.sticky = True
                a.toasts.show(note, 0)
                settle()
                a.toasts.items[0].grab().save(os.path.join(OUT, kind + ".png"))
                a.toasts.items[0].hide()
                a.toasts.items.clear()
                print("  ✓", kind)
        finally:
            shutil.rmtree(HOME, ignore_errors=True)
            os._exit(0)

    QTimer.singleShot(1200, go)
    a.qapp.exec()


if __name__ == "__main__":
    print("Знімки → %s" % OUT)
    main()
