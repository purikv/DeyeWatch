package com.deyewatch.app.data

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject
import java.net.URI
import java.security.MessageDigest

/**
 * Налаштування. Імена ключів — ті самі, що в DeyeWatch для ПК, тож файл експорту налаштувань
 * з ПК можна просто імпортувати на телефон.
 */
class Settings(context: Context) {
    private val p: SharedPreferences = context.getSharedPreferences("settings", Context.MODE_PRIVATE)

    var name by str("name", "Дім")
    var loggerIp by str("logger_ip", "")
    var loggerSerial by long("logger_serial", 0)
    var loggerPort by int("logger_port", 8899)
    var gridMinVoltage by dbl("grid_min_voltage", 170.0)
    var batteryKwh by dbl("battery_kwh", 10.0)
    var batteryMinSoc by int("battery_min_soc", 15)
    var lowSocThresholds by str("low_soc_thresholds", "50, 30, 20")
    var hasPv by bool("has_pv", true)
    var hasGen by bool("has_gen", false)
    var genMinPower by int("gen_min_power", 30)

    var notifyOutage by bool("notify_outage", true)
    var notifyRestore by bool("notify_restore", true)
    var notifyLowSoc by bool("notify_low_soc", true)
    var notifyGen by bool("notify_gen", true)
    var notifyOffline by bool("notify_offline", true)

    var monitorEnabled by bool("monitor_enabled", true)
    var onboarded by bool("onboarded", false)

    var cloudEnabled by bool("cloud_enabled", false)
    var cloudBase by str("cloud_base", DEFAULT_CLOUD)
    var cloudAppId by str("cloud_app_id", "")
    var cloudAppSecret by str("cloud_app_secret", "")
    var cloudEmail by str("cloud_email", "")
    var cloudPasswordSha by str("cloud_password_sha", "")

    val configured get() = loggerIp.isNotBlank() && loggerSerial > 0
    val cloudReady get() = cloudEnabled && cloudAppId.isNotBlank() && cloudAppSecret.isNotBlank() &&
        cloudEmail.isNotBlank() && cloudPasswordSha.isNotBlank() && isDeyeCloud(cloudBase)

    fun thresholds(): List<Int> =
        lowSocThresholds.split(',', ';').mapNotNull { it.trim().toIntOrNull() }.filter { it in 1..99 }
            .distinct().sortedDescending()

    /** Службові значення (токен хмари, стан) — окремо від налаштувань користувача. */
    fun kv(key: String): String? = p.getString("kv_$key", null)
    fun putKv(key: String, value: String?) = p.edit().putString("kv_$key", value).apply()

    /**
     * Імпорт файлу «Зберегти у файл…» з DeyeWatch для ПК (або просто settings.json).
     * Повертає кількість застосованих параметрів.
     */
    fun importDesktop(json: String): Int {
        val root = JSONObject(json)
        val s = if (root.optString("app") == "DeyeWatch" && root.has("settings")) root.getJSONObject("settings") else root
        var n = 0
        val e = p.edit()
        for (key in s.keys()) {
            val v = s.get(key)
            when (key) {
                "name", "logger_ip", "cloud_app_id", "cloud_app_secret", "cloud_email", "cloud_password_sha" ->
                    if (v is String) { e.putString(key, v); n++ }
                "cloud_base" -> if (v is String && isDeyeCloud(v)) { e.putString(key, v); n++ }
                "logger_serial" -> (v as? Number)?.let { e.putLong(key, it.toLong()); n++ }
                "logger_port", "battery_min_soc", "gen_min_power" -> (v as? Number)?.let { e.putInt(key, it.toInt()); n++ }
                "grid_min_voltage", "battery_kwh" -> (v as? Number)?.let { e.putFloat(key, it.toFloat()); n++ }
                "has_pv", "has_gen", "notify_outage", "notify_restore", "notify_low_soc", "notify_gen",
                "notify_offline", "cloud_enabled" -> (v as? Boolean)?.let { e.putBoolean(key, it); n++ }
                "low_soc_thresholds" -> (v as? JSONArray)?.let { arr ->
                    e.putString(key, (0 until arr.length()).joinToString(", ") { arr.get(it).toString() }); n++
                }
            }
        }
        e.putString("kv_cloud_token", null).putString("kv_cloud_setup", null)
        e.apply()
        return n
    }

    // ---- делегати
    private fun str(key: String, def: String) = Pref({ p.getString(key, def) ?: def }, { p.edit().putString(key, it).apply() })
    private fun int(key: String, def: Int) = Pref({ p.getInt(key, def) }, { p.edit().putInt(key, it).apply() })
    private fun long(key: String, def: Long) = Pref({ p.getLong(key, def) }, { p.edit().putLong(key, it).apply() })
    private fun bool(key: String, def: Boolean) = Pref({ p.getBoolean(key, def) }, { p.edit().putBoolean(key, it).apply() })
    private fun dbl(key: String, def: Double) =
        Pref({ p.getFloat(key, def.toFloat()).toDouble() }, { p.edit().putFloat(key, it.toFloat()).apply() })

    class Pref<T>(private val get: () -> T, private val set: (T) -> Unit) {
        operator fun getValue(thisRef: Any?, property: kotlin.reflect.KProperty<*>): T = get()
        operator fun setValue(thisRef: Any?, property: kotlin.reflect.KProperty<*>, value: T) = set(value)
    }

    companion object {
        const val DEFAULT_CLOUD = "https://eu1-developer.deyecloud.com"

        /** Ключі й пароль Deye Cloud можна надсилати лише на сервери Deye і лише через HTTPS. */
        fun isDeyeCloud(url: String): Boolean = runCatching {
            val u = URI(url.trim())
            val host = (u.host ?: "").lowercase()
            u.scheme == "https" && (host == "deyecloud.com" || host.endsWith(".deyecloud.com"))
        }.getOrDefault(false)

        fun sha256(s: String): String =
            MessageDigest.getInstance("SHA-256").digest(s.toByteArray()).joinToString("") { "%02x".format(it) }
    }
}
