# -*- coding: utf-8 -*-
import json
import os
import sys
import threading
import time

APP_NAME = "DeyeWatch"

DEFAULTS = {
    "name": "Дім",
    # підключення
    "logger_ip": "",           # порожньо — при першому запуску стік знаходиться в мережі автоматично
    "logger_serial": 0,
    "logger_port": 8899,
    "poll_interval_sec": 10,
    # визначення відключення
    "grid_min_voltage": 170.0,
    "confirm_polls": 2,
    "offline_alert_polls": 6,
    # батарея
    "battery_kwh": 10.0,
    "battery_min_soc": 15,
    "low_soc_thresholds": [50, 30, 20],
    "has_pv": True,
    # генератор на порту GEN
    "has_gen": False,          # вмикається сам, щойно інвертор уперше покаже потужність на GEN
    "gen_min_power": 30,       # Вт: від цієї потужності генератор вважається запущеним
    "notify_gen": True,
    # якість мережі
    "v_low": 207.0,     # 230 В −10 %
    "v_high": 253.0,    # 230 В +10 %
    "v_alert_minutes": 2,
    # сповіщення: що
    "notify_outage": True,
    "notify_restore": True,
    "notify_low_soc": True,
    "notify_voltage": True,
    "notify_offline": True,
    "notify_daily_summary": False,
    # сповіщення: куди
    "desktop_notify": True,
    "toast_seconds": 12,
    "sound": True,
    "telegram_enabled": False,
    "telegram_token": "",
    "telegram_chat_ids": "",
    "telegram_commands": False,
    # аналітика
    "stats_enabled": True,
    "an_outages": True,
    "an_grid": True,
    "an_energy": True,
    "an_battery": True,
    "keep_days": 365,
    # інтерфейс
    "theme": "system",      # system | light | dark
    "autostart": False,
    "start_minimized": True,
    # хмара Deye Cloud (догрузка історії)
    "cloud_enabled": False,
    "cloud_base": "https://eu1-developer.deyecloud.com",
    "cloud_app_id": "",
    "cloud_app_secret": "",
    "cloud_email": "",
    "cloud_password_sha": "",    # зберігається лише SHA-256, як вимагає API
    "cloud_backfill_days": 30,
}


def config_dir():
    if os.environ.get("DEYEWATCH_HOME"):
        d = os.environ["DEYEWATCH_HOME"]
    elif sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, APP_NAME)
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        d = os.path.join(base, APP_NAME.lower())
    os.makedirs(d, exist_ok=True)
    private(d, 0o700)
    return d


def private(path, mode=0o600):
    """Linux/macOS: налаштування містять токени — доступ лише власнику. На Windows профіль і так особистий."""
    if os.name == "posix":
        try:
            os.chmod(path, mode)
        except OSError:
            pass


def is_deye_cloud(url):
    """Ключі й пароль Deye Cloud можна надсилати лише на сервери Deye і лише через HTTPS."""
    from urllib.parse import urlparse
    try:
        u = urlparse(str(url).strip())
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    return u.scheme == "https" and (host == "deyecloud.com" or host.endswith(".deyecloud.com"))


class Config(dict):
    _lock = threading.Lock()

    def __init__(self):
        super().__init__(DEFAULTS)
        self.path = os.path.join(config_dir(), "settings.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("не словник")
            self.update(data)
        except FileNotFoundError:
            self.save()
        except Exception:
            # пошкоджений файл не перезаписуємо мовчки — зберігаємо копію, щоб налаштування можна було відновити
            try:
                os.replace(self.path, self.path + ".broken-%d" % int(time.time()))
            except OSError:
                pass
            self.save()
        if not is_deye_cloud(self.get("cloud_base")):
            self["cloud_base"] = DEFAULTS["cloud_base"]
        private(self.path)

    def save(self):
        # зберігають і вікно, і фонові потоки (нова IP стіка, генератор) — тому під замком і з fsync:
        # навіть при раптовому вимкненні живлення лишиться або старий, або новий файл, але не порожній
        with self._lock:
            tmp = "%s.%d.tmp" % (self.path, threading.get_ident())
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(dict(self), f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            private(tmp)
            os.replace(tmp, self.path)

    def chat_ids(self):
        return [c.strip() for c in str(self["telegram_chat_ids"]).replace(";", ",").split(",") if c.strip()]


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"


def autostart_cmd():
    exe = sys.executable if getattr(sys, "frozen", False) else None
    if sys.platform.startswith("win"):
        cmd = '"%s"' % exe if exe else '"%s" "%s"' % (sys.executable.replace("python.exe", "pythonw.exe"),
                                                     os.path.abspath(sys.argv[0]))
        return cmd + " --minimized"
    # запускач задає змінну DEYEWATCH_LAUNCHER: /usr/bin/deyewatch (.deb) або ~/.local/bin/deyewatch (install.sh)
    launcher = os.environ.get("DEYEWATCH_LAUNCHER") or os.path.expanduser("~/.local/bin/deyewatch")
    return (exe or (launcher if os.path.exists(launcher) else
                    '%s "%s"' % (sys.executable, os.path.abspath(sys.argv[0])))) + " --minimized"


def autostart_state():
    """Фактичний стан автозапуску в системі:
    ok — запис є і веде на цю програму; missing — запису немає; other — веде на інший файл
    (програму перенесли); disabled — вимкнено в Диспетчері завдань → Автозавантаження."""
    if sys.platform.startswith("win"):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                val = winreg.QueryValueEx(k, APP_NAME)[0]
        except OSError:
            return "missing"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY) as k:
                flag = winreg.QueryValueEx(k, APP_NAME)[0]
            if flag and flag[0] % 2 == 1:      # 2 — дозволено, 3 — вимкнено користувачем
                return "disabled"
        except OSError:
            pass
        return "ok" if val.strip().lower() == autostart_cmd().strip().lower() else "other"
    p = os.path.expanduser("~/.config/autostart/deyewatch.desktop")
    if not os.path.exists(p):
        return "missing"
    txt = open(p, encoding="utf-8", errors="replace").read()
    if "X-GNOME-Autostart-enabled=false" in txt or "Hidden=true" in txt:
        return "disabled"
    return "ok" if ("Exec=%s" % autostart_cmd()) in txt else "other"


def ensure_autostart(enabled):
    """Приводить систему у відповідність до налаштування (викликається при кожному запуску):
    якщо автозапуск увімкнено, але запису немає або програму перенесли — записує заново."""
    if os.environ.get("DEYEWATCH_HOME"):      # тестова/портативна копія — системний автозапуск не чіпаємо
        return autostart_state()
    st = autostart_state()
    if enabled and st in ("missing", "other"):
        set_autostart(True)
    elif not enabled and st in ("ok", "disabled"):
        # «other» не видаляємо: запис веде на іншу копію програми, яку користувач, можливо, використовує
        set_autostart(False)
    return autostart_state()


def set_autostart(enabled):
    exe = sys.executable if getattr(sys, "frozen", False) else None
    if sys.platform.startswith("win"):
        import winreg
        cmd = autostart_cmd()
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                           0, winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(k)
    else:
        d = os.path.expanduser("~/.config/autostart")
        p = os.path.join(d, "deyewatch.desktop")
        if enabled:
            os.makedirs(d, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write("[Desktop Entry]\nType=Application\nName=DeyeWatch\n"
                        "Comment=Сповіщення про відключення світла\n"
                        "Exec=%s\nX-GNOME-Autostart-enabled=true\n" % autostart_cmd())
        elif os.path.exists(p):
            os.remove(p)
