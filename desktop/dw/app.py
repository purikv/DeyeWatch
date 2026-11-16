# -*- coding: utf-8 -*-
"""Головне вікно, трей, запуск."""
import os
import sys
import time

from PySide6.QtCore import QLockFile, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QGuiApplication
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu,
                               QPushButton, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from . import icons, theme
from . import messages as M
from .config import Config, config_dir
from .monitor import Monitor
from .pages import Battery, Energy, Grid, Outages, Overview
from .settings_page import SettingsPage
from .store import Store
from .toast import ToastManager
from .widgets import Insight, Tile


class MainWindow(QMainWindow):
    NAV = [("overview", "Огляд", "overview", None), ("outages", "Відключення", "bolt_off", "an_outages"),
           ("grid", "Якість мережі", "wave", "an_grid"), ("energy", "Енергія", "sun", "an_energy"),
           ("battery", "Батарея", "battery", "an_battery"), ("settings", "Налаштування", "gear", None)]

    NAV_TIPS = {
        "overview": "Що відбувається зараз: є світло чи ні, звідки енергія, заряд батареї",
        "outages": "Скільки разів і коли вимикали світло, найчастіші години",
        "grid": "Напруга й частота в мережі — чи безпечно для техніки",
        "energy": "Скільки вироблено сонцем, спожито і взято з мережі",
        "battery": "Заряд, прогноз роботи, температура й цикли батареї",
        "settings": "Підключення, сповіщення, Telegram, хмара",
    }

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowTitle("DeyeWatch — світло вдома")
        self.resize(1180, 820)
        self.setMinimumSize(900, 600)
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        hl = QHBoxLayout(root)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)

        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(220)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(14, 18, 14, 14)
        sv.setSpacing(4)
        brand = QHBoxLayout()
        self.logo = QLabel()
        self.logo.setFixedSize(34, 34)
        brand.addWidget(self.logo)
        bt = QVBoxLayout()
        bt.setSpacing(0)
        t = QLabel("DeyeWatch")
        f = QFont()
        f.setPixelSize(16)
        f.setWeight(QFont.DemiBold)
        t.setObjectName("brand")
        bt.addWidget(t)
        self.brand_sub = QLabel(app.cfg["name"])
        self.brand_sub.setObjectName("faint")
        bt.addWidget(self.brand_sub)
        brand.addLayout(bt)
        brand.addStretch()
        sv.addLayout(brand)
        sv.addSpacing(18)

        self.stack = QStackedWidget()
        self.pages = {
            "overview": Overview(app), "outages": Outages(app), "grid": Grid(app),
            "energy": Energy(app), "battery": Battery(app), "settings": SettingsPage(app),
        }
        self.group = QButtonGroup(self)
        self.btns = {}
        for key, label, ic, _ in self.NAV:
            b = QPushButton("  " + label)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.show_page(k))
            b.setToolTip(self.NAV_TIPS.get(key, ""))
            self.group.addButton(b)
            self.btns[key] = (b, ic)
            if key == "settings":
                sv.addStretch()
            sv.addWidget(b)
            self.stack.addWidget(self.pages[key])
        self.conn = QLabel("")
        self.conn.setObjectName("faint")
        self.conn.setWordWrap(True)
        self.sync = QLabel("")
        self.sync.setObjectName("faint")
        self.sync.setWordWrap(True)
        sv.addSpacing(8)
        sv.addWidget(self.sync)
        sv.addWidget(self.conn)
        hl.addWidget(side)
        hl.addWidget(self.stack, 1)
        self.restyle()
        self.apply_visibility()
        self.show_page("overview")

    def restyle(self):
        col = theme.T["ok"] if self.app.monitor.grid_ok is not False else theme.T["bad"]
        self.logo.setPixmap(icons.badge_icon(col, size=68).pixmap(34, 34))
        for key, (b, ic) in self.btns.items():
            b.setIcon(icons.pixmap(ic, theme.T["muted"], 18))

    def apply_visibility(self):
        for key, _, _, flag in self.NAV:
            if flag:
                self.btns[key][0].setVisible(bool(self.app.cfg[flag]))

    def show_page(self, key):
        self.btns[key][0].setChecked(True)
        page = self.pages[key]
        self.stack.setCurrentWidget(page)
        try:
            page.refresh()
        except Exception as e:
            print("refresh", key, e)

    def open_settings(self, section):
        self.show_page("settings")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, lambda: self.pages["settings"].goto(section))

    def closeEvent(self, e):
        e.ignore()
        self.hide()
        if not self.app.cfg.get("_tray_hint_shown"):
            self.app.cfg["_tray_hint_shown"] = True
            self.app.cfg.save()
            self.app.toasts.show(M.Note("online", "DeyeWatch працює у фоні",
                                        "Іконка біля годинника · подвійний клік відкриває вікно",
                                        [], None), 8)


class App:
    def __init__(self, argv):
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        self.qapp = QApplication(argv)
        self.qapp.setApplicationName("DeyeWatch")
        self.qapp.setQuitOnLastWindowClosed(False)
        self.lock = QLockFile(os.path.join(config_dir(), "deyewatch.lock"))
        if not self.lock.tryLock(100):
            print("DeyeWatch вже запущено")
            sys.exit(0)
        self.cfg = Config()
        self.store = Store(os.path.join(config_dir(), "history.sqlite3"))
        theme.apply(self.cfg["theme"])
        self.qapp.setStyleSheet(theme.qss())
        try:
            self.qapp.styleHints().colorSchemeChanged.connect(lambda *_: self.retheme())
        except Exception:
            pass
        try:
            from .config import ensure_autostart
            ensure_autostart(self.cfg["autostart"])
        except Exception as e:
            print("autostart", e)
        self.monitor = Monitor(self.cfg, self.store)
        self.toasts = ToastManager(self.open_window)
        self.win = MainWindow(self)
        self.win.setWindowIcon(icons.badge_icon(theme.T["accent"]))
        self.qapp.setWindowIcon(icons.badge_icon(theme.T["accent"]))

        self.tray = QSystemTrayIcon(icons.badge_icon(theme.T["faint"]))
        menu = QMenu()
        self.tray_state = QAction("Підключення…")
        self.tray_state.setEnabled(False)
        menu.addAction(self.tray_state)
        menu.addSeparator()
        menu.addAction("Відкрити", self.open_window)
        menu.addAction("Статистика відключень", lambda: (self.open_window(), self.win.show_page("outages")))
        menu.addSeparator()
        menu.addAction("Вийти", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("DeyeWatch")
        self.tray.activated.connect(self._tray_click)
        self.tray.show()
        self.menu = menu

        self.monitor.data.connect(self.on_data)
        self.monitor.note.connect(self.on_note)
        self.monitor.status.connect(self.on_status)
        self.monitor.cloud.connect(self.on_cloud)
        self.monitor.syncing.connect(self.on_syncing)
        self.show_sync_state()
        self.monitor.start()
        # повернення до програми (з іншого вікна, з трею, після блокування екрана) — оновлюємося, якщо дані старі
        self.qapp.applicationStateChanged.connect(
            lambda st: self.monitor.request_sync("повернення до вікна")
            if st == Qt.ApplicationActive and self.monitor.sync_age() > 600 else None)

        self.timer = QTimer()
        self.timer.timeout.connect(self.periodic)
        self.timer.start(60_000)

        if "--minimized" in argv and self.cfg["start_minimized"]:
            pass
        else:
            self.win.show()

    # ---- події
    def _tray_click(self, reason):
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.open_window()

    def open_window(self):
        if self.monitor.sync_age() > 600:      # дані могли застаріти — оновлюємося, поки вікно відкривається
            self.monitor.request_sync("відкриття вікна")
        self.win.show()
        self.win.setWindowState(self.win.windowState() & ~Qt.WindowMinimized)
        self.win.raise_()
        self.win.activateWindow()

    def on_data(self, d):
        ov = self.win.pages["overview"]
        ov.on_data(d)
        conn = self.win.conn
        conn.setText("● Інвертор на зв'язку\n%s · SN %s" % (self.cfg["logger_ip"], self.cfg["logger_serial"]))
        if not getattr(self, "_first", False):
            self._first = True
            self.periodic()

    def on_syncing(self, busy):
        self._syncing = busy
        self.show_sync_state()

    def on_cloud(self, ok, text):
        self._cloud_err = None if ok else text
        self.show_sync_state()
        self.periodic(all_pages=True)

    def show_sync_state(self):
        lbl = self.win.sync
        if not self.cfg["cloud_enabled"]:
            lbl.setText("")
        elif getattr(self, "_syncing", False):
            lbl.setText("⟳ Оновлюю дані з хмари…\nграфіки уточняться за хвилину")
        elif getattr(self, "_cloud_err", None):
            lbl.setText("⚠ Хмара недоступна, повторю згодом")
            lbl.setToolTip(self._cloud_err)
        else:
            try:
                t = float(self.store.get("cloud_last", 0))
            except (TypeError, ValueError):
                t = 0
            lbl.setText("☁ Хмара: оновлено о %s" % time.strftime("%H:%M", time.localtime(t)) if t else "")
            lbl.setToolTip("")

    def on_status(self, state, text):
        key = {"ok": "ok", "outage": "bad", "offline": "faint"}.get(state, "faint")
        self.tray.setIcon(icons.badge_icon(theme.T[key], "bolt_off" if state == "outage" else "bolt"))
        self.tray.setToolTip("DeyeWatch · " + text)
        self.tray_state.setText(text)
        if state == "offline":
            self.win.conn.setText("○ Немає зв'язку з інвертором\n%s" % self.cfg["logger_ip"])
        self.win.restyle()

    def on_note(self, note):
        self.toasts.show(note, self.cfg["toast_seconds"])
        if self.cfg["sound"]:
            try:
                if sys.platform.startswith("win"):
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION if note.kind in ("outage", "low_soc", "voltage")
                                         else winsound.MB_OK)
                else:
                    QApplication.beep()
            except Exception:
                pass

    def demo_note(self, kind):
        d = self.monitor.last or {"load_power": 640, "batt_soc": 76, "grid_voltage": 228, "grid_freq": 50.0}
        name = self.cfg["name"]
        now = time.time()
        if kind == "outage":
            n = M.note_outage(name, now, 5 * 3600 + 12 * 60, d, 9.6)
        elif kind == "restore":
            n = M.note_restore(name, now, 3 * 3600 + 40 * 60, d)
        elif kind == "gen":
            n = M.note_gen_start(name, now, dict(d, gen_power=d.get("gen_power") or 2400), 45 * 60)
        else:
            n = M.note_low_soc(name, 28, 30, 2 * 3600 + 5 * 60, d, 3.2)
        n.sticky = False
        self.on_note(n)

    def periodic(self, all_pages=False):
        if all_pages:     # нові дані з хмари: оновлюємо й приховані сторінки
            for k, p in self.win.pages.items():
                if k != "settings" and p is not self.win.stack.currentWidget():
                    try:
                        p.refresh()
                    except Exception:
                        pass
        page = self.win.stack.currentWidget()
        if self.win.isVisible() and page is not self.win.pages["settings"]:
            try:
                page.refresh()
            except Exception as e:
                print("refresh", e)
        if page is not self.win.pages["overview"]:
            try:
                self.win.pages["overview"].refresh()
            except Exception:
                pass

    def settings_changed(self, theme_changed):
        self.win.apply_visibility()
        self.win.brand_sub.setText(self.cfg["name"])
        if theme_changed:
            self.retheme()
        self.monitor.poke()
        self.show_sync_state()

    def retheme(self):
        theme.apply(self.cfg["theme"])
        self.qapp.setStyleSheet(theme.qss())
        for w in self.win.findChildren(Tile) + self.win.findChildren(Insight):
            w.restyle()
        self.win.restyle()
        for w in self.win.findChildren(QWidget):
            w.update()

    def quit(self):
        self.tray.hide()
        self.qapp.quit()

    def run(self):
        return self.qapp.exec()


def main():
    sys.exit(App(sys.argv).run())
