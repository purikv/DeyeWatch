package com.deyewatch.app.data

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Locale

class CloudException(message: String) : Exception(message)

/**
 * Deye Cloud OpenAPI — ті самі запити, що й у DeyeWatch для ПК (desktop/dw/cloud.py):
 * токен, станція й інвертор, сирі дані historyRaw (крок ~5 хв).
 */
class DeyeCloud(private val s: Settings) {
    private val base = s.cloudBase.trimEnd('/')

    init {
        if (!Settings.isDeyeCloud(base)) throw CloudException("сервер API має бути https://…deyecloud.com")
    }

    private fun http(path: String, body: JSONObject, auth: Boolean = true, query: String = ""): JSONObject {
        val c = URL(base + path + query).openConnection() as HttpURLConnection
        try {
            c.requestMethod = "POST"
            c.connectTimeout = 20000
            c.readTimeout = 40000
            c.doOutput = true
            c.setRequestProperty("Content-Type", "application/json")
            if (auth) c.setRequestProperty("Authorization", token())
            c.outputStream.use { it.write(body.toString().toByteArray()) }
            val code = c.responseCode
            if (code == 401 && auth) s.putKv("cloud_token", null)
            if (code !in 200..299) throw CloudException("HTTP $code")
            val res = JSONObject(c.inputStream.bufferedReader().use { it.readText() })
            if (res.optString("code") != "1000000" || (res.has("success") && !res.optBoolean("success"))) {
                var msg = res.optString("msg", "помилка")
                runCatching { msg = JSONObject(msg).optString("error", msg) }
                if (auth && msg.contains("token", true)) s.putKv("cloud_token", null)
                throw CloudException("$msg (${res.optString("code")})")
            }
            return res
        } finally {
            c.disconnect()
        }
    }

    private fun token(): String {
        val tok = s.kv("cloud_token")
        val exp = s.kv("cloud_token_exp")?.toLongOrNull() ?: 0
        if (!tok.isNullOrBlank() && exp > System.currentTimeMillis() + 3_600_000) return tok
        if (!s.cloudReady) throw CloudException("заповніть App ID, App Secret, email і пароль Deye Cloud")
        val res = http("/v1.0/account/token",
            JSONObject().put("appSecret", s.cloudAppSecret).put("email", s.cloudEmail).put("password", s.cloudPasswordSha),
            auth = false, query = "?appId=" + s.cloudAppId.trim())
        var t = res.optString("accessToken")
        if (!t.lowercase().startsWith("bearer")) t = "Bearer $t"
        s.putKv("cloud_token", t)
        s.putKv("cloud_token_exp", (System.currentTimeMillis() + res.optLong("expiresIn", 86400) * 1000).toString())
        return t
    }

    private data class Setup(val sn: String, val points: Map<String, String>)

    private fun setup(): Setup {
        s.kv("cloud_setup")?.let { cached ->
            runCatching {
                val j = JSONObject(cached)
                val pts = j.getJSONObject("points")
                return Setup(j.getString("sn"), pts.keys().asSequence().associateWith { pts.getString(it) })
            }
        }
        val st = http("/v1.0/station/listWithDevice", JSONObject().put("page", 1).put("size", 20))
            .optJSONArray("stationList")?.optJSONObject(0) ?: throw CloudException("в акаунті немає станцій")
        val devices = st.optJSONArray("deviceListItems") ?: JSONArray()
        val inv = (0 until devices.length()).map { devices.getJSONObject(it) }
            .firstOrNull { it.optString("deviceType") == "INVERTER" } ?: throw CloudException("у станції немає інвертора")
        val sn = inv.getString("deviceSn")
        val mp = http("/v1.0/device/measurePoints", JSONObject().put("deviceSn", sn).put("deviceType", "INVERTER"))
            .optJSONArray("measurePoints") ?: JSONArray()
        val names = (0 until mp.length()).mapNotNull {
            when (val x = mp.get(it)) {
                is String -> x
                is JSONObject -> x.optString("key").ifBlank { x.optString("measurePoint").ifBlank { x.optString("name") } }
                else -> null
            }
        }
        val picked = pickPoints(names)
        if ("grid_v" !in picked) throw CloudException("не вдалося знайти напругу мережі серед показників хмари")
        val j = JSONObject().put("sn", sn).put("points", JSONObject(picked as Map<*, *>))
        s.putKv("cloud_setup", j.toString())
        return Setup(sn, picked)
    }

    /** Записи з кроком ~5 хв за [fromMs, toMs] (не більше 5 діб). */
    fun history(fromMs: Long, toMs: Long): List<InverterData> {
        val st = setup()
        val pts = st.points.values.distinct()
        val merged = sortedMapOf<Long, MutableMap<String, Double>>()
        for (chunk in pts.chunked(5)) {        // API приймає не більше 5 показників за запит
            val res = http("/v1.0/device/historyRaw", JSONObject()
                .put("deviceSn", st.sn).put("deviceType", "INVERTER")
                .put("startTimestamp", fromMs / 1000).put("endTimestamp", toMs / 1000)
                .put("measurePoints", JSONArray(chunk)))
            val list = res.optJSONArray("dataList") ?: continue
            for (i in 0 until list.length()) {
                val item = list.getJSONObject(i)
                val ts = parseTs(item.opt("time") ?: item.opt("collectionTime")) ?: continue
                val vals = merged.getOrPut(ts) { HashMap() }
                val items = item.optJSONArray("itemList") ?: continue
                for (k in 0 until items.length()) {
                    val kv = items.getJSONObject(k)
                    val key = kv.optString("key").ifBlank { kv.optString("name") }
                    kv.optString("value").toDoubleOrNull()?.let { vals[key] = it }
                }
            }
        }
        val p = st.points
        return merged.mapNotNull { (ts, v) ->
            val gv = v[p["grid_v"]] ?: return@mapNotNull null
            InverterData(
                ts = ts, source = InverterData.Source.CLOUD, gridVoltage = gv, gridFreq = v[p["freq"]],
                gridPower = v[p["grid_p"]] ?: 0.0, loadPower = v[p["load_p"]] ?: 0.0, pvPower = v[p["pv_p"]] ?: 0.0,
                battPower = v[p["batt_p"]] ?: 0.0, soc = v[p["soc"]] ?: 0.0, battVoltage = null, battTemp = null,
                dcTemp = null, genPower = 0.0, dayPv = null, dayLoad = null, dayBought = null, daySold = null,
                dayBattCharge = null, dayBattDis = null, runningStatus = null,
            )
        }
    }

    /** Останній відомий стан інвертора за даними хмари. */
    fun latest(): InverterData? {
        val now = System.currentTimeMillis()
        return history(now - 45 * 60_000, now).lastOrNull()
    }

    companion object {
        private val WANT = linkedMapOf(
            "grid_v" to listOf("^(a)?gridvoltage(l1|a)?$", "grid.*volt.*(l1|a)\\b", "grid.*volt", "^ac.*volt.*(l1|a)?"),
            "freq" to listOf("grid.*freq", "^ac.*freq", "freq"),
            "soc" to listOf("^soc$", "battery.*soc", "soc"),
            "load_p" to listOf("total.*(load|consumption).*power", "(load|consumption).*power$", "(load|consumption).*power"),
            "pv_p" to listOf("^(total)?dcpower$", "total.*(dc|pv|solar).*power", "(dc|pv|solar|generation).*power$"),
            "grid_p" to listOf("total.*grid.*power", "^grid.*power$", "grid.*power"),
            "batt_p" to listOf("^battery.*power$", "batt.*power"),
        )
        private val EXCLUDE = Regex(
            "((?<!l1)l2|l3|gen|load|ups|bms|\\bb\\b|\\bc\\b|phaseb|phasec|bvolt|cvolt|max|min|rated|limit|setting|upper|lower|protect)",
            RegexOption.IGNORE_CASE)

        fun pickPoints(points: List<String>): Map<String, String> {
            val norm = points.associateWith { it.lowercase().replace(Regex("[^a-z0-9]"), "") }
            val out = LinkedHashMap<String, String>()
            for ((want, pats) in WANT) {
                for (pat in pats) {
                    val re = Regex(pat)
                    val c = points.filter { re.containsMatchIn(norm.getValue(it)) && !EXCLUDE.containsMatchIn(it) }
                    if (c.isNotEmpty()) { out[want] = c.minBy { it.length }; break }
                }
            }
            return out
        }

        fun parseTs(v: Any?): Long? {
            val s = v?.toString()?.trim() ?: return null
            if (Regex("\\d{10,13}").matches(s)) {
                val n = s.toLong()
                return if (n > 1_000_000_000_000L) n else n * 1000
            }
            for (fmt in listOf("yyyy-MM-dd HH:mm:ss", "yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd HH:mm", "yyyy/MM/dd HH:mm:ss")) {
                runCatching { return SimpleDateFormat(fmt, Locale.US).parse(s.take(19))!!.time }
            }
            return null
        }
    }
}
