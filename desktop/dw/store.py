# -*- coding: utf-8 -*-
"""Збереження історії (SQLite) та аналітика."""
import datetime as dt
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples(
  ts INTEGER PRIMARY KEY, grid_ok INTEGER,
  v_avg REAL, v_min REAL, v_max REAL, freq REAL,
  grid_p INTEGER, load_p INTEGER, pv_p INTEGER, batt_p INTEGER,
  soc INTEGER, batt_v REAL, batt_t REAL, dc_t REAL);
CREATE TABLE IF NOT EXISTS daily(
  day TEXT PRIMARY KEY, pv REAL, load REAL, bought REAL, sold REAL,
  batt_chg REAL, batt_dis REAL);
CREATE TABLE IF NOT EXISTS outages(
  id INTEGER PRIMARY KEY AUTOINCREMENT, start REAL, end REAL);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, kind TEXT, value REAL, text TEXT);
CREATE TABLE IF NOT EXISTS outbox(
  id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
"""


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        try:   # колонка генератора з'явилася пізніше — додаємо в стару базу
            self.db.execute("ALTER TABLE samples ADD COLUMN gen_p INTEGER")
            self.db.commit()
        except sqlite3.OperationalError:
            pass
        self.lock = threading.Lock()

    def q(self, sql, args=()):
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    def x(self, sql, args=()):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur.lastrowid

    # ---- kv ----
    def get(self, k, default=None):
        r = self.q("SELECT v FROM kv WHERE k=?", (k,))
        return r[0][0] if r else default

    def put(self, k, v):
        self.x("INSERT OR REPLACE INTO kv VALUES(?,?)", (k, str(v)))

    # ---- запис ----
    def add_sample(self, s):
        self.x("""INSERT OR REPLACE INTO samples(ts, grid_ok, v_avg, v_min, v_max, freq, grid_p, load_p, pv_p,
                  batt_p, soc, batt_v, batt_t, dc_t, gen_p) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (s["ts"], s["grid_ok"], s["v_avg"], s["v_min"], s["v_max"], s["freq"],
                s["grid_p"], s["load_p"], s["pv_p"], s["batt_p"], s["soc"],
                s["batt_v"], s["batt_t"], s["dc_t"], s.get("gen_p")))

    def update_daily(self, d):
        day = dt.date.today().isoformat()
        vals = (d["day_pv"], d["day_load"], d["day_bought"], d["day_sold"],
                d["day_batt_charge"], d["day_batt_dis"])
        self.x("""INSERT INTO daily VALUES(?,?,?,?,?,?,?)
                  ON CONFLICT(day) DO UPDATE SET
                  pv=max(pv,excluded.pv), load=max(load,excluded.load),
                  bought=max(bought,excluded.bought), sold=max(sold,excluded.sold),
                  batt_chg=max(batt_chg,excluded.batt_chg), batt_dis=max(batt_dis,excluded.batt_dis)""",
               (day,) + vals)

    def open_outage(self):
        r = self.q("SELECT id,start FROM outages WHERE end IS NULL ORDER BY id DESC LIMIT 1")
        return r[0] if r else None

    def start_outage(self, ts):
        if not self.open_outage():
            self.x("INSERT INTO outages(start,end) VALUES(?,NULL)", (ts,))

    def end_outage(self, ts):
        o = self.open_outage()
        if o:
            self.x("UPDATE outages SET end=? WHERE id=?", (ts, o[0]))
            return ts - o[1]
        return None

    def last_outage_end(self):
        r = self.q("SELECT max(end) FROM outages")
        return r[0][0] if r and r[0][0] else None

    def rebuild_outages(self, a, min_dur=120):
        """Перебудовує відключення з a до останнього запису за самими записами (локальні + хмара).
        Відключення, що почалися після останнього запису (поточна хвилина), не чіпає."""
        last = self.q("SELECT max(ts) FROM samples")[0][0]
        if not last:
            return 0
        # відключення, що перетинає початок вікна, включаємо повністю
        r = self.q("SELECT min(start) FROM outages WHERE start<? AND coalesce(end, 1e12)>?", (a, a))[0][0]
        if r:
            a = r
        rows = self.q("SELECT ts, grid_ok FROM samples WHERE ts>=? ORDER BY ts", (a,))
        found, start, prev = [], None, None
        for ts, ok in rows:
            near = prev is not None and ts - prev <= 120
            if not ok and start is None:
                start = ts if (prev is None or near) else (prev + ts) / 2
            elif ok and start is not None:
                found.append([start, ts if near else (prev + ts) / 2])
                start = None
            prev = ts
        open_now = self.open_outage()
        keep_open = open_now if open_now and open_now[1] > last else None   # почалося вже після запису
        if start is not None:
            if keep_open:
                self.x("UPDATE outages SET start=? WHERE id=?", (min(start, keep_open[1]), keep_open[0]))
            else:
                found.append([start, None if open_now else last + 60])
        merged = []
        for s, e in found:
            if merged and merged[-1][1] is not None and s - merged[-1][1] < min_dur:
                merged[-1][1] = e
            else:
                merged.append([s, e])
        merged = [(s, e) for s, e in merged if e is None or e - s >= min_dur]
        with self.lock:
            self.db.execute("DELETE FROM outages WHERE start>=? AND start<=? AND id IS NOT ?",
                            (a, last, keep_open[0] if keep_open else None))
            self.db.executemany("INSERT INTO outages(start,end) VALUES(?,?)", merged)
            self.db.commit()
        return len(merged)

    def add_event(self, kind, value, text, ts=None):
        self.x("INSERT INTO events(ts,kind,value,text) VALUES(?,?,?,?)",
               (ts or time.time(), kind, value, text))

    def purge(self, keep_days):
        lim = time.time() - keep_days * 86400
        self.x("DELETE FROM samples WHERE ts<?", (lim,))
        self.x("DELETE FROM events WHERE ts<?", (lim,))

    # ---- outbox ----
    def outbox_add(self, chat_id, text):
        self.x("INSERT INTO outbox(chat_id,text) VALUES(?,?)", (str(chat_id), text))

    def outbox_first(self):
        r = self.q("SELECT id,chat_id,text FROM outbox ORDER BY id LIMIT 1")
        return r[0] if r else None

    def outbox_del(self, i):
        self.x("DELETE FROM outbox WHERE id=?", (i,))

    # ---- аналітика ----
    def series(self, since, cols):
        return self.q("SELECT ts,%s FROM samples WHERE ts>=? ORDER BY ts" % ",".join(cols), (since,))

    def outages_between(self, a, b):
        now = time.time()
        rows = self.q("SELECT start, coalesce(end, ?) FROM outages WHERE coalesce(end, ?)>? AND start<? ORDER BY start",
                      (now, now, a, b))
        return [(max(s, a), min(e, b), s, e) for s, e in rows]

    def outage_stats(self, days):
        now = time.time()
        a = now - days * 86400
        rows = self.outages_between(a, now)
        durs = [e - s for s, e, _, _ in rows]
        full = [e0 - s0 for _, _, s0, e0 in rows]
        return {
            "count": len(rows),
            "total": sum(durs),
            "longest": max(full) if full else 0,
            "avg": (sum(full) / len(full)) if full else 0,
            "share": sum(durs) / (days * 86400),
        }

    def outage_hours_per_day(self, days):
        """[(дата, годин без світла)] за останні days днів, включно з сьогодні."""
        today = dt.date.today()
        res = []
        for i in range(days - 1, -1, -1):
            d = today - dt.timedelta(days=i)
            a = time.mktime(d.timetuple())
            b = a + 86400
            tot = sum(e - s for s, e, _, _ in self.outages_between(a, b))
            res.append((d, tot / 3600))
        return res

    def outage_heatmap(self, days=30):
        """Матриця 7×24: частка часу без світла для дня тижня × години."""
        now = time.time()
        a = now - days * 86400
        off = [[0.0] * 24 for _ in range(7)]
        tot = [[0.0] * 24 for _ in range(7)]
        first = self.q("SELECT min(start) FROM outages")[0][0]
        fs = self.q("SELECT min(ts) FROM samples")[0][0]
        start_obs = min([x for x in (first, fs) if x] or [now])
        t = max(a, start_obs)
        t = t - (t % 3600)
        rows = self.outages_between(a, now)
        while t < now:
            lt = time.localtime(t)
            w, h = lt.tm_wday, lt.tm_hour
            seg_end = min(t + 3600, now)
            tot[w][h] += seg_end - t
            for s, e, _, _ in rows:
                ov = min(e, seg_end) - max(s, t)
                if ov > 0:
                    off[w][h] += ov
            t += 3600
        return [[(off[w][h] / tot[w][h]) if tot[w][h] else None for h in range(24)] for w in range(7)]

    def recent_outages(self, n=30):
        return self.q("SELECT start,end FROM outages ORDER BY start DESC LIMIT ?", (n,))

    def daily(self, days):
        a = (dt.date.today() - dt.timedelta(days=days - 1)).isoformat()
        rows = {r[0]: r[1:] for r in self.q("SELECT * FROM daily WHERE day>=? ORDER BY day", (a,))}
        out = []
        for i in range(days - 1, -1, -1):
            d = dt.date.today() - dt.timedelta(days=i)
            out.append((d, rows.get(d.isoformat(), (0, 0, 0, 0, 0, 0))))
        return out

    def grid_quality(self, since, vlo, vhi):
        r = self.q("""SELECT min(v_min), max(v_max), avg(v_avg), min(freq), max(freq),
                      sum(CASE WHEN v_min<? THEN 1 ELSE 0 END),
                      sum(CASE WHEN v_max>? THEN 1 ELSE 0 END), count(*)
                      FROM samples WHERE ts>=? AND grid_ok=1""", (vlo, vhi, since))[0]
        return {"vmin": r[0], "vmax": r[1], "vavg": r[2], "fmin": r[3], "fmax": r[4],
                "low_min": r[5] or 0, "high_min": r[6] or 0, "minutes": r[7] or 0}

    def events(self, kinds, n=30):
        qs = ",".join("?" * len(kinds))
        return self.q("SELECT ts,kind,value,text FROM events WHERE kind IN (%s) ORDER BY ts DESC LIMIT ?" % qs,
                      tuple(kinds) + (n,))

    def total_discharge_kwh(self):
        r = self.q("SELECT sum(batt_dis), min(day) FROM daily")[0]
        return (r[0] or 0), r[1]

    def gen_stats(self, since, thr=30):
        """Генератор з моменту since: (годин роботи, кВт·год). Записи похвилинні."""
        r = self.q("SELECT count(*), sum(gen_p) FROM samples WHERE ts>=? AND gen_p>=?", (since, thr))[0]
        return (r[0] or 0) / 60, (r[1] or 0) / 60000

    def gen_daily(self, days, thr=30):
        """{дата ISO: кВт·год від генератора} за останні days днів."""
        a = time.mktime((dt.date.today() - dt.timedelta(days=days - 1)).timetuple())
        rows = self.q("""SELECT date(ts, 'unixepoch', 'localtime'), sum(gen_p) FROM samples
                         WHERE ts>=? AND gen_p>=? GROUP BY 1""", (a, thr))
        return {d: (w or 0) / 60000 for d, w in rows}

    def recent_discharge_w(self, minutes=15):
        r = self.q("SELECT avg(batt_p) FROM samples WHERE ts>=? AND batt_p>0", (time.time() - minutes * 60,))
        return r[0][0]
