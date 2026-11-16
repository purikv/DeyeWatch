#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Імітатор WiFi-стіка Solarman (V5, порт 8899) для перевірки бота без інвертора.
Напругу мережі можна змінювати на льоту, записуючи число у файл fake_voltage.txt
(наприклад 0 — «світло зникло», 230 — «з'явилося»).

    python fake_logger.py --port 8899 --serial 2712345678
"""
import argparse
import os
import socket
import struct
import threading

from deyebot import modbus_crc

VFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_voltage.txt")


def regs():
    try:
        v = float(open(VFILE).read().strip())
    except Exception:
        v = 230.0
    r = {i: 0 for i in range(0, 0x200)}
    r[0x003B] = 2
    r[0x004F] = 5000 if v > 0 else 0
    r[0x0096] = int(v * 10)
    r[0x00A9] = 350 if v > 0 else 0
    r[0x00B2] = 640
    r[0x00B7] = 5210
    r[0x00B8] = 76
    r[0x00BA] = 1200
    r[0x00BB] = 0
    r[0x00BE] = (0x10000 - 500) if v > 0 else 640   # -500 = заряд
    r[0x00C2] = 1 if v > 0 else 0
    return r


def handle(conn, serial):
    with conn:
        while True:
            data = conn.recv(1024)
            if not data:
                return
            if struct.unpack("<I", data[7:11])[0] != serial:
                continue   # справжній логер мовчить при неправильному S/N
            mb = data[26:-2]
            slave, fn, start, count = struct.unpack(">BBHH", mb[:6])
            r = regs()
            body = struct.pack(">BBB", slave, fn, count * 2) + b"".join(
                struct.pack(">H", r[start + i]) for i in range(count))
            body += struct.pack("<H", modbus_crc(body))
            payload = b"\x02\x01" + b"\x00" * 12 + body
            hdr = b"\xA5" + struct.pack("<HHH", len(payload), 0x1510, struct.unpack("<H", data[5:7])[0]) \
                + struct.pack("<I", serial)
            frame = hdr + payload
            conn.sendall(frame + bytes([sum(frame[1:]) & 0xFF, 0x15]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--serial", type=int, default=2712345678)
    a = ap.parse_args()
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", a.port))
    s.listen()
    print("Імітатор логера на 127.0.0.1:%d, S/N %d" % (a.port, a.serial), flush=True)
    while True:
        c, _ = s.accept()
        threading.Thread(target=handle, args=(c, a.serial), daemon=True).start()


if __name__ == "__main__":
    main()
