# -*- coding: utf-8 -*-
"""Єдиний опис сповіщень: з нього малюється спливаюче вікно на ПК і повідомлення Telegram."""
import html
import time
from dataclasses import dataclass, field

MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня", "липня",
          "серпня", "вересня", "жовтня", "листопада", "грудня"]
WDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "нд"]
WDAYS_FULL = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]


def fmt_dur(sec, short=False):
    sec = int(max(0, sec or 0))
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    if d:
        return "%d д %d год" % (d, h)
    if h:
        return "%d год %02d хв" % (h, m) if not short else "%d:%02d" % (h, m)
    return "%d хв" % m


def fmt_clock(ts):
    return time.strftime("%H:%M", time.localtime(ts))


def fmt_date(ts):
    lt = time.localtime(ts)
    return "%s, %d %s" % (WDAYS[lt.tm_wday], lt.tm_mday, MONTHS[lt.tm_mon - 1])


def fmt_power(w):
    w = w or 0
    return "%.2f кВт" % (w / 1000) if abs(w) >= 1000 else "%d Вт" % round(w)


def soc_bar(soc, n=10):
    k = max(0, min(n, round((soc or 0) / 100 * n)))
    return "▰" * k + "▱" * (n - k)


@dataclass
class Note:
    kind: str                 # outage | restore | low_soc | voltage | offline | online | summary | test
    title: str
    subtitle: str
    rows: list = field(default_factory=list)    # [(іконка, підпис, значення)]
    soc: float = None          # якщо задано — показати шкалу заряду
    emoji: str = ""
    ts: float = field(default_factory=time.time)
    sticky: bool = False

    def telegram_html(self):
        e = lambda s: html.escape(s, quote=False)
        lines = ["%s <b>%s</b>" % (self.emoji, e(self.title)),
                 "<i>%s</i>" % e(self.subtitle), ""]
        for icon, label, value in self.rows:
            lines.append("%s %s: <b>%s</b>" % (icon, e(label), e(str(value))))
        if self.soc is not None:
            lines.append("")
            lines.append("<code>%s</code>  %d%%" % (soc_bar(self.soc), round(self.soc)))
        return "\n".join(lines).strip()


# Кольори акцентів (світла/темна тема однакові — насичені, читаються на обох)
ACCENT = {
    "outage": "#E5484D", "restore": "#30A46C", "low_soc": "#F5A524", "voltage": "#F76B15",
    "offline": "#8B8D98", "online": "#3E63DD", "summary": "#3E63DD", "test": "#3E63DD",
    "gen_on": "#B5651D", "gen_off": "#8B8D98",
}


def autonomy_text(hours):
    if hours is None:
        return None
    if hours > 48:
        return "понад 2 доби"
    return "≈ " + fmt_dur(hours * 3600)


def note_outage(name, ts, was_on_sec, d, autonomy_h):
    rows = [("⏱", "Світло було", fmt_dur(was_on_sec) if was_on_sec else "—"),
            ("🏠", "Споживання", fmt_power(d.get("load_power")))]
    a = autonomy_text(autonomy_h)
    if a:
        rows.append(("⏳", "Батареї вистачить", a))
    return Note("outage", "Світло зникло", "%s · %s, %s" % (name, fmt_date(ts), fmt_clock(ts)),
                rows, d.get("batt_soc"), "🔴", ts, sticky=True)


def note_restore(name, ts, off_sec, d):
    rows = [("⏱", "Світла не було", fmt_dur(off_sec) if off_sec else "—"),
            ("⚡", "Напруга", "%.0f В · %.2f Гц" % (d.get("grid_voltage", 0), d.get("grid_freq", 0)))]
    return Note("restore", "Світло з'явилося", "%s · %s, %s" % (name, fmt_date(ts), fmt_clock(ts)),
                rows, d.get("batt_soc"), "🟢", ts)


def note_low_soc(name, soc, threshold, off_sec, d, autonomy_h):
    rows = [("🕯", "Без світла вже", fmt_dur(off_sec)),
            ("🏠", "Споживання", fmt_power(d.get("load_power")))]
    a = autonomy_text(autonomy_h)
    if a:
        rows.append(("⏳", "Залишилось", a))
    return Note("low_soc", "Заряд батареї %d%%" % soc, "%s · нижче порогу %d%%" % (name, threshold),
                rows, soc, "🪫", sticky=soc <= 20)


def note_voltage(name, kind, v, lo, hi):
    if kind == "high":
        t, s = "Завищена напруга", "Вище норми %d В" % hi
    else:
        t, s = "Занижена напруга", "Нижче норми %d В" % lo
    return Note("voltage", t, "%s · %s" % (name, s),
                [("⚡", "Зараз", "%.0f В" % v), ("📏", "Норма", "%d–%d В" % (lo, hi))], None, "⚠️")


def note_gen_start(name, ts, d, off_sec):
    rows = [("⚙️", "Потужність", fmt_power(d.get("gen_power")))]
    if off_sec:
        rows.append(("🕯", "Світла немає вже", fmt_dur(off_sec)))
    rows.append(("🏠", "Споживання", fmt_power(d.get("load_power"))))
    return Note("gen_on", "Генератор запущено", "%s · %s, %s" % (name, fmt_date(ts), fmt_clock(ts)),
                rows, d.get("batt_soc"), "⚙️", ts)


def note_gen_stop(name, ts, run_sec, kwh, d):
    rows = [("⏱", "Пропрацював", fmt_dur(run_sec))]
    if kwh:
        rows.append(("⚡", "Дав енергії", "%.1f кВт·год" % kwh))
    return Note("gen_off", "Генератор зупинено", "%s · %s, %s" % (name, fmt_date(ts), fmt_clock(ts)),
                rows, d.get("batt_soc"), "⏹", ts)


def note_offline(name, err):
    return Note("offline", "Немає зв'язку з інвертором", "%s · WiFi-стік не відповідає" % name,
                [("ℹ️", "Причина", err[:80]), ("❔", "Стан мережі", "невідомий")], None, "📡")


def note_online(name):
    return Note("online", "Зв'язок відновлено", "%s · інвертор знову на зв'язку" % name, [], None, "✅")
