# -*- coding: utf-8 -*-
"""Власні спливаючі сповіщення: картка в куті екрана з анімацією, кольоровим акцентом і шкалою заряду."""
from PySide6.QtCore import (QEasingCurve, QPoint, QPropertyAnimation, QRectF, Qt, QTimer, Signal)
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget

from . import icons
from .messages import ACCENT, fmt_clock
from .theme import T, c
from .widgets import font

KIND_ICON = {"outage": "bolt_off", "restore": "bolt", "low_soc": "battery", "voltage": "warn",
             "offline": "wifi_off", "online": "check", "summary": "chart", "test": "bolt",
             "gen_on": "gen", "gen_off": "gen"}

W = 380


class Toast(QWidget):
    clicked = Signal()
    closed = Signal(object)

    def __init__(self, note, seconds):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.note = note
        self.accent = QColor(ACCENT.get(note.kind, "#3E63DD"))
        self.hover_close = False
        self.setMouseTracking(True)
        rows = len(note.rows)
        self.h = 92 + rows * 24 + (34 if note.soc is not None else 0)
        self.setFixedSize(W + 24, self.h + 24)    # +поле під тінь
        self.progress = 1.0
        self.total = seconds * 1000
        self.left = self.total
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        if not note.sticky and seconds > 0:
            self.timer.start(40)
        self.paused = False

    def _tick(self):
        if self.paused:
            return
        self.left -= 40
        self.progress = max(0, self.left / self.total)
        self.update()
        if self.left <= 0:
            self.dismiss()

    def enterEvent(self, e):
        self.paused = True

    def leaveEvent(self, e):
        self.paused = False
        self.hover_close = False
        self.update()

    def _close_rect(self):
        return QRectF(12 + W - 34, 12 + 12, 22, 22)

    def mouseMoveEvent(self, e):
        hc = self._close_rect().contains(e.position())
        if hc != self.hover_close:
            self.hover_close = hc
            self.update()

    def mousePressEvent(self, e):
        if not self._close_rect().contains(e.position()):
            self.clicked.emit()
        self.dismiss()

    def dismiss(self):
        self.timer.stop()
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(180)
        a.setStartValue(self.windowOpacity())
        a.setEndValue(0.0)
        a.finished.connect(self.close)
        a.start()

    def closeEvent(self, e):
        self.closed.emit(self)
        super().closeEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = self.note
        card = QRectF(12, 12, W, self.h)
        # тінь
        for i in range(10, 0, -1):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, int(5 * (11 - i) / 10 * (1.6 if T.get("dark") else 1))))
            p.drawRoundedRect(card.adjusted(-i * .9, -i * .6, i * .9, i * 1.2), 16 + i, 16 + i)
        path = QPainterPath()
        path.addRoundedRect(card, 16, 16)
        p.fillPath(path, c("surface"))
        p.setPen(QPen(c("border"), 1))
        p.drawPath(path)
        p.save()
        p.setClipPath(path)
        # м'який градієнт акценту зверху
        acc_soft = QColor(self.accent)
        acc_soft.setAlphaF(.10 if not T.get("dark") else .16)
        p.fillRect(QRectF(card.left(), card.top(), card.width(), 64), acc_soft)
        p.fillRect(QRectF(card.left(), card.top(), 4, card.height()), self.accent)
        # смужка часу, що залишився
        if self.timer.isActive():
            pc = QColor(self.accent)
            pc.setAlphaF(.55)
            p.fillRect(QRectF(card.left(), card.bottom() - 3, card.width() * self.progress, 3), pc)
        p.restore()
        # іконка
        ic = QRectF(card.left() + 18, card.top() + 14, 38, 38)
        p.setPen(Qt.NoPen)
        p.setBrush(self.accent)
        p.drawEllipse(ic)
        icons.draw(p, KIND_ICON.get(n.kind, "bolt"), ic.adjusted(9, 9, -9, -9), "#FFFFFF",
                   n.soc if n.kind == "low_soc" else None)
        # заголовок
        tx = ic.right() + 14
        p.setPen(c("text"))
        p.setFont(font(16, QFont.DemiBold))
        p.drawText(QRectF(tx, card.top() + 13, W - (tx - card.left()) - 40, 22), Qt.AlignLeft | Qt.AlignVCenter, n.title)
        p.setPen(c("muted"))
        p.setFont(font(12))
        p.drawText(QRectF(tx, card.top() + 35, W - (tx - card.left()) - 20, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(n.subtitle, Qt.ElideRight, int(W - (tx - card.left()) - 20)))
        # закрити
        cr = self._close_rect()
        if self.hover_close:
            p.setBrush(c("surface2"))
            p.drawEllipse(cr)
        p.setPen(QPen(c("faint"), 1.6, Qt.SolidLine, Qt.RoundCap))
        m = 7
        p.drawLine(cr.left() + m, cr.top() + m, cr.right() - m, cr.bottom() - m)
        p.drawLine(cr.right() - m, cr.top() + m, cr.left() + m, cr.bottom() - m)
        # рядки
        y = card.top() + 74
        for _, label, value in n.rows:
            p.setFont(font(13))
            p.setPen(c("muted"))
            p.drawText(QRectF(card.left() + 22, y, 180, 20), Qt.AlignLeft | Qt.AlignVCenter, label)
            p.setPen(c("text"))
            p.setFont(font(13, QFont.DemiBold))
            p.drawText(QRectF(card.left() + 150, y, W - 172, 20), Qt.AlignRight | Qt.AlignVCenter, str(value))
            y += 24
        # шкала заряду
        if n.soc is not None:
            y += 6
            bar = QRectF(card.left() + 22, y + 6, W - 100, 8)
            p.setPen(Qt.NoPen)
            p.setBrush(c("surface2"))
            p.drawRoundedRect(bar, 4, 4)
            key = "bad" if n.soc <= 20 else "warn" if n.soc <= 40 else "ok"
            p.setBrush(c(key))
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * max(0.02, min(1, n.soc / 100)), 8), 4, 4)
            p.setPen(c("text"))
            p.setFont(font(13, QFont.DemiBold))
            p.drawText(QRectF(bar.right() + 8, y - 2, 70, 22), Qt.AlignRight | Qt.AlignVCenter, "%d%%" % round(n.soc))
        # час події
        p.setPen(c("faint"))
        p.setFont(font(11))
        p.drawText(QRectF(card.right() - 90, card.top() + 37, 66, 16), Qt.AlignRight | Qt.AlignVCenter, fmt_clock(n.ts))


class ToastManager:
    def __init__(self, on_click):
        self.items = []
        self.on_click = on_click

    def show(self, note, seconds=12):
        t = Toast(note, seconds)
        t.clicked.connect(self.on_click)
        t.closed.connect(self._closed)
        self.items.insert(0, t)
        if len(self.items) > 4:
            self.items[-1].dismiss()
        self._layout(new=t)
        t.show()

    def _closed(self, t):
        if t in self.items:
            self.items.remove(t)
        self._layout()

    def _layout(self, new=None):
        scr = QGuiApplication.primaryScreen().availableGeometry()
        y = scr.bottom() - 8
        for t in self.items:
            y -= t.height() - 4
            target = QPoint(scr.right() - t.width() - 4, y)
            if t is new:
                t.move(target + QPoint(40, 0))
                t.setWindowOpacity(0)
                for prop, start, end in ((b"pos", target + QPoint(40, 0), target), (b"windowOpacity", 0.0, 1.0)):
                    a = QPropertyAnimation(t, prop, t)
                    a.setDuration(260)
                    a.setStartValue(start)
                    a.setEndValue(end)
                    a.setEasingCurve(QEasingCurve.OutCubic)
                    a.start()
            else:
                a = QPropertyAnimation(t, b"pos", t)
                a.setDuration(200)
                a.setEndValue(target)
                a.setEasingCurve(QEasingCurve.OutCubic)
                a.start()
