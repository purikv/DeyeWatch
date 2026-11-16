# -*- coding: utf-8 -*-
"""Векторні іконки, намальовані QPainter (однаково чітко в будь-якому масштабі та темі)."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _pen(color, w):
    p = QPen(QColor(color), w)
    p.setCapStyle(Qt.RoundCap)
    p.setJoinStyle(Qt.RoundJoin)
    return p


def bolt_path(r: QRectF):
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    pts = [(0.58, 0.04), (0.18, 0.56), (0.47, 0.56), (0.40, 0.96), (0.82, 0.42), (0.53, 0.42), (0.58, 0.04)]
    p = QPainterPath(QPointF(x + pts[0][0] * w, y + pts[0][1] * h))
    for px, py in pts[1:]:
        p.lineTo(x + px * w, y + py * h)
    return p


def draw(p: QPainter, name, r: QRectF, color, level=None):
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    s = min(r.width(), r.height())
    lw = max(1.4, s * 0.085)
    col = QColor(color)
    if name in ("bolt", "bolt_off"):
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawPath(bolt_path(r.adjusted(s * .06, s * .02, -s * .06, -s * .02)))
        if name == "bolt_off":
            p.setPen(_pen(col, lw * 1.1))
            p.drawLine(QPointF(r.left() + s * .12, r.top() + s * .1), QPointF(r.right() - s * .12, r.bottom() - s * .1))
    elif name == "sun":
        p.setPen(_pen(col, lw))
        cx, cy = r.center().x(), r.center().y()
        p.drawEllipse(QPointF(cx, cy), s * .2, s * .2)
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(QPointF(cx + math.cos(a) * s * .33, cy + math.sin(a) * s * .33),
                       QPointF(cx + math.cos(a) * s * .45, cy + math.sin(a) * s * .45))
    elif name == "home":
        p.setPen(_pen(col, lw))
        x, y = r.x(), r.y()
        path = QPainterPath(QPointF(x + s * .12, y + s * .48))
        path.lineTo(x + s * .5, y + s * .14)
        path.lineTo(x + s * .88, y + s * .48)
        p.drawPath(path)
        p.drawRoundedRect(QRectF(x + s * .22, y + s * .42, s * .56, s * .44), s * .05, s * .05)
    elif name == "battery":
        p.setPen(_pen(col, lw))
        body = QRectF(r.x() + s * .2, r.y() + s * .16, s * .6, s * .74)
        p.drawRoundedRect(body, s * .09, s * .09)
        p.drawLine(QPointF(r.center().x() - s * .1, r.y() + s * .08), QPointF(r.center().x() + s * .1, r.y() + s * .08))
        if level is not None:
            inner = body.adjusted(s * .1, s * .1, -s * .1, -s * .1)
            hgt = inner.height() * max(0, min(1, level / 100))
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(inner.x(), inner.bottom() - hgt, inner.width(), hgt), s * .03, s * .03)
    elif name == "grid":   # опора ЛЕП
        p.setPen(_pen(col, lw))
        x, y = r.x(), r.y()
        p.drawLine(QPointF(x + s * .5, y + s * .1), QPointF(x + s * .25, y + s * .9))
        p.drawLine(QPointF(x + s * .5, y + s * .1), QPointF(x + s * .75, y + s * .9))
        p.drawLine(QPointF(x + s * .2, y + s * .3), QPointF(x + s * .8, y + s * .3))
        p.drawLine(QPointF(x + s * .3, y + s * .55), QPointF(x + s * .7, y + s * .55))
    elif name == "wave":
        p.setPen(_pen(col, lw))
        path = QPainterPath()
        for i in range(41):
            t = i / 40
            px = r.x() + s * (.1 + .8 * t)
            py = r.center().y() - math.sin(t * 2 * math.pi) * s * .25
            path.moveTo(px, py) if i == 0 else path.lineTo(px, py)
        p.drawPath(path)
    elif name == "warn":
        p.setPen(_pen(col, lw))
        x, y = r.x(), r.y()
        path = QPainterPath(QPointF(x + s * .5, y + s * .1))
        path.lineTo(x + s * .92, y + s * .86)
        path.lineTo(x + s * .08, y + s * .86)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(x + s * .5, y + s * .38), QPointF(x + s * .5, y + s * .6))
        p.drawPoint(QPointF(x + s * .5, y + s * .73))
    elif name == "wifi_off":
        p.setPen(_pen(col, lw))
        cx, by = r.center().x(), r.y() + s * .78
        for k in (.62, .42, .22):
            p.drawArc(QRectF(cx - s * k / 1.2, by - s * k / 1.2, s * k / .6, s * k / .6), 45 * 16, 90 * 16)
        p.drawLine(QPointF(r.x() + s * .15, r.y() + s * .15), QPointF(r.right() - s * .15, r.bottom() - s * .15))
    elif name == "check":
        p.setPen(_pen(col, lw * 1.2))
        x, y = r.x(), r.y()
        p.drawPolyline([QPointF(x + s * .2, y + s * .52), QPointF(x + s * .42, y + s * .74), QPointF(x + s * .82, y + s * .3)])
    elif name == "chart":
        p.setPen(_pen(col, lw))
        x, y = r.x(), r.y()
        for i, hh in enumerate((.35, .6, .45, .75)):
            px = x + s * (.18 + i * .2)
            p.drawLine(QPointF(px, y + s * .86), QPointF(px, y + s * (.86 - hh)))
    elif name == "gear":
        p.setPen(_pen(col, lw))
        cx, cy = r.center().x(), r.center().y()
        p.drawEllipse(QPointF(cx, cy), s * .14, s * .14)
        path = QPainterPath()
        n = 8
        for i in range(n * 2 + 1):
            a = i * math.pi / n
            rr = s * (.42 if i % 2 == 0 else .32)
            pt = QPointF(cx + math.cos(a) * rr, cy + math.sin(a) * rr)
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        p.drawPath(path)
    elif name == "gen":    # генератор: корпус на ніжках з блискавкою
        p.setPen(_pen(col, lw))
        x, y = r.x(), r.y()
        body = QRectF(x + s * .1, y + s * .22, s * .8, s * .56)
        p.drawRoundedRect(body, s * .1, s * .1)
        p.drawLine(QPointF(x + s * .25, y + s * .78), QPointF(x + s * .25, y + s * .9))
        p.drawLine(QPointF(x + s * .75, y + s * .78), QPointF(x + s * .75, y + s * .9))
        p.drawLine(QPointF(x + s * .35, y + s * .1), QPointF(x + s * .65, y + s * .1))
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawPath(bolt_path(QRectF(x + s * .36, y + s * .28, s * .28, s * .44)))
    elif name == "clock":
        p.setPen(_pen(col, lw))
        cx, cy = r.center().x(), r.center().y()
        p.drawEllipse(QPointF(cx, cy), s * .4, s * .4)
        p.drawPolyline([QPointF(cx, cy - s * .22), QPointF(cx, cy), QPointF(cx + s * .16, cy + s * .1)])
    elif name == "overview":
        p.setPen(_pen(col, lw))
        x, y = r.x(), r.y()
        for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
            p.drawRoundedRect(QRectF(x + s * (.14 + dx * .38), y + s * (.14 + dy * .38), s * .3, s * .3), s * .06, s * .06)
    p.restore()


def pixmap(name, color, size=24, level=None, dpr=2.0):
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    draw(p, name, QRectF(0, 0, size, size), color, level)
    p.end()
    return pm


def badge_icon(color, name="bolt", size=64):
    """Кругла іконка (для трею / вікна): кольорове коло з білою блискавкою."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(QRectF(2, 2, size - 4, size - 4))
    draw(p, name, QRectF(size * .22, size * .2, size * .56, size * .6), "#FFFFFF")
    p.end()
    return QIcon(pm)
