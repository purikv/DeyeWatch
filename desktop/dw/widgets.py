# -*- coding: utf-8 -*-
"""Власні віджети: картки, кільце заряду, графіки (лінійний, стовпчиковий, теплова карта)."""
import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from . import icons
from .theme import T, c


def font(px, weight=QFont.Normal):
    f = QFont()
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


class InfoDot(QLabel):
    """Кружечок «?» з поясненням при наведенні."""

    def __init__(self, text):
        super().__init__("?")
        self.setObjectName("info")
        self.setFixedSize(16, 16)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.tip = tip_html(text)
        self.setToolTip(self.tip)
        self.setToolTipDuration(30000)

    # Стандартна підказка Qt з'являється лише після ~0,7 с нерухомого курсора і тільки в активному вікні —
    # тому показуємо її самі: одразу при наведенні та при кліку.
    def _show(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QToolTip
        from PySide6.QtCore import QRect
        # без rect: інакше Qt ховає підказку, щойно курсор на піксель зміститься; ховаємо самі в leaveEvent
        QToolTip.showText(self.mapToGlobal(QPoint(self.width() // 2, self.height() + 4)), self.tip, self,
                          QRect(), 30000)

    def enterEvent(self, e):
        self._show()
        super().enterEvent(e)

    def mousePressEvent(self, e):
        self._show()

    def leaveEvent(self, e):
        from PySide6.QtWidgets import QToolTip
        QToolTip.hideText()
        super().leaveEvent(e)


def tip_html(text):
    """Підказка з переносами (QToolTip переносить рядки лише в rich text)."""
    if text.startswith("<div"):
        return text
    return "<div style='max-width:340px'>%s</div>" % text.replace("\n", "<br>")


class Card(QFrame):
    def __init__(self, title=None, parent=None, hint=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(18, 16, 18, 16)
        self.lay.setSpacing(10)
        if title:
            hl = QHBoxLayout()
            hl.setSpacing(6)
            self.title = QLabel(title)
            self.title.setObjectName("h2")
            hl.addWidget(self.title)
            if hint:
                hl.addWidget(InfoDot(hint))
            hl.addStretch()
            self.head = hl
            self.lay.addLayout(hl)


class Insight(QFrame):
    """Смуга-висновок угорі сторінки: коротко і людською мовою, що показують цифри нижче."""

    def __init__(self, icon="chart"):
        super().__init__()
        self.setObjectName("insight")
        self.icon = icon
        hl = QHBoxLayout(self)
        hl.setContentsMargins(16, 12, 16, 12)
        hl.setSpacing(12)
        self.ic = QLabel()
        self.ic.setFixedSize(22, 22)
        hl.addWidget(self.ic, 0, Qt.AlignTop)
        self.text = QLabel("")
        self.text.setObjectName("body")
        self.text.setWordWrap(True)
        self.text.setTextFormat(Qt.RichText)
        hl.addWidget(self.text, 1)
        self.restyle()

    def restyle(self):
        self.ic.setPixmap(icons.pixmap(self.icon, T["accent"], 20))

    def set(self, html):
        self.text.setText(html)
        self.setVisible(bool(html))


class Segmented(QFrame):
    changed = Signal(int)

    def __init__(self, labels, current=0):
        super().__init__()
        self.setObjectName("segbox")
        hl = QHBoxLayout(self)
        hl.setContentsMargins(3, 3, 3, 3)
        hl.setSpacing(2)
        self.btns = []
        for i, l in enumerate(labels):
            b = QPushButton(l)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setChecked(i == current)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, i=i: self._click(i))
            hl.addWidget(b)
            self.btns.append(b)
        self.current = current

    def _click(self, i):
        for j, b in enumerate(self.btns):
            b.setChecked(j == i)
        self.current = i
        self.changed.emit(i)


class Tile(QFrame):
    """Плитка показника: іконка, підпис, велике значення, підрядок."""

    def __init__(self, icon, label, color_key, hint=None):
        super().__init__()
        self.setObjectName("card")
        self.icon, self.color_key = icon, color_key
        self.level = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(2)
        top = QHBoxLayout()
        self.ic = QLabel()
        self.ic.setFixedSize(30, 30)
        top.addWidget(self.ic)
        self.lbl = QLabel(label)
        self.lbl.setObjectName("muted")
        top.addWidget(self.lbl)
        top.addStretch()
        if hint:
            top.addWidget(InfoDot(hint))
        lay.addLayout(top)
        lay.addSpacing(6)
        self.val = QLabel("—")
        self.val.setObjectName("value")
        lay.addWidget(self.val)
        self.sub = QLabel("")
        self.sub.setObjectName("faint")
        self.sub.setWordWrap(True)
        lay.addWidget(self.sub)
        self.restyle()

    def restyle(self):
        col = T[self.color_key]
        pm = icons.pixmap(self.icon, col, 18, self.level)
        self.ic.setPixmap(pm)
        self.ic.setAlignment(Qt.AlignCenter)
        self.ic.setStyleSheet("background:%s; border-radius:9px;" % c(self.color_key, .14).name(QColor.HexArgb))

    def set(self, value, sub="", color_key=None, level=None):
        self.val.setText(value)
        self.sub.setText(sub)
        changed = (color_key and color_key != self.color_key) or level != self.level
        if color_key:
            self.color_key = color_key
        self.level = level
        if changed:
            self.restyle()


class Ring(QWidget):
    """Кільце заряду батареї."""

    def __init__(self, size=120):
        super().__init__()
        self.setFixedSize(size, size)
        self.value, self.color_key, self.caption = None, "batt", ""

    def set(self, v, color_key="batt", caption=""):
        self.value, self.color_key, self.caption = v, color_key, caption
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self.width()
        w = s * .09
        r = QRectF(w / 2 + 2, w / 2 + 2, s - w - 4, s - w - 4)
        p.setPen(QPen(c("surface2"), w, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(r, 0, 360 * 16)
        if self.value is not None:
            p.setPen(QPen(c(self.color_key), w, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(r, 90 * 16, -int(360 * 16 * max(0, min(100, self.value)) / 100))
            p.setPen(c("text"))
            p.setFont(font(int(s * .24), QFont.DemiBold))
            p.drawText(QRectF(0, s * .2, s, s * .4), Qt.AlignCenter, "%d%%" % self.value)
            p.setPen(c("muted"))
            p.setFont(font(max(10, int(s * .095))))
            p.drawText(QRectF(0, s * .56, s, s * .2), Qt.AlignCenter, self.caption)


class Dot(QWidget):
    """Пульсуюча точка стану."""

    def __init__(self, size=14):
        super().__init__()
        self.setFixedSize(size * 2, size * 2)
        self.color_key = "faint"
        self.phase = 0.0
        from PySide6.QtCore import QTimer
        self.t = QTimer(self)
        self.t.timeout.connect(self._tick)
        self.t.start(50)

    def _tick(self):
        self.phase = (self.phase + 0.03) % 1.0
        self.update()

    def set(self, color_key):
        self.color_key = color_key
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self.width()
        cx = s / 2
        rr = s / 4 + self.phase * s / 4
        p.setPen(Qt.NoPen)
        p.setBrush(c(self.color_key, .35 * (1 - self.phase)))
        p.drawEllipse(QPointF(cx, cx), rr, rr)
        p.setBrush(c(self.color_key))
        p.drawEllipse(QPointF(cx, cx), s / 4, s / 4)


def nice_ticks(lo, hi, n=4):
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=raw)
    start = math.floor(lo / step) * step
    ticks = []
    v = start
    while True:
        ticks.append(round(v, 6))
        if v >= hi - step * .01:
            break
        v += step
    return ticks


class LineChart(QWidget):
    """Часовий графік: кілька серій, заливка, смуга норми, затінення відключень, наведення."""

    def __init__(self, height=220):
        super().__init__()
        self.setMinimumHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.series, self.shade, self.ref = [], [], None
        self.x0 = self.x1 = 0
        self.y_fmt = lambda v: "%g" % v
        self.y_min = self.y_max = None
        self.hover = None
        self.empty_text = "Даних поки немає — статистика накопичується"

    def set_data(self, series, x0, x1, shade=(), ref=None, y_fmt=None, y_min=None, y_max=None):
        self.series, self.x0, self.x1 = series, x0, x1
        self.shade, self.ref = list(shade), ref
        if y_fmt:
            self.y_fmt = y_fmt
        self.y_min, self.y_max = y_min, y_max
        self.update()

    def _plot_rect(self):
        return QRectF(52, 30, self.width() - 64, self.height() - 58)

    def mouseMoveEvent(self, e):
        self.hover = e.position().x()
        self.update()

    def leaveEvent(self, e):
        self.hover = None
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        R = self._plot_rect()
        vals = [v for s in self.series for _, v in s["points"] if v is not None]
        vals += [v for s in self.series for _, lo, hi in s.get("band", []) for v in (lo, hi) if v is not None]
        if not vals:
            p.setPen(c("faint"))
            p.setFont(font(13))
            p.drawText(self.rect(), Qt.AlignCenter, self.empty_text)
            return
        lo = self.y_min if self.y_min is not None else min(vals)
        hi = self.y_max if self.y_max is not None else max(vals)
        if self.ref and self.y_min is None:
            lo, hi = min(lo, self.ref[0]), max(hi, self.ref[1])
        pad = (hi - lo) * .08 or 1
        if self.y_min is None:
            lo -= pad
        if self.y_max is None:
            hi += pad
        ticks = nice_ticks(lo, hi)
        lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])
        X = lambda t: R.left() + (t - self.x0) / max(1, self.x1 - self.x0) * R.width()
        Y = lambda v: R.bottom() - (v - lo) / (hi - lo) * R.height()

        # сітка і підписи осі Y
        p.setFont(font(11))
        for t in ticks:
            y = Y(t)
            p.setPen(QPen(c("grid_line"), 1))
            p.drawLine(QPointF(R.left(), y), QPointF(R.right(), y))
            p.setPen(c("faint"))
            p.drawText(QRectF(0, y - 8, R.left() - 8, 16), Qt.AlignRight | Qt.AlignVCenter, self.y_fmt(t))
        # вісь часу
        span = self.x1 - self.x0
        step = 3600 * (1 if span <= 6 * 3600 else 3 if span <= 26 * 3600 else 12 if span <= 3 * 86400 else 24)
        off = time.localtime(self.x0).tm_gmtoff
        t = math.ceil((self.x0 + off) / step) * step - off
        while t < self.x1:
            if t > self.x0:
                x = X(t)
                lt = time.localtime(t)
                lab = time.strftime("%H:%M", lt) if step < 86400 else time.strftime("%d.%m", lt)
                p.setPen(c("faint"))
                p.drawText(QRectF(x - 30, R.bottom() + 6, 60, 16), Qt.AlignCenter, lab)
            t += step
        # затінення відключень
        for a, b in self.shade:
            xa, xb = max(R.left(), X(a)), min(R.right(), X(b))
            if xb > xa:
                p.fillRect(QRectF(xa, R.top(), xb - xa, R.height()), c("bad", .09))
        # смуга норми
        if self.ref:
            ya, yb = Y(self.ref[1]), Y(self.ref[0])
            p.fillRect(QRectF(R.left(), ya, R.width(), yb - ya), c("ok", .06))
            pen = QPen(c("ok", .5), 1, Qt.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(R.left(), ya), QPointF(R.right(), ya))
            p.drawLine(QPointF(R.left(), yb), QPointF(R.right(), yb))
        p.setClipRect(R.adjusted(-2, -2, 2, 2))
        # «розрив» = немає даних понад 15 хв (локально крок 1 хв, з хмари 5–10 хв);
        # відключення розриває лінію окремо — точками зі значенням None
        gap = max(900, (self.x1 - self.x0) / 300)
        for s in self.series:
            col = QColor(T[s["color"]])
            band = s.get("band")
            if band:
                bsegs, cur, prev_t = [], [], None
                for t, l, h in band:
                    if prev_t is not None and t - prev_t > gap and cur:
                        bsegs.append(cur)
                        cur = []
                    cur.append((t, l, h))
                    prev_t = t
                if cur:
                    bsegs.append(cur)
                bc = QColor(col)
                bc.setAlphaF(.15)
                for seg in bsegs:
                    path = QPainterPath(QPointF(X(seg[0][0]), Y(seg[0][2])))
                    for t, l, h in seg[1:]:
                        path.lineTo(X(t), Y(h))
                    for t, l, h in reversed(seg):
                        path.lineTo(X(t), Y(l))
                    path.closeSubpath()
                    p.fillPath(path, bc)
            # розбиваємо лінію на відрізки там, де немає даних
            segs, cur, prev_t = [], [], None
            for t, v in s["points"]:
                if v is None or (prev_t is not None and t - prev_t > gap):
                    if cur:
                        segs.append(cur)
                    cur = []
                if v is not None:
                    cur.append((t, v))
                prev_t = t
            if cur:
                segs.append(cur)
            for seg in segs:
                path = QPainterPath(QPointF(X(seg[0][0]), Y(seg[0][1])))
                for t, v in seg[1:]:
                    path.lineTo(X(t), Y(v))
                if s.get("fill"):
                    fp = QPainterPath(path)
                    base = Y(max(lo, 0)) if lo < 0 < hi else R.bottom()
                    fp.lineTo(X(seg[-1][0]), base)
                    fp.lineTo(X(seg[0][0]), base)
                    fp.closeSubpath()
                    g = QLinearGradient(0, R.top(), 0, R.bottom())
                    c1, c2 = QColor(col), QColor(col)
                    c1.setAlphaF(.28)
                    c2.setAlphaF(.02)
                    g.setColorAt(0, c1)
                    g.setColorAt(1, c2)
                    p.fillPath(fp, g)
                p.setPen(QPen(col, s.get("width", 2), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.setBrush(Qt.NoBrush)
                if len(seg) == 1:      # одиноке вимірювання — крапка, а не невидима лінія нульової довжини
                    p.setPen(Qt.NoPen)
                    p.setBrush(col)
                    p.drawEllipse(QPointF(X(seg[0][0]), Y(seg[0][1])), 2.5, 2.5)
                    continue
                p.drawPath(path)
        p.setClipping(False)
        # легенда
        x = R.left()
        p.setFont(font(12))
        for s in self.series:
            if not s.get("name"):
                continue
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T[s["color"]]))
            p.drawRoundedRect(QRectF(x, 9, 10, 10), 3, 3)
            p.setPen(c("muted"))
            w = p.fontMetrics().horizontalAdvance(s["name"])
            p.drawText(QPointF(x + 15, 18), s["name"])
            x += w + 32
        # наведення
        if self.hover is not None and R.left() <= self.hover <= R.right():
            t = self.x0 + (self.hover - R.left()) / R.width() * (self.x1 - self.x0)
            lines = [time.strftime("%d.%m %H:%M", time.localtime(t))]
            p.setPen(QPen(c("faint"), 1, Qt.DashLine))
            p.drawLine(QPointF(self.hover, R.top()), QPointF(self.hover, R.bottom()))
            for s in self.series:
                pts = [(pt, v) for pt, v in s["points"] if v is not None]
                if not pts:
                    continue
                pt, v = min(pts, key=lambda q: abs(q[0] - t))
                if abs(pt - t) > gap:
                    continue
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(T[s["color"]]))
                p.drawEllipse(QPointF(X(pt), Y(v)), 4, 4)
                lines.append("%s: %s" % (s.get("name") or "", s.get("fmt", self.y_fmt)(v)))
            self._tooltip(p, R, self.hover, lines)

    def _tooltip(self, p, R, x, lines):
        p.setFont(font(12))
        fm = p.fontMetrics()
        w = max(fm.horizontalAdvance(l) for l in lines) + 20
        h = len(lines) * 18 + 12
        bx = x + 12 if x + 12 + w < self.width() else x - 12 - w
        box = QRectF(bx, R.top() + 4, w, h)
        p.setPen(QPen(c("border"), 1))
        p.setBrush(c("surface"))
        p.drawRoundedRect(box, 8, 8)
        for i, l in enumerate(lines):
            p.setPen(c("text") if i else c("muted"))
            p.drawText(QPointF(box.left() + 10, box.top() + 20 + i * 18), l)


class BarChart(QWidget):
    """Стовпчики за днями; кілька серій поруч або стосом."""

    def __init__(self, height=220):
        super().__init__()
        self.setMinimumHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.labels, self.series, self.stacked = [], [], False
        self.fmt = lambda v: "%g" % v
        self.hover = None
        self.full_labels = []

    def set_data(self, labels, series, stacked=False, fmt=None, full_labels=None):
        self.labels, self.series, self.stacked = labels, series, stacked
        self.full_labels = full_labels or labels
        if fmt:
            self.fmt = fmt
        self.update()

    def mouseMoveEvent(self, e):
        self.hover = e.position().x()
        self.update()

    def leaveEvent(self, e):
        self.hover = None
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        R = QRectF(48, 30, self.width() - 60, self.height() - 58)
        n = len(self.labels)
        if not n or not self.series:
            return
        if self.stacked:
            mx = max((sum(s["values"][i] for s in self.series) for i in range(n)), default=0)
        else:
            mx = max((v for s in self.series for v in s["values"]), default=0)
        if mx <= 0:
            p.setPen(c("faint"))
            p.setFont(font(13))
            p.drawText(self.rect(), Qt.AlignCenter, "Даних поки немає — статистика накопичується")
            return
        ticks = nice_ticks(0, mx)
        hi = ticks[-1]
        Y = lambda v: R.bottom() - v / hi * R.height()
        p.setFont(font(11))
        for t in ticks:
            p.setPen(QPen(c("grid_line"), 1))
            p.drawLine(QPointF(R.left(), Y(t)), QPointF(R.right(), Y(t)))
            p.setPen(c("faint"))
            p.drawText(QRectF(0, Y(t) - 8, R.left() - 8, 16), Qt.AlignRight | Qt.AlignVCenter, self.fmt(t))
        slot = R.width() / n
        hover_i = int((self.hover - R.left()) // slot) if self.hover is not None and R.left() <= self.hover <= R.right() else None
        if hover_i is not None and 0 <= hover_i < n:
            p.fillRect(QRectF(R.left() + hover_i * slot, R.top(), slot, R.height()), c("surface2"))
        k = len(self.series)
        every = max(1, math.ceil(n / 10))
        for i in range(n):
            x0 = R.left() + i * slot
            if self.stacked:
                bw = min(28, slot * .62)
                y = R.bottom()
                for s in self.series:
                    v = s["values"][i]
                    h = v / hi * R.height()
                    if h > 0:
                        p.setPen(Qt.NoPen)
                        p.setBrush(QColor(T[s["color"]]))
                        p.drawRoundedRect(QRectF(x0 + (slot - bw) / 2, y - h, bw, h), 3, 3)
                    y -= h
            else:
                bw = min(16, slot * .7 / k)
                gx = x0 + (slot - bw * k - 2 * (k - 1)) / 2
                for j, s in enumerate(self.series):
                    v = s["values"][i]
                    h = v / hi * R.height()
                    if h > 0:
                        p.setPen(Qt.NoPen)
                        p.setBrush(QColor(T[s["color"]]))
                        p.drawRoundedRect(QRectF(gx + j * (bw + 2), Y(v), bw, h), 3, 3)
            if i % every == 0 or i == n - 1:
                p.setPen(c("faint"))
                p.drawText(QRectF(x0 - 10, R.bottom() + 6, slot + 20, 16), Qt.AlignCenter, self.labels[i])
        x = R.left()
        p.setFont(font(12))
        for s in self.series:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T[s["color"]]))
            p.drawRoundedRect(QRectF(x, 9, 10, 10), 3, 3)
            p.setPen(c("muted"))
            p.drawText(QPointF(x + 15, 18), s["name"])
            x += p.fontMetrics().horizontalAdvance(s["name"]) + 32
        if hover_i is not None and 0 <= hover_i < n:
            lines = [self.full_labels[hover_i]] + ["%s: %s" % (s["name"], self.fmt(s["values"][hover_i])) for s in self.series]
            LineChart._tooltip(self, p, R, self.hover, lines)


class Heatmap(QWidget):
    """Теплова карта 7 днів × 24 години — частка часу без світла."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(230)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.m = None
        self.hover = None

    def set_data(self, m):
        self.m = m
        self.update()

    def mouseMoveEvent(self, e):
        self.hover = e.position()
        self.update()

    def leaveEvent(self, e):
        self.hover = None
        self.update()

    def paintEvent(self, _):
        if not self.m:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
        left, top = 34, 6
        cw = (self.width() - left - 6) / 24
        ch = min(26, (self.height() - top - 26) / 7)
        p.setFont(font(11))
        hov = None
        for w in range(7):
            p.setPen(c("faint"))
            p.drawText(QRectF(0, top + w * ch, left - 6, ch), Qt.AlignRight | Qt.AlignVCenter, days[w])
            for h in range(24):
                r = QRectF(left + h * cw + 1.5, top + w * ch + 1.5, cw - 3, ch - 3)
                v = self.m[w][h]
                if v is None:
                    col = c("surface2", .5)
                elif v <= 0.001:
                    col = c("ok", .16)
                else:
                    col = c("bad", .18 + .82 * min(1, v))
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawRoundedRect(r, 4, 4)
                if self.hover is not None and r.contains(self.hover):
                    hov = (w, h, v, r)
        for h in range(0, 24, 3):
            p.setPen(c("faint"))
            p.drawText(QRectF(left + h * cw, top + 7 * ch + 4, cw * 2, 16), Qt.AlignLeft, "%02d:00" % h)
        if hov:
            w, h, v, r = hov
            txt = "%s %02d:00–%02d:00 — %s" % (days[w], h, (h + 1) % 24,
                                               "немає даних" if v is None else "без світла %d%% часу" % round(v * 100))
            LineChart._tooltip(self, p, QRectF(0, r.bottom() - 4, self.width(), 10), r.right(), [txt])


class DayStrip(QWidget):
    """Смуга останніх 24 годин: зелене — світло є, червоне — немає."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(44)
        self.ranges, self.a, self.b = [], 0, 1

    def set_data(self, a, b, outages):
        self.a, self.b, self.ranges = a, b, outages
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        R = QRectF(0, 4, self.width(), 18)
        path = QPainterPath()
        path.addRoundedRect(R, 6, 6)
        p.setClipPath(path)
        p.fillRect(R, c("ok", .55))
        X = lambda t: R.left() + (t - self.a) / (self.b - self.a) * R.width()
        for s, e in self.ranges:
            p.fillRect(QRectF(X(s), R.top(), max(2, X(e) - X(s)), R.height()), c("bad"))
        p.setClipping(False)
        p.setFont(font(11))
        p.setPen(c("faint"))
        for k in range(0, 25, 6):
            t = self.a + k * 3600
            x = X(t)
            al = Qt.AlignLeft if k == 0 else Qt.AlignRight if k == 24 else Qt.AlignHCenter
            rx = x if k == 0 else x - 60 if k == 24 else x - 30
            p.drawText(QRectF(rx, 26, 60, 16), al, "зараз" if k == 24 else time.strftime("%H:%M", time.localtime(t)))


def shadow(w, blur=24, alpha=40):
    eff = QGraphicsDropShadowEffect(w)
    eff.setBlurRadius(blur)
    eff.setOffset(0, 4)
    col = QColor(0, 0, 0, alpha)
    eff.setColor(col)
    w.setGraphicsEffect(eff)


def _pw(w):
    w = w or 0
    return "%.2f кВт" % (w / 1000) if abs(w) >= 1000 else "%d Вт" % round(w)


def _dur(sec):
    m = int(max(0, sec)) // 60
    return "%d год %02d хв" % (m // 60, m % 60) if m >= 60 else "%d хв" % m


class EnergyFlow(QWidget):
    """Схема потоків енергії: СЕС, мережа, батарея ↔ інвертор → дім. Точки рухаються в напрямку потоку
    (швидше — коли потужність більша). Немає потоку — сіра лінія; мережа без світла — червоний пунктир."""

    def __init__(self, height=300):
        super().__init__()
        self.setMinimumHeight(height)
        self.setMinimumWidth(420)
        self.d = None
        self.has_pv = True
        self.has_gen = False
        self.phase = 0.0
        from PySide6.QtCore import QTimer
        self.t = QTimer(self)
        self.t.timeout.connect(self._tick)
        self.t.start(40)

    def _tick(self):
        if self.isVisible() and self.d:
            self.phase = (self.phase + 0.004) % 1.0
            self.update()

    def set(self, d, has_pv=True, grid_ok=True, v_ok=True, has_gen=False):
        self.d = dict(d, _grid_ok=grid_ok, _v_ok=v_ok)
        self.has_pv = has_pv
        if has_gen != self.has_gen:
            self.has_gen = has_gen
            self.setMinimumHeight(380 if has_gen else 300)
            self.updateGeometry()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2 - 8
        dx, dy = min(W * .30, 230), H * .32
        R = 30
        nodes = {"pv": QPointF(cx, cy - dy), "grid": QPointF(cx - dx, cy), "home": QPointF(cx + dx, cy),
                 "batt": QPointF(cx, cy + dy)}
        if self.has_gen:     # ліворуч дві джерела: мережа зверху, генератор знизу
            nodes["grid"] = QPointF(cx - dx, cy - 66)
            nodes["gen"] = QPointF(cx - dx, cy + 66)
        d = self.d
        if not d:
            p.setPen(c("faint"))
            p.setFont(font(13))
            p.drawText(self.rect(), Qt.AlignCenter, "Чекаю на дані інвертора…")
            return
        ok = d["_grid_ok"]
        gp, bp = d.get("grid_power") or 0, d.get("batt_power") or 0
        pv, load = d.get("pv_power") or 0, d.get("load_power") or 0
        # вузол: (потужність, +1 — до інвертора / −1 — від інвертора, колір)
        flows = {"grid": (abs(gp) if ok else 0, 1 if gp > 0 else -1, "grid"),
                 "batt": (abs(bp), 1 if bp > 0 else -1, "batt"),
                 "home": (load, -1, "load")}
        if self.has_pv:
            flows["pv"] = (pv, 1, "pv")
        gw = d.get("gen_power") or 0
        if self.has_gen:
            flows["gen"] = (gw, 1, "gen")
        center = QPointF(cx, cy)
        for k, (w, sign, col) in flows.items():
            a = nodes[k]
            active = w >= 15
            if k == "grid" and not ok:
                p.setPen(QPen(c("bad", .6), 2, Qt.DashLine))
            else:
                p.setPen(QPen(c(col, .5) if active else c("border"), 3 if active else 2, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(a, center)
            if active:
                speed = 0.6 + min(2.5, max(0.0, math.log10(max(w, 10)) - 1.5))
                for i in range(3):
                    f = (self.phase * speed * 3 + i / 3) % 1.0
                    pt = center + (a - center) * f if sign < 0 else a + (center - a) * f
                    p.setPen(Qt.NoPen)
                    p.setBrush(c(col))
                    p.drawEllipse(pt, 4.5, 4.5)
        # інвертор у центрі
        p.setPen(QPen(c("border"), 1.5))
        p.setBrush(c("surface2"))
        p.drawRoundedRect(QRectF(cx - 24, cy - 24, 48, 48), 12, 12)
        icons.draw(p, "bolt", QRectF(cx - 12, cy - 12, 24, 24), c("accent"))
        soc = d.get("batt_soc")
        bcol = "bad" if soc is not None and soc <= 20 else "warn" if soc is not None and soc <= 40 else "batt"
        gcol = "bad" if not ok else ("grid" if d["_v_ok"] else "warn")
        info = {
            "pv": ("sun", "pv", "Сонячні панелі", _pw(pv), "генерують" if pv >= 15 else "зараз не генерують"),
            "grid": ("grid", gcol, "Мережа", _pw(abs(gp)) if ok else "Немає світла",
                     ("%.0f В · %s" % (d.get("grid_voltage") or 0,
                                       "беремо з мережі" if gp >= 15 else "віддаємо в мережу" if gp <= -15 else "без обміну"))
                     if ok else ("дім живиться від генератора" if d.get("gen_on") else "дім живиться від батареї")),
            "home": ("home", "load", "Дім", _pw(load), "споживає зараз"),
            "gen": ("gen", "gen", "Генератор", _pw(gw) if d.get("gen_on") or gw >= 15 else "Вимкнений",
                    "працює %s" % _dur(time.time() - d["gen_since"]) if d.get("gen_on") and d.get("gen_since")
                    else "заряджає батарею й живить дім" if gw >= 15 else "порт GEN"),
            "batt": ("battery", bcol, "Батарея %d%%" % soc if soc is not None else "Батарея", _pw(abs(bp)),
                     "розряджається" if bp >= 15 else "заряджається" if bp <= -15 else "у спокої"),
        }
        for k, (ic, col, title, val, sub_) in info.items():
            if (k == "pv" and not self.has_pv) or (k == "gen" and not self.has_gen):
                continue
            a = nodes[k]
            p.setPen(QPen(c(col), 2))
            p.setBrush(c("surface"))
            p.drawEllipse(a, R, R)
            p.setPen(Qt.NoPen)
            p.setBrush(c(col, .12))
            p.drawEllipse(a, R - 2, R - 2)
            icons.draw(p, ic, QRectF(a.x() - 13, a.y() - 13, 26, 26), c(col),
                       level=soc if ic == "battery" else None)
            if k in ("grid", "home", "gen"):  # підпис під вузлом
                box = QRectF(a.x() - 90, a.y() + R + 6, 180, 60)
                al = Qt.AlignHCenter
            else:                            # підпис праворуч від вузла
                box = QRectF(a.x() + R + 12, a.y() - 29, 200, 60)
                al = Qt.AlignLeft
            p.setPen(c("muted"))
            p.setFont(font(12))
            p.drawText(QRectF(box.left(), box.top(), box.width(), 16), al, title)
            p.setPen(c("bad") if col == "bad" else c("text"))
            p.setFont(font(17, QFont.DemiBold))
            p.drawText(QRectF(box.left(), box.top() + 16, box.width(), 24), al, val)
            p.setPen(c("faint"))
            p.setFont(font(11))
            p.drawText(QRectF(box.left(), box.top() + 40, box.width(), 16), al, sub_)
