# -*- coding: utf-8 -*-
"""Ядро: протокол Solarman V5, карта регістрів Deye, автопошук стіка, Telegram.

Адреси регістрів — з deye_hybrid.yaml (StephanJoubert/home_assistant_solarman),
однофазний гібрид Deye SUN-xK-SG03LP1.
"""
import concurrent.futures as cf
import json
import socket
import struct
import time
import urllib.request

# name: (адреса, множник, знаковий, зсув)
REGISTERS = {
    "running_status":   (0x003B, 1, False, 0),
    "day_batt_charge":  (0x0046, 0.1, False, 0),   # кВт·год за сьогодні
    "day_batt_dis":     (0x0047, 0.1, False, 0),
    "day_bought":       (0x004C, 0.1, False, 0),
    "day_sold":         (0x004D, 0.1, False, 0),
    "grid_freq":        (0x004F, 0.01, False, 0),
    "day_load":         (0x0054, 0.1, False, 0),
    "dc_temp":          (0x005A, 0.1, True, 1000),
    "ac_temp":          (0x005B, 0.1, True, 1000),
    "day_pv":           (0x006C, 0.1, False, 0),
    "pv1_voltage":      (0x006D, 0.1, False, 0),
    "pv1_current":      (0x006E, 0.1, False, 0),
    "pv2_voltage":      (0x006F, 0.1, False, 0),
    "pv2_current":      (0x0070, 0.1, False, 0),
    "grid_voltage":     (0x0096, 0.1, False, 0),
    "load_voltage":     (0x009D, 0.1, False, 0),
    "grid_power":       (0x00A9, 1, True, 0),     # + імпорт з мережі, - експорт
    "load_power":       (0x00B2, 1, False, 0),
    "batt_temp":        (0x00B6, 0.1, False, 1000),
    "batt_voltage":     (0x00B7, 0.01, False, 0),
    "batt_soc":         (0x00B8, 1, False, 0),
    "pv1_power":        (0x00BA, 1, False, 0),
    "pv2_power":        (0x00BB, 1, False, 0),
    "batt_power":       (0x00BE, 1, True, 0),     # + розряд, - заряд
    "batt_current":     (0x00BF, 0.01, True, 0),
    "load_freq":        (0x00C0, 0.01, False, 0),
    "grid_connected":   (0x00C2, 1, False, 0),    # 0 Off-Grid, 1 On-Grid
    "gen_power":        (0x00A6, 1, True, 0),     # потужність через порт GEN (генератор)
}
READ_BLOCKS = [(0x003B, 0x0070 - 0x003B + 1), (0x0096, 0x00C2 - 0x0096 + 1)]

RUNNING_STATUS = {0: "Очікування", 1: "Самоперевірка", 2: "Працює", 3: "Аварія"}


def modbus_crc(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


class SolarmanError(Exception):
    pass


class SolarmanV5:
    def __init__(self, ip, serial, port=8899, slave_id=1, timeout=6):
        self.ip, self.serial, self.port = ip, int(serial), int(port)
        self.slave_id, self.timeout = slave_id, timeout
        self.seq = 0x10

    def _frame(self, modbus: bytes) -> bytes:
        self.seq = (self.seq + 1) & 0xFF
        payload = b"\x02\x00\x00" + b"\x00" * 12 + modbus
        body = (b"\xA5" + struct.pack("<HHH", len(payload), 0x4510, self.seq)
                + struct.pack("<I", self.serial) + payload)
        return body + bytes([sum(body[1:]) & 0xFF, 0x15])

    @staticmethod
    def _recv(sock) -> bytes:
        buf = b""
        while True:
            chunk = sock.recv(1024)
            if not chunk:
                raise SolarmanError("стік закрив з'єднання")
            buf += chunk
            if len(buf) > 8192:          # сміття замість кадру — не накопичуємо безкінечно
                raise SolarmanError("некоректна відповідь стіка")
            s = buf.find(b"\xA5")
            if s >= 0 and len(buf) - s >= 3:
                need = 11 + struct.unpack("<H", buf[s + 1:s + 3])[0] + 2
                if len(buf) - s >= need:
                    return buf[s:s + need]

    def _read(self, sock, start, count):
        req = struct.pack(">BBHH", self.slave_id, 3, start, count)
        sock.sendall(self._frame(req + struct.pack("<H", modbus_crc(req))))
        for _ in range(3):
            fr = self._recv(sock)
            if fr[-1] != 0x15 or sum(fr[1:-2]) & 0xFF != fr[-2]:
                raise SolarmanError("пошкоджений кадр")
            if struct.unpack("<H", fr[3:5])[0] != 0x1510:
                continue
            mb = fr[25:-2]
            if len(mb) < 5:
                raise SolarmanError("порожня відповідь — перевірте серійний номер стіка")
            if mb[1] & 0x80:
                raise SolarmanError("помилка Modbus %d" % mb[2])
            if modbus_crc(mb[:-2]) != struct.unpack("<H", mb[-2:])[0]:
                raise SolarmanError("помилка CRC")
            n = mb[2]
            if n != count * 2 or len(mb) < 3 + n + 2:
                raise SolarmanError("неповна відповідь Modbus (%d з %d байт)" % (n, count * 2))
            return struct.unpack(">%dH" % count, mb[3:3 + n])
        raise SolarmanError("немає відповіді")

    def read_all(self) -> dict:
        raw = {}
        with socket.create_connection((self.ip, self.port), timeout=self.timeout) as s:
            s.settimeout(self.timeout)
            for start, count in READ_BLOCKS:
                for i, v in enumerate(self._read(s, start, count)):
                    raw[start + i] = v
        out = {}
        for k, (reg, scale, signed, offset) in REGISTERS.items():
            v = raw[reg]
            if signed and v >= 0x8000:
                v -= 0x10000
            v = (v - offset) * scale
            out[k] = round(v, 2) if scale != 1 else int(v)
        out["pv_power"] = out["pv1_power"] + out["pv2_power"]
        out["ts"] = time.time()
        # Після перезавантаження стік інколи віддає кадр із самих нулів. Напруга мережі 0 у такому кадрі
        # означала б хибне «світло зникло», тож нефізичні дані відкидаємо як помилку зв'язку.
        # Ознака такого кадру — температура інвертора −100 °C (регістр зі зсувом 1000 містить 0).
        if out["dc_temp"] <= -50 or not 0 <= out["batt_soc"] <= 100 or out["grid_voltage"] > 400:
            raise SolarmanError("некоректні дані від інвертора (температура %.0f °C, заряд %s %%)"
                                % (out["dc_temp"], out["batt_soc"]))
        return out


# ---------------------------------------------------------------------------
# Автопошук стіка
# ---------------------------------------------------------------------------
DISCOVERY_MSG = b"WIFIKIT-214028-READ"


def local_ipv4s():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return [ip for ip in ips if not ip.startswith("127.") and not ip.startswith("169.254.")]


def discover(timeout=3.0):
    """Повертає список {'ip','mac','serial'}. Шле широкомовний і адресний UDP-запит
    на порт 48899 кожному хосту /24-підмереж ПК (крізь ретранслятори broadcast часто не проходить)."""
    found = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("0.0.0.0", 0))
    sock.settimeout(0.3)
    if hasattr(socket, "SIO_UDP_CONNRESET"):   # Windows: не обривати прийом через ICMP «порт недоступний»
        try:
            sock.ioctl(socket.SIO_UDP_CONNRESET, False)
        except OSError:
            pass
    targets = ["255.255.255.255"]
    for ip in local_ipv4s():
        base = ip.rsplit(".", 1)[0]
        targets.append(base + ".255")
        targets += ["%s.%d" % (base, i) for i in range(1, 255)]
    for _ in range(2):
        for t in targets:
            try:
                sock.sendto(DISCOVERY_MSG, (t, 48899))
            except OSError:
                pass
    end = time.time() + timeout
    while time.time() < end:
        try:
            data, addr = sock.recvfrom(1024)
        except (socket.timeout, ConnectionResetError):
            continue
        except OSError:
            break
        parts = data.decode("ascii", "ignore").strip().split(",")
        # відповідь має прийти саме з тієї адреси, яку вона називає, — інакше будь-хто в мережі
        # міг би підсунути свою IP замість стіка
        if len(parts) >= 3 and parts[2].isdigit() and parts[0] == addr[0]:
            mac = ":".join(parts[1][i:i + 2] for i in range(0, len(parts[1]), 2))
            found[parts[0]] = {"ip": parts[0], "mac": mac, "serial": int(parts[2])}
    sock.close()
    if found:
        return list(found.values())
    # запасний варіант: хто слухає TCP 8899 (серійний номер доведеться ввести вручну)
    def probe(ip):
        c = socket.socket()
        c.settimeout(0.6)
        ok = c.connect_ex((ip, 8899)) == 0
        c.close()
        return ip if ok else None
    hosts = []
    for ip in local_ipv4s():
        base = ip.rsplit(".", 1)[0]
        hosts += ["%s.%d" % (base, i) for i in range(1, 255)]
    with cf.ThreadPoolExecutor(64) as ex:
        return [{"ip": ip, "mac": "", "serial": 0} for ip in ex.map(probe, hosts) if ip]


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
class Telegram:
    def __init__(self, token):
        self.base = "https://api.telegram.org/bot%s/" % token.strip()

    def call(self, method, params, timeout=30):
        req = urllib.request.Request(self.base + method, data=json.dumps(params).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            res = json.loads(r.read().decode())
        if not res.get("ok"):
            raise RuntimeError(res.get("description", "помилка Telegram"))
        return res["result"]

    def send(self, chat_id, html):
        return self.call("sendMessage", {"chat_id": chat_id, "text": html, "parse_mode": "HTML",
                                         "disable_web_page_preview": True})
