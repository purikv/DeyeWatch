# -*- coding: utf-8 -*-
"""Deye Cloud OpenAPI: догрузка історії за час, коли DeyeWatch не працював.

Специфікація: https://eu1-developer.deyecloud.com/v2/api-docs
  POST /v1.0/account/token?appId=…      {appSecret, email, password(sha256)}
  POST /v1.0/station/listWithDevice      станції та їх пристрої
  POST /v1.0/device/measurePoints        {deviceSn} — назви доступних показників
  POST /v1.0/device/historyRaw           {deviceSn, startTimestamp, endTimestamp(≤5 діб), measurePoints}
  POST /v1.0/station/history             {stationId, granularity=2, startAt, endAt(≤31 доба)} — енергія по днях
"""
import datetime as dt
import hashlib
import json
import re
import time
import urllib.error
import urllib.request

OK = "1000000"


class CloudError(Exception):
    pass


def sha256(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# Які показники нам потрібні і як їх упізнати серед measurePoints (назви різняться між моделями)
WANT = {
    "grid_v": [r"^(a)?gridvoltage(l1|a)?$", r"grid.*volt.*(l1|a)\b", r"grid.*volt", r"^ac.*volt.*(l1|a)?"],
    "freq":   [r"grid.*freq", r"^ac.*freq", r"freq"],
    "soc":    [r"^soc$", r"battery.*soc", r"soc"],
    "load_p": [r"total.*(load|consumption).*power", r"(load|consumption).*power$", r"(load|consumption).*power"],
    "pv_p":   [r"^(total)?dcpower$", r"total.*(dc|pv|solar).*power", r"(dc|pv|solar|generation).*power$"],
    "grid_p": [r"total.*grid.*power", r"^grid.*power$", r"grid.*power"],
    "batt_p": [r"^battery.*power$", r"batt.*power"],
}
EXCLUDE = re.compile(r"((?<!l1)l2|l3|gen|load|ups|bms|\bb\b|\bc\b|phaseb|phasec|bvolt|cvolt|max|min|rated|limit|setting|upper|lower|protect)", re.I)


def pick_points(points):
    norm = {p: re.sub(r"[^a-z0-9]", "", p.lower()) for p in points}
    out = {}
    for want, pats in WANT.items():
        for pat in pats:
            cands = [p for p in points if re.search(pat, norm[p]) and not EXCLUDE.search(p)]
            if cands:
                out[want] = sorted(cands, key=len)[0]
                break
    return out


def parse_ts(v):
    if v is None:
        return None
    s = str(v).strip()
    if re.fullmatch(r"\d{10,13}", s):
        n = int(s)
        return n / 1000 if n > 1e12 else n
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S"):
        try:
            return time.mktime(time.strptime(s[:19], fmt))
        except ValueError:
            pass
    return None


class DeyeCloud:
    def __init__(self, cfg, store):
        self.cfg, self.store = cfg, store
        from .config import is_deye_cloud
        self.base = (cfg["cloud_base"] or "https://eu1-developer.deyecloud.com").rstrip("/")
        if not is_deye_cloud(self.base):
            raise CloudError("сервер API має бути https://…deyecloud.com")

    # ---- HTTP
    def _http(self, path, body, auth=True, query=""):
        url = self.base + path + query
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = self.token()
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                res = json.loads(r.read(20_000_000).decode("utf-8"))
            if not isinstance(res, dict):
                raise CloudError("неочікувана відповідь сервера")
        except urllib.error.HTTPError as e:
            if e.code == 401 and auth:
                self.store.put("cloud_token", "")
            raise CloudError("HTTP %s" % e.code)
        if str(res.get("code")) != OK or res.get("success") is False:
            msg = res.get("msg") or ""
            try:
                msg = json.loads(msg).get("error", msg)
            except Exception:
                pass
            if auth and "token" in str(msg).lower():
                self.store.put("cloud_token", "")
            raise CloudError("%s (%s)" % (msg or "помилка", res.get("code")))
        return res

    def token(self):
        tok = self.store.get("cloud_token", "")
        exp = float(self.store.get("cloud_token_exp", 0) or 0)
        if tok and exp > time.time() + 3600:
            return tok
        c = self.cfg
        if not (c["cloud_app_id"] and c["cloud_app_secret"] and c["cloud_email"] and c["cloud_password_sha"]):
            raise CloudError("заповніть App ID, App Secret, email і пароль")
        res = self._http("/v1.0/account/token",
                         {"appSecret": c["cloud_app_secret"], "email": c["cloud_email"],
                          "password": c["cloud_password_sha"]},
                         auth=False, query="?appId=%s" % c["cloud_app_id"])
        tok = res.get("accessToken") or ""
        if not tok.lower().startswith("bearer"):
            tok = "Bearer " + tok
        self.store.put("cloud_token", tok)
        self.store.put("cloud_token_exp", time.time() + float(res.get("expiresIn") or 86400))
        return tok

    # ---- станція, пристрій, показники
    def setup(self, force=False):
        info = self.store.get("cloud_setup")
        if info and not force:
            return json.loads(info)
        res = self._http("/v1.0/station/listWithDevice", {"page": 1, "size": 20})
        stations = res.get("stationList") or []
        if not stations:
            raise CloudError("в акаунті немає станцій")
        st = stations[0]
        inv = [d for d in st.get("deviceListItems") or [] if d.get("deviceType") == "INVERTER"]
        if not inv:
            raise CloudError("у станції «%s» немає інвертора" % st.get("name"))
        sn = inv[0]["deviceSn"]
        mp = self._http("/v1.0/device/measurePoints", {"deviceSn": sn, "deviceType": "INVERTER"})
        points = mp.get("measurePoints") or []
        if points and isinstance(points[0], dict):
            points = [p.get("key") or p.get("measurePoint") or p.get("name") for p in points]
        info = {"station_id": st["id"], "station_name": st.get("name"), "timezone": st.get("regionTimezone"),
                "device_sn": sn, "points": points, "picked": pick_points(points),
                "stations": [(s.get("id"), s.get("name")) for s in stations]}
        self.store.put("cloud_setup", json.dumps(info, ensure_ascii=False))
        return info

    def history_raw(self, sn, a, b, points):
        """[(ts, {point: float})] — дані з кроком ~5 хв; a..b ≤ 5 діб.
        API приймає не більше 5 показників за запит (інакше «list too long»), тож ділимо на частини."""
        merged = {}
        for i in range(0, len(points), 5):
            res = self._http("/v1.0/device/historyRaw", {"deviceSn": sn, "deviceType": "INVERTER",
                                                         "startTimestamp": int(a), "endTimestamp": int(b),
                                                         "measurePoints": points[i:i + 5]})
            for item in res.get("dataList") or []:
                ts = parse_ts(item.get("time") or item.get("collectionTime"))
                if ts is None:
                    continue
                vals = merged.setdefault(ts, {})
                for kv in item.get("itemList") or []:
                    k = kv.get("key") or kv.get("name")
                    try:
                        vals[k] = float(kv.get("value"))
                    except (TypeError, ValueError):
                        pass
        return sorted(merged.items(), key=lambda x: x[0])

    def station_daily(self, station_id, d0, d1):
        """Енергія по днях за [d0, d1) (≤31 доба)."""
        res = self._http("/v1.0/station/history", {"stationId": station_id, "granularity": 2,
                                                   "startAt": d0.isoformat(), "endAt": d1.isoformat()})
        out = []
        for it in res.get("stationDataItems") or []:
            try:
                day = dt.date(int(it["year"]), int(it["month"]), int(it["day"]))
            except Exception:
                continue
            f = lambda k: float(it.get(k) or 0)
            out.append((day, f("generationValue"), f("consumptionValue"), f("purchaseValue"),
                        f("gridValue"), f("chargeValue"), f("dischargeValue")))
        return out


# ---------------------------------------------------------------------------
def find_gaps(store, a, b, min_gap=420):
    """Проміжки [x, y] у межах a..b, де немає локальних записів довше min_gap секунд."""
    ts = [r[0] for r in store.q("SELECT ts FROM samples WHERE ts>=? AND ts<=? ORDER BY ts", (a, b))]
    gaps, prev = [], a
    for t in ts + [b]:
        if t - prev > min_gap:
            gaps.append((prev, t))
        prev = t
    return gaps


def sync(cloud, cfg, store, log=print):
    """Заповнює прогалини історії з хмари. Повертає короткий звіт."""
    info = cloud.setup()
    picked = pick_points(info["points"])
    if not picked:
        raise CloudError("не вдалося розпізнати показники інвертора: %s" % ", ".join(info["points"][:20]))
    now = time.time()
    first = now - cfg["cloud_backfill_days"] * 86400
    done = float(store.get("cloud_checked", 0) or 0)
    a = max(first, done - 3 * 3600)
    # хмара отримує дані від інвертора із затримкою ~5–15 хв: просимо до «мінус 5 хв»,
    # а те, чого там ще немає, доберемо наступною (прискореною) синхронізацією
    gaps = find_gaps(store, a, now - 5 * 60)
    thr = cfg["grid_min_voltage"]
    added, outs = 0, 0
    pts = list(dict.fromkeys(picked.values()))
    for g0, g1 in gaps:
        t = g0
        while t < g1:
            t2 = min(g1, t + 5 * 86400 - 60)
            rows = cloud.history_raw(info["device_sn"], t, t2, pts)
            t = t2
            if not rows:
                continue
            series = []
            for ts, v in rows:
                gv = v.get(picked.get("grid_v"))
                ok = None if gv is None else int(gv >= thr)
                s = {"ts": int(ts // 60 * 60), "grid_ok": ok if ok is not None else 1,
                     "v_avg": gv if ok else None, "v_min": gv if ok else None, "v_max": gv if ok else None,
                     "freq": v.get(picked.get("freq")) if ok else None,
                     "grid_p": v.get(picked.get("grid_p")), "load_p": v.get(picked.get("load_p")),
                     "pv_p": v.get(picked.get("pv_p")), "batt_p": v.get(picked.get("batt_p")),
                     "soc": v.get(picked.get("soc")), "batt_v": None, "batt_t": None, "dc_t": None}
                if g0 < ts < g1:
                    store.add_sample(s)
                    added += 1
    # відключення перебудовуються за всіма записами (локальні + хмара), тож «відкрите» відключення,
    # що тривало, поки програма була закрита, розрізається там, де хмара бачила світло
    if not store.get("outages_rebuilt_v2"):
        outs = store.rebuild_outages(0)
        store.put("outages_rebuilt_v2", 1)
    elif added:
        outs = store.rebuild_outages(min(min(g0 for g0, _ in gaps) - 600, now - 6 * 3600))
    else:
        # нових точок немає, але останні години все одно перебудовуємо: це виправляє сліди
        # попередніх збоїв (напр. хибний проміжок «світло було» після запуску) і коштує мілісекунди
        outs = store.rebuild_outages(now - 6 * 3600)
    store.put("cloud_checked", now - 15 * 60)
    # енергія по днях
    days = 0
    d1 = dt.date.today() + dt.timedelta(days=1)
    d0 = max(dt.date.fromtimestamp(first), d1 - dt.timedelta(days=30))
    while d0 < d1:
        de = min(d1, d0 + dt.timedelta(days=30))
        for day, pv, load, buy, sold, chg, dis in cloud.station_daily(info["station_id"], d0, de):
            store.x("""INSERT INTO daily VALUES(?,?,?,?,?,?,?) ON CONFLICT(day) DO UPDATE SET
                       pv=max(pv,excluded.pv), load=max(load,excluded.load), bought=max(bought,excluded.bought),
                       sold=max(sold,excluded.sold), batt_chg=max(batt_chg,excluded.batt_chg),
                       batt_dis=max(batt_dis,excluded.batt_dis)""",
                    (day.isoformat(), pv, load, buy, sold, chg, dis))
            days += 1
        d0 = de
    store.add_event("cloud_sync", added, "%d точок, %d відключень" % (added, outs))
    # свіжий пропуск (останні 45 хв), який хмара ще не встигла заповнити → повторити через 10 хв
    pending = bool(find_gaps(store, now - 45 * 60, now - 5 * 60))
    return {"samples": added, "outages": outs, "days": days, "gaps": len(gaps), "pending": pending}


def merge_outages(store, series):
    """series [(ts, ok)] → відключення; додає нові або подовжує наявні, що перетинаються."""
    found, start, last_ok, last_bad = [], None, None, None
    for ts, ok in series:
        if not ok:
            if start is None:   # межа — посередині між останньою «є» і першою «немає»
                start = (last_ok + ts) / 2 if last_ok is not None else ts
            last_bad = ts
        else:
            if start is not None:
                found.append((start, (last_bad + ts) / 2))
                start = None
            last_ok = ts
    if start is not None and series:
        found.append((start, series[-1][0]))
    n = 0
    for s, e in found:
        if e - s < 120:
            continue
        ov = store.q("SELECT id,start,end FROM outages WHERE start<? AND coalesce(end, 1e12)>?", (e + 600, s - 600))
        if ov:
            i, s0, e0 = ov[0]
            if s < s0:
                store.x("UPDATE outages SET start=? WHERE id=?", (s, i))
            if e0 is not None and e > e0:
                store.x("UPDATE outages SET end=? WHERE id=?", (e, i))
        else:
            store.x("INSERT INTO outages(start,end) VALUES(?,?)", (s, e))
            n += 1
    return n
