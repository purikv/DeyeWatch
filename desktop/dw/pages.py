# -*- coding: utf-8 -*-
"""Сторінки головного вікна: Огляд, Відключення, Мережа, Енергія, Батарея."""
import datetime as dt
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QSizePolicy, QAbstractItemView, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import messages as M
from .core import RUNNING_STATUS
from .theme import T
from .widgets import (BarChart, Card, DayStrip, Dot, EnergyFlow, Heatmap, Insight, LineChart, Ring, Segmented, Tile,
                      font, tip_html)


def kwh(v):
    return "%.1f кВт·год" % (v or 0)


def pw(v):
    return M.fmt_power(v)


def plural(n, one, few, many):
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def legend(color_key, text):
    """Кольоровий квадратик + підпис для легенди."""
    l = QLabel("<span style='color:%s'>■</span>&nbsp;%s" % (T[color_key], text))
    l.setObjectName("legend")
    l.setTextFormat(Qt.RichText)
    return l


WD_FULL = ["понеділок", "вівторок", "середу", "четвер", "п'ятницю", "суботу", "неділю"]


class Page(QScrollArea):
    title = ""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWidgetResizable(True)
        self.body = QWidget()
        self.body.setObjectName("root")
        self.setWidget(self.body)
        self.v = QVBoxLayout(self.body)
        self.v.setContentsMargins(28, 24, 28, 28)
        self.v.setSpacing(16)
        head = QHBoxLayout()
        self.h1 = QLabel(self.title)
        self.h1.setObjectName("h1")
        head.addWidget(self.h1)
        head.addStretch()
        self.head = head
        self.v.addLayout(head)

    def refresh(self):
        pass

    def on_data(self, d):
        pass

    def table(self, headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.NoSelection)
        t.setFocusPolicy(Qt.NoFocus)
        t.setShowGrid(False)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.horizontalHeader().setDefaultAlignment(Qt.AlignLeft)
        return t

    @staticmethod
    def fill(t, rows, max_h=360):
        t.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, v in enumerate(r):
                it = QTableWidgetItem(str(v))
                t.setItem(i, j, it)
        t.setFixedHeight(min(max_h, 34 + 36 * max(1, len(rows))))


# ---------------------------------------------------------------------------
class Overview(Page):
    title = "Огляд"

    def __init__(self, app):
        super().__init__(app)
        self.onboard = None
        self.build_onboarding()

        # Головна картка стану
        hero = Card()
        hl = QHBoxLayout()
        self.dot = Dot(14)
        hl.addWidget(self.dot, 0, Qt.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.state = QLabel("Підключення…")
        self.state.setObjectName("hero")
        self.state_sub = QLabel("Отримую дані з інвертора")
        self.state_sub.setObjectName("heroSub")
        col.addWidget(self.state)
        col.addWidget(self.state_sub)
        hl.addLayout(col)
        hl.addStretch()
        side = QVBoxLayout()
        side.setSpacing(2)
        self.inv_state = QLabel("")
        self.inv_state.setObjectName("faint")
        self.inv_state.setAlignment(Qt.AlignRight)
        self.inv_state.setToolTip(tip_html("Режим роботи інвертора, як його повідомляє сам інвертор. "
                                           "«Нормальна робота» — усе гаразд."))
        self.updated = QLabel("")
        self.updated.setObjectName("faint")
        self.updated.setAlignment(Qt.AlignRight)
        self.updated.setToolTip(tip_html("Час останніх даних з інвертора. Програма опитує його кожні "
                                         "%d с." % app.cfg["poll_interval_sec"]))
        side.addWidget(self.inv_state)
        side.addWidget(self.updated)
        side.addStretch()
        hl.addLayout(side)
        col.addStretch()
        hero.lay.addLayout(hl)
        hero.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        caph = QHBoxLayout()
        cap = QLabel("Останні 24 години")
        cap.setObjectName("faint")
        caph.addWidget(cap)
        caph.addStretch()
        caph.addWidget(legend("ok", "світло було"))
        caph.addSpacing(10)
        caph.addWidget(legend("bad", "світла не було"))
        hero.lay.addLayout(caph)
        self.strip = DayStrip()
        hero.lay.addWidget(self.strip)
        self.v.addWidget(hero)

        self.insight = Insight("clock")
        self.v.addWidget(self.insight)

        # Схема потоків + батарея
        row = QHBoxLayout()
        row.setSpacing(14)
        fc = Card("Куди йде енергія зараз",
                  hint="Схема показує, звідки зараз береться електрика і куди вона йде.\n"
                       "• Точки рухаються в напрямку потоку — що швидше, то більша потужність.\n"
                       "• Сіра лінія — потоку немає.\n"
                       "• Червоний пунктир до мережі — світла немає, дім живиться від батареї та сонця.\n"
                       "• У центрі — інвертор, який усім цим керує.")
        self.flow = EnergyFlow(380 if app.cfg["has_gen"] else 300)
        self.flow.has_gen = app.cfg["has_gen"]
        fc.lay.addWidget(self.flow)
        row.addWidget(fc, 3)

        bc = Card("Батарея", hint="Заряд батареї та прогноз, на скільки його вистачить при поточному "
                                  "споживанні — до мінімального заряду, після якого інвертор вимикає живлення "
                                  "(налаштовується в «Налаштуваннях»).")
        bl = QVBoxLayout()
        bl.setSpacing(6)
        self.ring = Ring(132)
        bl.addWidget(self.ring, 0, Qt.AlignHCenter)
        bl.addSpacing(6)
        self.b_power = QLabel("—")
        self.b_power.setObjectName("value2")
        self.b_power.setAlignment(Qt.AlignHCenter)
        bl.addWidget(self.b_power)
        self.b_auto = QLabel("")
        self.b_auto.setObjectName("body")
        self.b_auto.setAlignment(Qt.AlignHCenter)
        self.b_auto.setWordWrap(True)
        bl.addWidget(self.b_auto)
        self.b_misc = QLabel("")
        self.b_misc.setObjectName("faint")
        self.b_misc.setAlignment(Qt.AlignHCenter)
        self.b_misc.setWordWrap(True)
        bl.addWidget(self.b_misc)
        bl.addStretch()
        bc.lay.addLayout(bl)
        row.addWidget(bc, 2)
        self.v.addLayout(row)

        ch = Card("Потужність за 24 години",
                  hint="Скільки енергії споживав дім, давали сонячні панелі, генератор та бралося з мережі "
                       "протягом доби.\n"
                       "Наведіть мишу на графік, щоб побачити точні значення. Червоні ділянки — відключення.")
        self.chart = LineChart(240)
        ch.lay.addWidget(self.chart)
        self.v.addWidget(ch)
        self.v.addStretch()

    # ---- «З чого почати» (перший запуск)
    def build_onboarding(self):
        if self.app.cfg.get("onboarding_done"):
            return
        box = QFrame()
        box.setObjectName("onboard")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)
        top = QHBoxLayout()
        t = QLabel("Ласкаво просимо до DeyeWatch")
        t.setObjectName("h2")
        top.addWidget(t)
        top.addStretch()
        close = QPushButton("Зрозуміло, сховати")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.hide_onboarding)
        top.addWidget(close)
        lay.addLayout(top)
        intro = QLabel("Програма стежить за інвертором і одразу повідомляє, коли зникає чи з'являється світло. "
                       "Кілька кроків, щоб усе працювало як слід:")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.steps = QVBoxLayout()
        self.steps.setSpacing(6)
        lay.addLayout(self.steps)
        self.v.addWidget(box)
        self.onboard = box
        self.fill_onboarding()

    def fill_onboarding(self):
        if not self.onboard:
            return
        cfg, mon = self.app.cfg, self.app.monitor
        sig = (mon.last is not None, cfg.get("_battery_checked"), cfg["autostart"], cfg["cloud_enabled"],
               cfg["telegram_enabled"], cfg["logger_ip"], cfg["battery_kwh"], cfg["battery_min_soc"])
        if sig == getattr(self, "_ob_sig", None):
            return
        self._ob_sig = sig
        while self.steps.count():
            it = self.steps.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        steps = [
            (mon.last is not None, "Підключення до інвертора",
             "Інвертор на зв'язку (%s)." % cfg["logger_ip"] if mon.last is not None else
             "Ще немає зв'язку. У «Налаштуваннях» натисніть «Знайти автоматично» — програма сама знайде WiFi-стік.",
             "connection"),
            (bool(cfg.get("_battery_checked")), "Перевірте батарею",
             "Ємність %.0f кВт·год, мінімальний заряд %d%%. Від цього залежить прогноз «батареї вистачить на…»."
             % (cfg["battery_kwh"], cfg["battery_min_soc"]), "battery"),
            (bool(cfg["autostart"]), "Автозапуск",
             "Увімкніть «Запускати разом із системою», щоб не пропустити відключення після перезавантаження.",
             "ui"),
            (bool(cfg["cloud_enabled"]), "Deye Cloud (необов'язково)",
             "Догружає статистику за час, коли комп'ютер був вимкнений або спав.", "cloud"),
            (bool(cfg["telegram_enabled"]), "Telegram (необов'язково)",
             "Сповіщення на телефон — вам і рідним, навіть коли ви не за комп'ютером.", "telegram"),
        ]
        for done, title, text, section in steps:
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 2, 0, 2)
            h.setSpacing(10)
            mark = QLabel("✓" if done else "○")
            mark.setFixedWidth(18)
            mark.setStyleSheet("color:%s; font-size:15px; font-weight:600;" % (T["ok"] if done else T["faint"]))
            h.addWidget(mark, 0, Qt.AlignTop)
            lbl = QLabel("<b>%s</b> — %s" % (title, text))
            lbl.setWordWrap(True)
            lbl.setTextFormat(Qt.RichText)
            if done:
                lbl.setObjectName("muted")
            h.addWidget(lbl, 1)
            if not done:
                b = QPushButton("Налаштувати")
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, s=section: self.app.win.open_settings(s))
                h.addWidget(b, 0, Qt.AlignTop)
            self.steps.addWidget(w)

    def hide_onboarding(self):
        self.app.cfg["onboarding_done"] = True
        self.app.cfg.save()
        if self.onboard:
            self.onboard.hide()
            self.onboard.deleteLater()
            self.onboard = None

    def on_data(self, d):
        cfg = self.app.cfg
        now = time.time()
        first = getattr(self, "_had_data", False) is False
        self._had_data = True
        if d.get("grid_ok"):
            self.dot.set("ok")
            self.state.setText("Світло є")
        else:
            self.dot.set("bad")
            self.state.setText("Світла немає")
        sub = "%s %s · з %s, %s" % ("вже" if not d.get("grid_ok") else "уже", M.fmt_dur(now - d["since"]),
                                    M.fmt_clock(d["since"]), M.fmt_date(d["since"]))
        if d.get("gen_on"):
            sub += " · працює генератор"
        self.state_sub.setText(sub)
        self.inv_state.setText("Інвертор: %s" % RUNNING_STATUS.get(d["running_status"], "?"))
        self.updated.setText("Оновлено о %s" % time.strftime("%H:%M:%S", time.localtime(d["ts"])))
        v_ok = cfg["v_low"] <= d["grid_voltage"] <= cfg["v_high"]
        self.flow.set(d, cfg["has_pv"], bool(d.get("grid_ok")), v_ok, cfg["has_gen"])
        if d.get("gen_on") != getattr(self, "_gen_shown", None):
            self._gen_shown = d.get("gen_on")
            self.update_insight()

        soc = d["batt_soc"]
        key = "bad" if soc <= 20 else "warn" if soc <= 40 else "batt"
        bp = d["batt_power"]
        self.ring.set(soc, key, "розряд" if bp > 20 else "заряд" if bp < -20 else "спокій")
        self.b_power.setText(("Розряд " if bp > 20 else "Заряд " if bp < -20 else "") + pw(abs(bp)))
        a = d.get("autonomy_h")
        if a is not None:
            self.b_auto.setText("Вистачить %s\nдо %d%% при поточному споживанні" % (M.autonomy_text(a),
                                                                                   cfg["battery_min_soc"]))
        elif bp < -20:
            self.b_auto.setText("Батарея заряджається")
        else:
            self.b_auto.setText("")
        self.b_misc.setText("%.2f В · батарея %.1f °C · інвертор %.0f °C" % (d["batt_voltage"], d["batt_temp"],
                                                                         d["dc_temp"]))
        if first:
            self.fill_onboarding()
            self.update_insight()

    def update_insight(self):
        """Підсумок дня одним реченням."""
        st = self.app.store
        now = time.time()
        midnight = time.mktime(dt.date.today().timetuple())
        offs = st.outages_between(midnight, now)
        tot = sum(e - s for s, e, _, _ in offs)
        if not self.app.cfg["stats_enabled"]:
            self.insight.set("")
            return
        if offs:
            txt = "Сьогодні світло вимикали <b>%d %s</b>, без світла — <b>%s</b>." % (
                len(offs), plural(len(offs), "раз", "рази", "разів"), M.fmt_dur(tot))
        else:
            txt = "Сьогодні відключень не було."
        d = self.app.monitor.last
        cfg = self.app.cfg
        if d and d.get("gen_on"):
            txt += " Зараз працює <b>генератор</b> — %s, уже %s." % (pw(d.get("gen_power")),
                                                                   M.fmt_dur(now - d["gen_since"]))
        elif cfg["has_gen"]:
            h, k = st.gen_stats(midnight, cfg["gen_min_power"])
            if h >= 1 / 60:
                txt += " Генератор сьогодні працював <b>%s</b> (%.1f кВт·год)." % (M.fmt_dur(h * 3600), k)
        if d and d.get("gen_on"):
            pass
        elif d and d.get("grid_ok") is False and d.get("autonomy_h") is not None:
            txt += " Батареї вистачить ще <b>%s</b>." % M.autonomy_text(d["autonomy_h"])
        elif d and self.app.cfg["has_pv"] and d.get("day_pv"):
            txt += " Сонячні панелі виробили <b>%s</b>." % kwh(d["day_pv"])
        self.insight.set(txt)

    def refresh(self):
        st = self.app.store
        now = time.time()
        a = now - 86400
        self.strip.set_data(a, now, [(s, e) for s, e, _, _ in st.outages_between(a, now)])
        rows = st.series(a, ["load_p", "pv_p", "grid_p", "gen_p"])
        series = [{"name": "Споживання", "color": "load", "points": [(r[0], r[1]) for r in rows], "fill": True}]
        if self.app.cfg["has_pv"]:
            series.append({"name": "СЕС", "color": "pv", "points": [(r[0], r[2]) for r in rows], "fill": True})
        series.append({"name": "Мережа", "color": "grid", "points": [(r[0], r[3]) for r in rows]})
        if self.app.cfg["has_gen"]:
            series.append({"name": "Генератор", "color": "gen", "points": [(r[0], r[4]) for r in rows]})
        self.chart.set_data(series, a, now, [(s, e) for s, e, _, _ in st.outages_between(a, now)],
                            y_fmt=lambda v: ("%.1fк" % (v / 1000)) if abs(v) >= 1000 else "%d" % v)
        for s in self.chart.series:
            s["fmt"] = pw
        self.update_insight()
        self.fill_onboarding()


# ---------------------------------------------------------------------------
class Outages(Page):
    title = "Відключення"
    RANGES = [7, 30, 90]

    def __init__(self, app):
        super().__init__(app)
        self.seg = Segmented(["7 днів", "30 днів", "90 днів"], 1)
        self.seg.changed.connect(lambda _: self.refresh())
        self.head.addWidget(self.seg)
        g = QGridLayout()
        g.setSpacing(14)
        self.insight = Insight("bolt_off")
        self.v.addWidget(self.insight)
        self.k_cnt = Tile("bolt_off", "Відключень", "bad", "Скільки разів зникало світло за вибраний період. "
                          "Короткі «блимання» до 2 хвилин не рахуються.")
        self.k_tot = Tile("clock", "Без світла всього", "warn", "Сумарний час без світла за період і яка це частка "
                          "від усього часу.")
        self.k_long = Tile("clock", "Найдовше", "orange", "Найдовше безперервне відключення за період.")
        self.k_avg = Tile("chart", "Середня тривалість", "accent", "Скільки в середньому триває одне відключення.")
        for i, w in enumerate((self.k_cnt, self.k_tot, self.k_long, self.k_avg)):
            g.addWidget(w, 0, i)
        self.v.addLayout(g)
        c1 = Card("Годин без світла по днях", hint="Кожен стовпчик — один день: скільки годин того дня не було світла. "
                  "Наведіть мишу, щоб побачити дату і точне значення.")
        self.bars = BarChart(230)
        c1.lay.addWidget(self.bars)
        self.v.addWidget(c1)
        c2 = Card("Коли найчастіше вимикають", hint="Рядки — дні тижня, стовпці — години доби. "
                  "Що червоніша клітинка, то частіше в цей час не було світла. "
                  "Допомагає побачити графік відключень і спланувати справи.")
        self.heat_sub = QLabel("")
        self.heat_sub.setObjectName("faint")
        c2.lay.addWidget(self.heat_sub)
        self.heat = Heatmap()
        c2.lay.addWidget(self.heat)
        self.v.addWidget(c2)
        c3 = Card("Останні відключення", hint="Повний список відключень: коли почалося, коли закінчилося і скільки "
                  "тривало. Дані за час, коли програма не працювала, догружаються з Deye Cloud (точність ~5 хв).")
        self.tbl = self.table(["Дата", "Почалося", "Закінчилося", "Тривалість"])
        c3.lay.addWidget(self.tbl)
        self.v.addWidget(c3)
        self.v.addStretch()

    def refresh(self):
        st = self.app.store
        days = self.RANGES[self.seg.current]
        s = st.outage_stats(days)
        self.k_cnt.set(str(s["count"]), "за %d днів · %.1f на добу" % (days, s["count"] / days))
        self.k_tot.set(M.fmt_dur(s["total"]), "%.0f%% часу без світла" % (s["share"] * 100))
        self.k_long.set(M.fmt_dur(s["longest"]) if s["count"] else "—", "")
        self.k_avg.set(M.fmt_dur(s["avg"]) if s["count"] else "—", "")
        per = st.outage_hours_per_day(days)
        self.bars.set_data([d.strftime("%d.%m") for d, _ in per],
                           [{"name": "Без світла, год", "color": "bad", "values": [h for _, h in per]}],
                           fmt=lambda v: "%.1f год" % v if v % 1 else "%d год" % v,
                           full_labels=["%s, %d %s" % (M.WDAYS[d.weekday()], d.day, M.MONTHS[d.month - 1]) for d, _ in per])
        self.heat.set_data(st.outage_heatmap(days))
        self.heat_sub.setText("Частка часу без світла за днями тижня та годинами, останні %d днів. "
                              "Що червоніше — то частіше." % days)
        rows = []
        for s0, e0 in st.recent_outages(40):
            rows.append((M.fmt_date(s0), M.fmt_clock(s0), M.fmt_clock(e0) if e0 else "триває",
                         M.fmt_dur((e0 or time.time()) - s0)))
        self.fill(self.tbl, rows or [("Відключень ще не зафіксовано", "", "", "")], 480)
        txt = self.outage_insight(days, s, st.outage_heatmap(days))
        cfg = self.app.cfg
        if cfg["has_gen"]:
            h, k = st.gen_stats(time.time() - days * 86400, cfg["gen_min_power"])
            if h >= 1 / 60:
                txt += " Генератор працював <b>%s</b> і дав <b>%.1f кВт·год</b>." % (M.fmt_dur(h * 3600), k)
        self.insight.set(txt)

    @staticmethod
    def outage_insight(days, s, heat):
        if not s["count"]:
            return "За останні %d днів відключень не було." % days
        txt = "За %d днів світло вимикали <b>%d %s</b> — разом <b>%s</b> без світла (%.0f%% часу)." % (
            days, s["count"], plural(s["count"], "раз", "рази", "разів"), M.fmt_dur(s["total"]), s["share"] * 100)
        # найгірший проміжок у тепловій карті: день тижня + 3 години поспіль
        best, bw, bh = -1, 0, 0
        for w in range(7):
            for h in range(22):
                vals = [heat[w][h + k] for k in range(3) if heat[w][h + k] is not None]
                if len(vals) == 3 and sum(vals) > best:
                    best, bw, bh = sum(vals), w, h
        if best > 0.9:      # у середньому понад 30 % часу в ці години
            txt += " Найчастіше світла немає в <b>%s з %02d:00 до %02d:00</b>." % (WD_FULL[bw], bh, bh + 3)
        return txt


# ---------------------------------------------------------------------------
class Grid(Page):
    title = "Якість мережі"

    def __init__(self, app):
        super().__init__(app)
        self.seg = Segmented(["24 години", "7 днів", "30 днів"], 0)
        self.seg.changed.connect(lambda _: self.refresh())
        self.head.addWidget(self.seg)
        g = QGridLayout()
        g.setSpacing(14)
        self.insight = Insight("wave")
        self.v.addWidget(self.insight)
        self.k_min = Tile("wave", "Мінімум", "accent", "Найнижча напруга, поки світло було. Нижче 207 В деякі "
                          "прилади (холодильник, насос, котел) можуть працювати погано.")
        self.k_max = Tile("wave", "Максимум", "orange", "Найвища напруга за період. Вище 253 В — ризик для техніки.")
        self.k_avg = Tile("wave", "Середня", "ok", "Середня напруга і діапазон частоти. Норма: 230 В, 50 Гц.")
        self.k_bad = Tile("warn", "Поза нормою", "warn", "Скільки часу напруга виходила за межі норми "
                          "(межі задаються в «Налаштуваннях»).")
        for i, w in enumerate((self.k_min, self.k_max, self.k_avg, self.k_bad)):
            g.addWidget(w, 0, i)
        self.v.addLayout(g)
        c1 = Card("Напруга мережі", hint="Як змінювалась напруга в розетці. Між пунктирними лініями — норма. "
                  "Розриви лінії — час, коли світла не було або даних немає.")
        self.vsub = QLabel("")
        self.vsub.setObjectName("faint")
        c1.lay.addWidget(self.vsub)
        self.vchart = LineChart(250)
        c1.lay.addWidget(self.vchart)
        self.v.addWidget(c1)
        c2 = Card("Частота", hint="Частота струму в мережі. Норма — 50 Гц; помітні відхилення означають, "
                  "що енергосистема перевантажена.")
        self.fchart = LineChart(180)
        c2.lay.addWidget(self.fchart)
        self.v.addWidget(c2)
        c3 = Card("Події", hint="Випадки, коли напруга довго була поза нормою, і втрати зв'язку з інвертором.")
        self.tbl = self.table(["Час", "Подія", "Значення"])
        c3.lay.addWidget(self.tbl)
        self.v.addWidget(c3)
        self.v.addStretch()

    def refresh(self):
        st, cfg = self.app.store, self.app.cfg
        span = [86400, 7 * 86400, 30 * 86400][self.seg.current]
        now = time.time()
        a = now - span
        q = st.grid_quality(a, cfg["v_low"], cfg["v_high"])
        self.k_min.set("%.0f В" % q["vmin"] if q["vmin"] else "—", "найнижча зафіксована")
        self.k_max.set("%.0f В" % q["vmax"] if q["vmax"] else "—", "найвища зафіксована")
        self.k_avg.set("%.1f В" % q["vavg"] if q["vavg"] else "—",
                       "частота %.2f–%.2f Гц" % (q["fmin"], q["fmax"]) if q["fmin"] else "")
        bad = q["low_min"] + q["high_min"]
        self.k_bad.set(M.fmt_dur(bad * 60) if q["minutes"] else "—",
                       "занижена %s · завищена %s" % (M.fmt_dur(q["low_min"] * 60), M.fmt_dur(q["high_min"] * 60)),
                       "warn" if bad else "ok")
        rows = st.series(a, ["v_avg", "v_min", "v_max", "freq", "grid_ok"])
        step = max(1, len(rows) // 1500)
        rows = rows[::step]
        pts = [(r[0], r[1] if r[5] else None) for r in rows]
        band = [(r[0], r[2], r[3]) for r in rows if r[5] and r[2] is not None and r[3] is not None]
        self.vsub.setText("Пунктир — межі норми %d–%d В. Лінія — середнє за хвилину, тінь — мінімум і максимум. "
                          "Червоні ділянки — відключення." % (cfg["v_low"], cfg["v_high"]))
        if q["minutes"]:
            good = max(0.0, 1 - bad / q["minutes"]) * 100
            verdict = ("напруга стабільна" if good >= 99 else "напруга здебільшого в нормі" if good >= 95
                       else "напруга часто виходить за норму")
            self.insight.set("Поки світло було, <b>%s</b>: у межах %d–%d В — <b>%.0f%%</b> часу, "
                             "середня <b>%.0f В</b>." % (verdict, cfg["v_low"], cfg["v_high"], good, q["vavg"]))
        else:
            self.insight.set("За цей період немає вимірювань напруги — можливо, весь час не було світла.")
        sh = [(s, e) for s, e, _, _ in st.outages_between(a, now)]
        self.vchart.set_data([{"name": "Напруга", "color": "grid", "points": pts, "band": band}], a, now, sh,
                             ref=(cfg["v_low"], cfg["v_high"]), y_fmt=lambda v: "%d В" % v)
        self.fchart.set_data([{"name": "Частота", "color": "accent", "points": [(r[0], r[4] if r[5] else None) for r in rows]}],
                             a, now, sh, ref=(49.8, 50.2), y_fmt=lambda v: "%.2f" % v)
        for s in self.fchart.series:
            s["fmt"] = lambda v: "%.2f Гц" % v
        for s in self.vchart.series:
            s["fmt"] = lambda v: "%.1f В" % v
        names = {"v_low": "Занижена напруга", "v_high": "Завищена напруга", "offline": "Втрата зв'язку з інвертором",
                 "online": "Зв'язок відновлено"}
        ev = st.events(list(names), 40)
        self.fill(self.tbl, [("%s %s" % (M.fmt_date(t), M.fmt_clock(t)), names.get(k, k),
                              "%.0f В" % v if k.startswith("v_") else "") for t, k, v, _ in ev]
                  or [("Подій немає", "", "")])


# ---------------------------------------------------------------------------
class Energy(Page):
    title = "Енергія"

    def __init__(self, app):
        super().__init__(app)
        self.seg = Segmented(["7 днів", "30 днів", "90 днів"], 1)
        self.seg.changed.connect(lambda _: self.refresh())
        self.head.addWidget(self.seg)
        g = QGridLayout()
        g.setSpacing(14)
        self.insight = Insight("sun")
        self.v.addWidget(self.insight)
        self.k_pv = Tile("sun", "Вироблено СЕС", "pv", "Скільки енергії дали сонячні панелі за період.")
        self.k_load = Tile("home", "Спожито", "load", "Скільки енергії спожив дім (усі прилади разом).")
        self.k_buy = Tile("grid", "З мережі", "grid", "Скільки енергії взято з мережі (за це ви платите) "
                          "і скільки віддано в мережу.")
        self.k_self = Tile("check", "Самозабезпечення", "ok", "Яку частку споживання покрили власні сонце "
                           "й батарея, без мережі. 100% — мережа не знадобилась зовсім.")
        for i, w in enumerate((self.k_pv, self.k_load, self.k_buy, self.k_self)):
            g.addWidget(w, 0, i)
        self.v.addLayout(g)
        c1 = Card("Енергія по днях", hint="Стовпчики для кожного дня: вироблено сонцем, спожито домом, взято "
                  "з мережі. Наведіть мишу на день, щоб побачити точні цифри (кВт·год).")
        self.bars = BarChart(260)
        c1.lay.addWidget(self.bars)
        self.v.addWidget(c1)
        c2 = Card("Сьогодні", hint="Лічильники інвертора з початку доби.")
        self.today = QLabel("")
        self.today.setWordWrap(True)
        self.today.setObjectName("body")
        c2.lay.addWidget(self.today)
        self.v.addWidget(c2)
        self.v.addStretch()

    def refresh(self):
        days = [7, 30, 90][self.seg.current]
        data = self.app.store.daily(days)
        pv = sum(r[0] for _, r in data)
        load = sum(r[1] for _, r in data)
        buy = sum(r[2] for _, r in data)
        sold = sum(r[3] for _, r in data)
        gen = self.app.store.gen_daily(days, self.app.cfg["gen_min_power"]) if self.app.cfg["has_gen"] else {}
        gen_total = sum(gen.values())
        has_pv = self.app.cfg["has_pv"]
        self.k_pv.setVisible(has_pv)
        self.k_pv.set(kwh(pv), "у середньому %s на день" % kwh(pv / days))
        self.k_load.set(kwh(load), "у середньому %s на день" % kwh(load / days))
        self.k_buy.set(kwh(buy), "віддано в мережу %s" % kwh(sold))
        self.k_self.set("%.0f%%" % ((1 - buy / load) * 100) if load else "—", "частка споживання без мережі")
        if load:
            txt = "За %d днів дім спожив <b>%s</b>" % (days, kwh(load))
            if has_pv and pv:
                txt += ", сонце дало <b>%s</b> (%.0f%% від спожитого)" % (kwh(pv), min(100, pv / load * 100))
            txt += ", з мережі взято <b>%s</b>" % kwh(buy)
            if gen_total > 0:
                txt += ", генератор дав <b>%s</b>" % kwh(gen_total)
            self.insight.set(txt + ".")
        else:
            self.insight.set("Даних про енергію за цей період ще немає.")
        series = []
        if has_pv:
            series.append({"name": "СЕС", "color": "pv", "values": [r[0] for _, r in data]})
        series += [{"name": "Спожито", "color": "load", "values": [r[1] for _, r in data]},
                   {"name": "З мережі", "color": "grid", "values": [r[2] for _, r in data]}]
        if sold > 0:
            series.append({"name": "В мережу", "color": "sold", "values": [r[3] for _, r in data]})
        if gen_total > 0:
            series.append({"name": "Генератор", "color": "gen",
                           "values": [gen.get(d.isoformat(), 0) for d, _ in data]})
        self.bars.set_data([d.strftime("%d.%m") for d, _ in data], series, fmt=lambda v: "%.1f" % v,
                           full_labels=["%s, %d %s" % (M.WDAYS[d.weekday()], d.day, M.MONTHS[d.month - 1]) for d, _ in data])
        d = self.app.monitor.last
        if d:
            parts = []
            if has_pv:
                parts.append("СЕС %s" % kwh(d["day_pv"]))
            parts += ["⌂ спожито %s" % kwh(d["day_load"]), "↓ з мережі %s" % kwh(d["day_bought"]),
                      "↑ в мережу %s" % kwh(d["day_sold"]),
                      "▲ заряд батареї %s" % kwh(d["day_batt_charge"]), "▼ розряд %s" % kwh(d["day_batt_dis"])]
            self.today.setText("     ".join(parts))


# ---------------------------------------------------------------------------
class Battery(Page):
    title = "Батарея"

    def __init__(self, app):
        super().__init__(app)
        self.seg = Segmented(["24 години", "48 годин", "7 днів"], 1)
        self.seg.changed.connect(lambda _: self.refresh())
        self.head.addWidget(self.seg)
        g = QGridLayout()
        g.setSpacing(14)
        self.insight = Insight("battery")
        self.v.addWidget(self.insight)
        self.k_soc = Tile("battery", "Заряд", "batt", "Поточний рівень заряду батареї, її напруга і що вона зараз "
                          "робить: заряджається, розряджається чи відпочиває.")
        self.k_auto = Tile("clock", "Вистачить", "accent", "Приблизний час роботи від батареї при поточному "
                           "споживанні — до мінімального заряду. Що менше вмикаєте приладів, то довше.")
        self.k_temp = Tile("warn", "Температура", "orange", "Температура батареї та інвертора. Оптимально для "
                           "батареї — 15–30 °C; на морозі вона гірше заряджається.")
        self.k_cyc = Tile("chart", "Цикли", "grid", "Скільки повних циклів «заряд–розряд» відпрацювала батарея "
                          "(за даними програми). Літієві батареї розраховані на тисячі циклів.")
        for i, w in enumerate((self.k_soc, self.k_auto, self.k_temp, self.k_cyc)):
            g.addWidget(w, 0, i)
        self.v.addLayout(g)
        c1 = Card("Рівень заряду", hint="Як змінювався заряд батареї. Червоні ділянки — відключення: видно, "
                  "скільки заряду витрачено за кожне.")
        self.chart = LineChart(240)
        c1.lay.addWidget(self.chart)
        self.v.addWidget(c1)
        c2 = Card("Заряд і розряд по днях", hint="Скільки енергії батарея набрала і віддала кожного дня, кВт·год.")
        self.bars = BarChart(220)
        c2.lay.addWidget(self.bars)
        self.v.addWidget(c2)
        self.v.addStretch()

    def refresh(self):
        st, cfg = self.app.store, self.app.cfg
        d = self.app.monitor.last
        if d:
            soc = d["batt_soc"]
            self.k_soc.set("%d%%" % soc, "%.2f В · %s" % (d["batt_voltage"],
                           "розряд %s" % pw(d["batt_power"]) if d["batt_power"] > 20 else
                           "заряд %s" % pw(-d["batt_power"]) if d["batt_power"] < -20 else "спокій"),
                           "bad" if soc <= 20 else "warn" if soc <= 40 else "batt", soc)
            a = d.get("autonomy_h")
            self.k_auto.set(M.autonomy_text(a) or ("Заряджається" if d["batt_power"] < -20 else "—"),
                            "до %d%% при поточному навантаженні" % cfg["battery_min_soc"])
            self.k_temp.set("%.1f °C" % d["batt_temp"], "інвертор %.0f °C" % d["dc_temp"])
            stored = max(0.0, (soc - cfg["battery_min_soc"]) / 100 * (cfg["battery_kwh"] or 0))
            txt = "Зараз <b>%d%%</b> — це приблизно <b>%.1f кВт·год</b> енергії, доступної до мінімального заряду %d%%." % (
                soc, stored, cfg["battery_min_soc"])
            if a is not None:
                txt += " При поточному споживанні вистачить на <b>%s</b>." % M.autonomy_text(a)
            self.insight.set(txt)
        else:
            self.insight.set("")
        dis, first = st.total_discharge_kwh()
        cap = cfg["battery_kwh"] or 0
        self.k_cyc.set("%.1f" % (dis / cap) if cap else "—",
                       "повних циклів з %s" % dt.date.fromisoformat(first).strftime("%d.%m.%Y") if first else "ще немає даних")
        span = [86400, 2 * 86400, 7 * 86400][self.seg.current]
        now = time.time()
        a = now - span
        rows = st.series(a, ["soc"])
        self.chart.set_data([{"name": "Заряд", "color": "batt", "points": [(r[0], r[1]) for r in rows], "fill": True}],
                            a, now, [(s, e) for s, e, _, _ in st.outages_between(a, now)],
                            y_fmt=lambda v: "%d%%" % v, y_min=0, y_max=100)
        for s in self.chart.series:
            s["fmt"] = lambda v: "%d%%" % v
        data = st.daily(14)
        self.bars.set_data([x.strftime("%d.%m") for x, _ in data],
                           [{"name": "Заряд", "color": "batt", "values": [r[4] for _, r in data]},
                            {"name": "Розряд", "color": "orange", "values": [r[5] for _, r in data]}],
                           fmt=lambda v: "%.1f" % v,
                           full_labels=["%s, %d %s" % (M.WDAYS[x.weekday()], x.day, M.MONTHS[x.month - 1]) for x, _ in data])
