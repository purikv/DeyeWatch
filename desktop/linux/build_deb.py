# -*- coding: utf-8 -*-
"""Збирає deyewatch_<версія>_amd64.deb без dpkg — працює і на Windows.

Пакет ставить програму в /opt/deyewatch, запускач /usr/bin/deyewatch, ярлик у меню.
PySide6 іде всередині пакета (колеса з PyPI для Linux x86_64), тож встановлення не потребує інтернету:
postinst створює venv і ставить те колесо, яке підходить до Python і glibc цієї системи
(6.12 — glibc ≥ 2.34, Python 3.10–3.15; 6.9 — glibc ≥ 2.28, Python 3.9–3.13).

    python linux/build_deb.py            # колеса беруться з build_deb/wheels (або завантажуються)
"""
import gzip
import hashlib
import io
import lzma
import os
import re
import subprocess
import sys
import tarfile
import time

VERSION = re.search(r'__version__ = "([^"]+)"', open(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dw", "__init__.py"), encoding="utf-8").read()).group(1)
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # desktop/
WHEELS = os.path.join(ROOT, "build_deb", "wheels")
OUT = os.path.join(ROOT, "dist", "deyewatch_%s_amd64.deb" % VERSION)
APP = "/opt/deyewatch"

WHEEL_SETS = [  # (версія, платформа, python для pip download)
    ("6.12.0", "manylinux_2_34_x86_64", "3.14"),
    ("6.9.3", "manylinux_2_28_x86_64", "3.10"),
]

DEPENDS = ", ".join([
    "python3 (>= 3.9)", "python3-venv",
    # системні бібліотеки, потрібні Qt (xcb) з коліс PySide6
    "libegl1", "libgl1", "libfontconfig1", "libdbus-1-3", "libxkbcommon0", "libxkbcommon-x11-0",
    "libxcb-cursor0", "libxcb-icccm4", "libxcb-image0", "libxcb-keysyms1", "libxcb-randr0",
    "libxcb-render-util0", "libxcb-shape0", "libxcb-xfixes0", "libxcb-xinerama0", "libxcb-xkb1",
])

LAUNCHER = """#!/bin/sh
# Сповіщення в куті екрана потребують X11/XWayland (на чистому Wayland вікна не можуть самі вибрати місце)
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb;wayland}"
export DEYEWATCH_LAUNCHER=/usr/bin/deyewatch
if [ ! -x %(app)s/venv/bin/python ]; then
    echo "DeyeWatch: середовище не встановлене. Виконайте: sudo dpkg-reconfigure deyewatch" >&2
    exit 1
fi
exec %(app)s/venv/bin/python -B %(app)s/app/deyewatch.py "$@"
""" % {"app": APP}

DESKTOP = """[Desktop Entry]
Type=Application
Name=DeyeWatch
GenericName=Відключення світла
Comment=Сповіщення про відключення світла та статистика інвертора Deye
Exec=/usr/bin/deyewatch
Icon=deyewatch
Terminal=false
Categories=Utility;Monitor;
StartupWMClass=DeyeWatch
"""

POSTINST = """#!/bin/sh
set -e
APP=%(app)s
case "$1" in
  configure)
    rm -rf "$APP/venv"
    PY=python3
    echo "DeyeWatch: створюю середовище Python ($($PY --version 2>&1))"
    $PY -m venv "$APP/venv"
    if ! "$APP/venv/bin/python" -m pip install --quiet --disable-pip-version-check --no-index \\
            --find-links "$APP/wheels" PySide6-Essentials; then
        echo "DeyeWatch: вбудовані колеса PySide6 не підходять до цієї системи — пробую з інтернету" >&2
        "$APP/venv/bin/python" -m pip install --quiet --disable-pip-version-check "PySide6-Essentials>=6.5"
    fi
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
    echo "DeyeWatch встановлено: меню програм → DeyeWatch або команда deyewatch"
    ;;
esac
exit 0
""" % {"app": APP}

PRERM = """#!/bin/sh
set -e
# середовище створює postinst — прибираємо його самі, бо dpkg про нього не знає
rm -rf %(app)s/venv
find %(app)s/app -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
exit 0
""" % {"app": APP}

POSTRM = """#!/bin/sh
set -e
if [ "$1" = "purge" ]; then rm -rf %(app)s; fi
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
exit 0
""" % {"app": APP}

COPYRIGHT = """DeyeWatch — сповіщення про відключення світла за даними інвертора Deye.
Вбудовані колеса PySide6 / Qt for Python поширюються за ліцензією LGPLv3 (https://www.qt.io/qt-for-python).
"""


def ensure_wheels():
    os.makedirs(WHEELS, exist_ok=True)
    have = os.listdir(WHEELS)
    for ver, plat, py in WHEEL_SETS:
        if any(n.startswith("pyside6_essentials-%s-" % ver) and plat in n for n in have):
            continue
        print("Завантажую PySide6-Essentials %s (%s)…" % (ver, plat))
        subprocess.check_call([sys.executable, "-m", "pip", "download", "PySide6-Essentials==%s" % ver,
                               "--only-binary=:all:", "--platform", plat, "--python-version", py,
                               "--implementation", "cp", "-d", WHEELS, "--disable-pip-version-check", "-q"])
    return sorted(n for n in os.listdir(WHEELS) if n.endswith(".whl"))


def collect(wheels):
    """[(шлях у пакеті, байти, режим)]"""
    files = []

    def add(path, data, mode=0o644):
        if isinstance(data, str):
            data = data.encode("utf-8")
        files.append((path, data, mode))

    for name in ["deyewatch.py", "requirements.txt", "deyewatch.png"]:
        add("%s/app/%s" % (APP, name), open(os.path.join(ROOT, name), "rb").read())
    for name in sorted(os.listdir(os.path.join(ROOT, "dw"))):
        if name.endswith(".py"):
            add("%s/app/dw/%s" % (APP, name), open(os.path.join(ROOT, "dw", name), "rb").read())
    for w in wheels:
        add("%s/wheels/%s" % (APP, w), open(os.path.join(WHEELS, w), "rb").read())
    add("/usr/bin/deyewatch", LAUNCHER, 0o755)
    add("/usr/share/applications/deyewatch.desktop", DESKTOP)
    add("/usr/share/icons/hicolor/256x256/apps/deyewatch.png", open(os.path.join(ROOT, "deyewatch.png"), "rb").read())
    add("/usr/share/doc/deyewatch/copyright", COPYRIGHT)
    return files


def tar_bytes(entries, compress):
    """entries: [(шлях, байти або None для теки, режим)] → стиснутий tar з власником root."""
    buf = io.BytesIO()
    now = int(time.time())
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tf:
        for path, data, mode in entries:
            ti = tarfile.TarInfo("." + path if path.startswith("/") else path)
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = "root"
            ti.mtime = now
            ti.mode = mode
            if data is None:
                ti.type = tarfile.DIRTYPE
                tf.addfile(ti)
            else:
                ti.size = len(data)
                tf.addfile(ti, io.BytesIO(data))
    raw = buf.getvalue()
    return compress(raw)


def with_dirs(files):
    dirs = set()
    for path, _, _ in files:
        parts = path.strip("/").split("/")[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add("/" + "/".join(parts[:i]))
    out = [("./", None, 0o755)] + [(d, None, 0o755) for d in sorted(dirs)]
    return out + sorted(files)


def ar_member(name, data):
    hdr = "%-16s%-12d%-6d%-6d%-8s%-10d`\n" % (name, int(time.time()), 0, 0, "100644", len(data))
    assert len(hdr) == 60
    return hdr.encode("ascii") + data + (b"\n" if len(data) % 2 else b"")


def main():
    wheels = ensure_wheels()
    files = collect(wheels)
    size_kb = sum(len(d) for _, d, _ in files) // 1024 + 1
    control = "\n".join([
        "Package: deyewatch",
        "Version: %s" % VERSION,
        "Section: utils",
        "Priority: optional",
        "Architecture: amd64",
        "Depends: %s" % DEPENDS,
        "Installed-Size: %d" % size_kb,
        "Maintainer: DeyeWatch <deyewatch@localhost>",
        "Homepage: https://github.com/",
        "Description: сповіщення про відключення світла за даними інвертора Deye",
        " DeyeWatch читає дані гібридного інвертора Deye через WiFi-стік Solarman у",
        " локальній мережі, показує сповіщення про зникнення й появу світла, заряд",
        " батареї, якість мережі та статистику відключень і енергії. Telegram і",
        " Deye Cloud — опційно.",
    ]) + "\n"
    control = control.replace("Homepage: https://github.com/\n", "")
    md5 = "".join("%s  %s\n" % (hashlib.md5(d).hexdigest(), p.lstrip("/")) for p, d, _ in files)
    ctl = [("./", None, 0o755),
           ("./control", control.encode("utf-8"), 0o644),
           ("./md5sums", md5.encode("utf-8"), 0o644),
           ("./postinst", POSTINST.encode("utf-8"), 0o755),
           ("./prerm", PRERM.encode("utf-8"), 0o755),
           ("./postrm", POSTRM.encode("utf-8"), 0o755)]
    control_tar = tar_bytes(ctl, lambda b: gzip.compress(b, 9, mtime=0))
    print("Стискаю дані (xz)…")
    data_tar = tar_bytes(with_dirs(files), lambda b: lzma.compress(b, preset=6))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(b"!<arch>\n")
        f.write(ar_member("debian-binary", b"2.0\n"))
        f.write(ar_member("control.tar.gz", control_tar))
        f.write(ar_member("data.tar.xz", data_tar))
    print("Готово: %s (%.1f МБ)" % (OUT, os.path.getsize(OUT) / 1e6))


if __name__ == "__main__":
    main()
