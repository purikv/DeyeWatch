#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeyeBot — Telegram-бот, що сповіщає про зникнення/появу електромережі
за даними гібридного інвертора Deye (SUN-6K-SG03LP1) через WiFi-стік Solarman.

Тільки стандартна бібліотека Python 3 (без pip), щоб працювати на роутері
з Entware.

Запуск:
    python3 deyebot.py -c config.json            # робочий режим
    python3 deyebot.py -c config.json --probe    # один раз прочитати інвертор і вийти
    python3 deyebot.py -c config.json --test-telegram   # надіслати тестове повідомлення
"""

import argparse
import json
import os
import socket
import struct
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Регістри Deye hybrid (однофазний). Джерело: deye_hybrid.yaml проєкту
# StephanJoubert/home_assistant_solarman.  scale — множник, signed — знаковий.
# ---------------------------------------------------------------------------
REGISTERS = {
    "running_status": (0x003B, 1, False),   # 0 Stand-by, 1 Self-checking, 2 Normal, 3 FAULT
    "grid_freq":      (0x004F, 0.01, False),  # Гц
    "grid_voltage":   (0x0096, 0.1, False),   # В, L1
    "grid_power":     (0x00A9, 1, True),      # Вт (+ споживання з мережі, - віддача)
    "load_power":     (0x00B2, 1, False),     # Вт
    "batt_voltage":   (0x00B7, 0.01, False),  # В
    "batt_soc":       (0x00B8, 1, False),     # %
    "pv1_power":      (0x00BA, 1, False),     # Вт
    "pv2_power":      (0x00BB, 1, False),     # Вт
    "batt_status":    (0x00BD, 1, False),
    "batt_power":     (0x00BE, 1, True),      # Вт (+ розряд, - заряд)
    "grid_connected": (0x00C2, 1, False),     # 0 Off-Grid, 1 On-Grid
}
# Блоки читання (start, count), що покривають усі регістри вище.
READ_BLOCKS = [(0x003B, 1), (0x004F, 1), (0x0096, 0x00C2 - 0x0096 + 1)]

RUNNING_STATUS = {0: "Очікування", 1: "Самоперевірка", 2: "Норма", 3: "АВАРІЯ"}

DEFAULT_CONFIG = {
    "telegram_token": "",
    "chat_ids": [],
    "logger_ip": "192.168.50.100",
    "logger_serial": 0,
    "logger_port": 8899,
    "modbus_slave_id": 1,
    "poll_interval_sec": 10,
    "grid_min_voltage": 170.0,      # нижче — мережі немає
    "confirm_polls": 2,             # скільки опитувань поспіль має підтвердити зміну
    "offline_alert_polls": 6,       # після скількох невдалих опитувань писати «немає зв'язку»
    "low_soc_thresholds": [50, 30, 15],
    "timezone": "EET-2EEST,M3.5.0/3,M10.5.0/4",   # Київ
    "state_file": "state.json",
    "history_keep": 500,
    "name": "Дім",
}


# ---------------------------------------------------------------------------
# Solarman V5 + Modbus RTU
# ---------------------------------------------------------------------------
def modbus_crc(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


class SolarmanError(Exception):
    pass


class SolarmanV5:
    """Мінімальний клієнт протоколу Solarman V5 (TCP 8899) для читання holding-регістрів."""

    def __init__(self, ip, serial, port=8899, slave_id=1, timeout=8):
        self.ip = ip
        self.serial = int(serial)
        self.port = port
        self.slave_id = slave_id
        self.timeout = timeout
        self.seq = 0x10

    def _frame(self, modbus: bytes) -> bytes:
        self.seq = (self.seq + 1) & 0xFF
        payload = (b"\x02" + b"\x00\x00" + b"\x00" * 12) + modbus
        header = (b"\xA5" + struct.pack("<H", len(payload)) + struct.pack("<H", 0x4510)
                  + struct.pack("<H", self.seq) + struct.pack("<I", self.serial))
        body = header + payload
        checksum = sum(body[1:]) & 0xFF
        return body + bytes([checksum, 0x15])

    @staticmethod
    def _recv_frame(sock) -> bytes:
        buf = b""
        while len(buf) < 3:
            chunk = sock.recv(1024)
            if not chunk:
                raise SolarmanError("з'єднання закрито логером")
            buf += chunk
        start = buf.find(b"\xA5")
        if start < 0:
            raise SolarmanError("немає початку кадру V5")
        buf = buf[start:]
        while len(buf) < 3:
            buf += sock.recv(1024)
        need = 11 + struct.unpack("<H", buf[1:3])[0] + 2
        while len(buf) < need:
            chunk = sock.recv(1024)
            if not chunk:
                raise SolarmanError("неповний кадр V5")
            buf += chunk
        return buf[:need]

    def read_holding(self, sock, start: int, count: int):
        req = struct.pack(">BBHH", self.slave_id, 0x03, start, count)
        req += struct.pack("<H", modbus_crc(req))
        sock.sendall(self._frame(req))
        for _ in range(3):   # логер інколи шле службові кадри (heartbeat) — пропускаємо
            frame = self._recv_frame(sock)
            if frame[-1] != 0x15:
                raise SolarmanError("некоректний кінець кадру V5")
            if sum(frame[1:-2]) & 0xFF != frame[-2]:
                raise SolarmanError("помилка контрольної суми V5")
            control = struct.unpack("<H", frame[3:5])[0]
            if control != 0x1510:
                continue
            modbus = frame[25:-2]
            if len(modbus) < 5:
                raise SolarmanError("порожня відповідь Modbus (невірний серійний номер логера?)")
            if modbus[1] & 0x80:
                raise SolarmanError("помилка Modbus, код %d" % modbus[2])
            if modbus_crc(modbus[:-2]) != struct.unpack("<H", modbus[-2:])[0]:
                raise SolarmanError("помилка CRC Modbus")
            n = modbus[2]
            data = modbus[3:3 + n]
            return list(struct.unpack(">%dH" % (n // 2), data))
        raise SolarmanError("не отримано відповіді на запит")

    def read_all(self) -> dict:
        raw = {}
        with socket.create_connection((self.ip, self.port), timeout=self.timeout) as sock:
            sock.settimeout(self.timeout)
            for start, count in READ_BLOCKS:
                vals = self.read_holding(sock, start, count)
                for i, v in enumerate(vals):
                    raw[start + i] = v
        out = {}
        for name, (reg, scale, signed) in REGISTERS.items():
            v = raw[reg]
            if signed and v >= 0x8000:
                v -= 0x10000
            out[name] = round(v * scale, 2) if scale != 1 else v
        return out


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
class Telegram:
    def __init__(self, token):
        self.base = "https://api.telegram.org/bot%s/" % token

    def call(self, method, params, timeout=30):
        data = json.dumps(params).encode("utf-8")
        req = urllib.request.Request(self.base + method, data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            res = json.loads(r.read().decode("utf-8"))
        if not res.get("ok"):
            raise RuntimeError("Telegram: %s" % res)
        return res["result"]

    def send(self, chat_id, text):
        return self.call("sendMessage", {"chat_id": chat_id, "text": text,
                                         "parse_mode": "HTML",
                                         "disable_web_page_preview": True})


# ---------------------------------------------------------------------------
# Допоміжне
# ---------------------------------------------------------------------------
def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def fmt_time(ts):
    return time.strftime("%d.%m %H:%M", time.localtime(ts))


def fmt_dur(sec):
    sec = int(max(0, sec))
    d, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    parts = []
    if d:
        parts.append("%d д" % d)
    if h:
        parts.append("%d год" % h)
    parts.append("%d хв" % m)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Бот
# ---------------------------------------------------------------------------
class Bot:
    def __init__(self, cfg, cfg_dir):
        self.cfg = cfg
        self.tg = Telegram(cfg["telegram_token"])
        self.inv = SolarmanV5(cfg["logger_ip"], cfg["logger_serial"],
                              cfg["logger_port"], cfg["modbus_slave_id"])
        sf = cfg["state_file"]
        self.state_path = sf if os.path.isabs(sf) else os.path.join(cfg_dir, sf)
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.last = None          # останні дані інвертора
        self.last_ts = 0
        self.fail_count = 0
        self.pending = None       # кандидат на нову зміну стану
        self.pending_count = 0
        self.state = {
            "grid_ok": None, "since": None,
            "outages": [], "outbox": [],
            "soc_warned": [], "offline": False,
            "update_offset": 0,
        }
        self.load_state()

    # ---- стан ----
    def load_state(self):
        try:
            with open(self.state_path, encoding="utf-8") as f:
                self.state.update(json.load(f))
        except FileNotFoundError:
            pass
        except Exception as e:
            log("Не вдалося прочитати стан:", e)

    def save_state(self):
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.state_path)

    def notify(self, text):
        """Повідомлення всім отримувачам; зберігається в черзі, поки не відправиться."""
        with self.lock:
            for cid in self.cfg["chat_ids"]:
                self.state["outbox"].append({"chat_id": cid, "text": text})
            self.save_state()
        log("СПОВІЩЕННЯ:", text.replace("\n", " | "))
        self.wake.set()

    # ---- опитування інвертора ----
    def poll_loop(self):
        while True:
            try:
                data = self.inv.read_all()
                self.on_data(data)
            except Exception as e:
                self.on_fail(e)
            time.sleep(self.cfg["poll_interval_sec"])

    def on_fail(self, err):
        self.fail_count += 1
        log("Помилка опитування (%d): %s" % (self.fail_count, err))
        if self.fail_count == self.cfg["offline_alert_polls"] and not self.state["offline"]:
            with self.lock:
                self.state["offline"] = True
                self.save_state()
            self.notify("⚠️ <b>%s</b>: немає зв'язку з інвертором (WiFi-стік не відповідає).\n"
                        "Стан мережі зараз невідомий." % self.cfg["name"])

    def on_data(self, d):
        now = time.time()
        self.last, self.last_ts = d, now
        self.fail_count = 0
        if self.state["offline"]:
            with self.lock:
                self.state["offline"] = False
                self.save_state()
            self.notify("✅ <b>%s</b>: зв'язок з інвертором відновлено." % self.cfg["name"])

        grid_ok = d["grid_voltage"] >= self.cfg["grid_min_voltage"]

        if self.state["grid_ok"] is None:          # перший запуск
            with self.lock:
                self.state["grid_ok"] = grid_ok
                self.state["since"] = now
                self.save_state()
            log("Початковий стан мережі:", "є" if grid_ok else "немає")
            return

        if grid_ok == self.state["grid_ok"]:
            self.pending, self.pending_count = None, 0
            if not grid_ok:
                self.check_soc(d)
            return

        # можлива зміна — підтверджуємо кількома опитуваннями
        if self.pending is None:
            self.pending, self.pending_count = now, 1
        else:
            self.pending_count += 1
        if self.pending_count < self.cfg["confirm_polls"]:
            return

        change_ts = self.pending
        self.pending, self.pending_count = None, 0
        prev_since = self.state["since"] or change_ts
        with self.lock:
            self.state["grid_ok"] = grid_ok
            self.state["since"] = change_ts
            if not grid_ok:
                self.state["soc_warned"] = []
            else:
                self.state["outages"].append({"start": prev_since, "end": change_ts})
                self.state["outages"] = self.state["outages"][-self.cfg["history_keep"]:]
            self.save_state()

        name = self.cfg["name"]
        if not grid_ok:
            self.notify("🔴 <b>%s: світло зникло</b> о %s\n"
                        "Світло було: %s\n"
                        "Батарея: %s%%, навантаження: %s Вт"
                        % (name, fmt_time(change_ts), fmt_dur(change_ts - prev_since),
                           d["batt_soc"], d["load_power"]))
        else:
            self.notify("🟢 <b>%s: світло з'явилося</b> о %s\n"
                        "Не було: %s\n"
                        "Напруга: %s В, батарея: %s%%"
                        % (name, fmt_time(change_ts), fmt_dur(change_ts - prev_since),
                           d["grid_voltage"], d["batt_soc"]))

    def check_soc(self, d):
        soc = d["batt_soc"]
        crossed = [th for th in self.cfg["low_soc_thresholds"]
                   if soc <= th and th not in self.state["soc_warned"]]
        if not crossed:
            return
        th = min(crossed)   # одне повідомлення про найнижчий перетнутий поріг
        with self.lock:
            self.state["soc_warned"].extend(crossed)
            self.save_state()
        self.notify("🪫 <b>%s</b>: заряд батареї %s%% (поріг %s%%).\n"
                    "Світла немає вже %s, навантаження %s Вт."
                    % (self.cfg["name"], soc, th,
                       fmt_dur(time.time() - self.state["since"]), d["load_power"]))

    # ---- відправка черги ----
    def sender_loop(self):
        while True:
            self.wake.wait(20)
            self.wake.clear()
            while True:
                with self.lock:
                    if not self.state["outbox"]:
                        break
                    msg = self.state["outbox"][0]
                try:
                    self.tg.send(msg["chat_id"], msg["text"])
                except urllib.error.HTTPError as e:
                    if 400 <= e.code < 500 and e.code != 429:
                        log("Telegram відхилив повідомлення (%s), пропускаю" % e.code)
                    else:
                        log("Telegram недоступний (%s), повтор пізніше" % e.code)
                        break
                except Exception as e:
                    log("Немає інтернету / Telegram недоступний: %s — повтор пізніше" % e)
                    break
                with self.lock:
                    if self.state["outbox"] and self.state["outbox"][0] is msg:
                        self.state["outbox"].pop(0)
                    self.save_state()

    # ---- команди ----
    def text_status(self):
        d = self.last
        name = self.cfg["name"]
        if self.state["grid_ok"] is None:
            grid = "невідомо"
        elif self.state["grid_ok"]:
            grid = "🟢 є, %s" % fmt_dur(time.time() - self.state["since"])
        else:
            grid = "🔴 немає, %s" % fmt_dur(time.time() - self.state["since"])
        lines = ["<b>%s</b>" % name, "Мережа: " + grid]
        if d is None:
            lines.append("Дані з інвертора ще не отримано.")
            return "\n".join(lines)
        age = time.time() - self.last_ts
        if age > 3 * self.cfg["poll_interval_sec"] + 30:
            lines.append("⚠️ Дані застарілі: %s тому" % fmt_dur(age))
        lines += [
            "Напруга мережі: %s В, %s Гц" % (d["grid_voltage"], d["grid_freq"]),
            "Мережа (потужність): %s Вт" % d["grid_power"],
            "Навантаження: %s Вт" % d["load_power"],
            "Батарея: %s%%, %s В, %s Вт (%s)" % (
                d["batt_soc"], d["batt_voltage"], abs(d["batt_power"]),
                "розряд" if d["batt_power"] > 0 else ("заряд" if d["batt_power"] < 0 else "спокій")),
            "СЕС: %s Вт" % (d["pv1_power"] + d["pv2_power"]),
            "Інвертор: %s, %s" % (RUNNING_STATUS.get(d["running_status"], d["running_status"]),
                                  "On-Grid" if d["grid_connected"] == 1 else "Off-Grid"),
        ]
        return "\n".join(lines)

    def text_history(self, n=10):
        outs = self.state["outages"]
        now = time.time()
        lines = ["<b>Відключення — %s</b>" % self.cfg["name"]]
        if self.state["grid_ok"] is False:
            lines.append("🔴 зараз: з %s, триває %s" % (fmt_time(self.state["since"]),
                                                        fmt_dur(now - self.state["since"])))
        if not outs and self.state["grid_ok"] is not False:
            lines.append("Записів ще немає.")
            return "\n".join(lines)
        for o in reversed(outs[-n:]):
            lines.append("• %s → %s (%s)" % (fmt_time(o["start"]),
                                             time.strftime("%H:%M", time.localtime(o["end"])),
                                             fmt_dur(o["end"] - o["start"])))
        for days, label in ((1, "24 год"), (7, "7 днів")):
            since = now - days * 86400
            total, cnt = 0, 0
            for o in outs:
                if o["end"] > since:
                    total += o["end"] - max(o["start"], since)
                    cnt += 1
            if self.state["grid_ok"] is False:
                total += now - max(self.state["since"], since)
                cnt += 1
            lines.append("За %s: %d відкл., без світла %s" % (label, cnt, fmt_dur(total)))
        return "\n".join(lines)

    def handle(self, msg):
        chat_id = msg["chat"]["id"]
        text = (msg.get("text") or "").strip()
        if not text.startswith("/"):
            return
        cmd = text.split()[0].split("@")[0].lower()
        args = text.split()[1:]
        if chat_id not in self.cfg["chat_ids"]:
            self.tg.send(chat_id, "Доступ не надано. Ваш chat_id: <code>%s</code>\n"
                                  "Передайте його власнику бота." % chat_id)
            return
        if cmd in ("/status", "/s"):
            reply = self.text_status()
        elif cmd in ("/history", "/h"):
            n = 10
            if args and args[0].isdigit():
                n = max(1, min(50, int(args[0])))
            reply = self.text_history(n)
        elif cmd == "/id":
            reply = "chat_id: <code>%s</code>" % chat_id
        else:
            reply = ("Команди:\n/status — стан мережі, батареї, навантаження\n"
                     "/history [N] — останні відключення\n/id — ваш chat_id")
        self.tg.send(chat_id, reply)

    def updates_loop(self):
        try:
            self.tg.call("setMyCommands", {"commands": [
                {"command": "status", "description": "Стан мережі та батареї"},
                {"command": "history", "description": "Історія відключень"},
                {"command": "id", "description": "Мій chat_id"},
            ]})
        except Exception as e:
            log("setMyCommands:", e)
        while True:
            try:
                ups = self.tg.call("getUpdates", {"offset": self.state["update_offset"],
                                                  "timeout": 25,
                                                  "allowed_updates": ["message"]}, timeout=35)
                for u in ups:
                    with self.lock:
                        self.state["update_offset"] = u["update_id"] + 1
                        self.save_state()
                    if "message" in u:
                        try:
                            self.handle(u["message"])
                        except Exception as e:
                            log("Помилка обробки команди:", e)
            except Exception as e:
                log("getUpdates:", e)
                time.sleep(15)

    def run(self):
        log("DeyeBot запущено. Логер %s, S/N %s" % (self.cfg["logger_ip"], self.cfg["logger_serial"]))
        threading.Thread(target=self.poll_loop, daemon=True).start()
        threading.Thread(target=self.sender_loop, daemon=True).start()
        self.updates_loop()


# ---------------------------------------------------------------------------
def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = dict(DEFAULT_CONFIG)
        cfg.update(json.load(f))
    cfg["chat_ids"] = [int(c) for c in cfg["chat_ids"]]
    cfg["logger_serial"] = int(cfg["logger_serial"])
    return cfg


def main():
    ap = argparse.ArgumentParser(description="Telegram-бот відключень світла для Deye")
    ap.add_argument("-c", "--config", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
    ap.add_argument("--probe", action="store_true", help="прочитати інвертор один раз і вийти")
    ap.add_argument("--test-telegram", action="store_true", help="надіслати тестове повідомлення")
    a = ap.parse_args()

    cfg = load_config(a.config)
    if cfg.get("timezone") and hasattr(time, "tzset"):
        os.environ["TZ"] = cfg["timezone"]
        time.tzset()

    if a.probe:
        inv = SolarmanV5(cfg["logger_ip"], cfg["logger_serial"], cfg["logger_port"], cfg["modbus_slave_id"])
        try:
            d = inv.read_all()
        except Exception as e:
            print("ПОМИЛКА:", e)
            if isinstance(e, socket.timeout):
                print("Порада: перевірте logger_serial — при неправильному серійному номері логер мовчить.")
            sys.exit(1)
        for k, v in d.items():
            print("%-15s %s" % (k, v))
        print("Мережа:", "Є" if d["grid_voltage"] >= cfg["grid_min_voltage"] else "НЕМАЄ")
        return

    if not cfg["telegram_token"]:
        sys.exit("Не вказано telegram_token у конфігу")

    if a.test_telegram:
        tg = Telegram(cfg["telegram_token"])
        for cid in cfg["chat_ids"]:
            tg.send(cid, "✅ DeyeBot: тестове повідомлення (%s)" % cfg["name"])
            print("Надіслано", cid)
        return

    cfg_dir = os.path.dirname(os.path.abspath(a.config))
    while True:
        try:
            Bot(cfg, cfg_dir).run()
        except KeyboardInterrupt:
            break
        except Exception:
            traceback.print_exc()
            time.sleep(30)


if __name__ == "__main__":
    main()
