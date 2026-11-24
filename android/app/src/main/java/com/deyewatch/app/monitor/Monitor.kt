package com.deyewatch.app.monitor

import android.content.Context
import com.deyewatch.app.data.CloudException
import com.deyewatch.app.data.DeyeCloud
import com.deyewatch.app.data.Fmt
import com.deyewatch.app.data.InverterData
import com.deyewatch.app.data.Settings
import com.deyewatch.app.data.SolarmanClient
import com.deyewatch.app.data.Store
import com.deyewatch.app.data.discoverLoggers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlin.coroutines.coroutineContext

/**
 * Логіка стеження — та сама, що в DeyeWatch для ПК:
 *  • удома (Wi-Fi) — опитування стіка кожні 10 с, зміна стану підтверджується 2 опитуваннями поспіль;
 *  • поза домом або коли стік не відповідає — останні дані з Deye Cloud кожні 5 хв;
 *  • сповіщення: світло зникло / з'явилося, низький заряд, генератор, немає даних.
 */
class Monitor(private val ctx: Context) {
    private val s = Settings(ctx)
    private val store = Store.get(ctx)

    private var gridOk: Boolean? = null
    private var since = Store.now()
    private var pendingOk: Boolean? = null
    private var pendingTs = 0L
    private var pendingN = 0
    private val socWarned = HashSet<Int>()
    private var genOn = false
    private var genSince = 0L
    private var genPending = 0
    private var localFails = 0
    private var lastCloudPoll = 0L
    private var lastCloudTs = 0L
    private var lastData = 0L
    private var offlineNotified = false
    private var minute = -1L
    private val acc = ArrayList<InverterData>()
    private var lastPurge = 0L
    private var fresh = true          // перші дані після запуску сервісу

    init {
        val open = store.openOutage()
        if (s.kv("grid_known") != null) gridOk = open == null
        since = open?.second ?: store.lastOutageEnd() ?: (s.kv("since")?.toLongOrNull() ?: Store.now())
        genOn = s.kv("gen_on") == "1"
        genSince = s.kv("gen_since")?.toLongOrNull() ?: 0
    }

    suspend fun run() {
        while (coroutineContext.isActive) {
            val wait = tick()
            delay(wait)
        }
    }

    /** Один цикл; повертає паузу до наступного, мс. */
    private suspend fun tick(): Long {
        if (!s.configured && !s.cloudReady) {
            if (Net.onLocalNetwork(ctx)) firstSetup()
            if (!s.configured) {
                Hub.update { it.copy(status = "Потрібне налаштування", error = "Вкажіть стік або Deye Cloud у налаштуваннях", running = true) }
                return 15_000
            }
        }
        var d: InverterData? = null
        var err: String? = null
        if (s.configured && Net.onLocalNetwork(ctx)) {
            d = readLocal()
            if (d == null) {
                localFails++
                err = "WiFi-стік не відповідає"
                if (localFails % 6 == 3) relocate()
            } else localFails = 0
        }
        val now = System.currentTimeMillis()
        if (d == null && s.cloudReady && now - lastCloudPoll >= 5 * 60_000) {
            lastCloudPoll = now
            try {
                val c = DeyeCloud(s).latest()
                if (c != null && c.ts > lastCloudTs) { lastCloudTs = c.ts; d = c }
                else if (c == null) err = "у хмарі немає свіжих даних"
            } catch (e: CloudException) {
                err = "Deye Cloud: ${e.message}"
            } catch (e: Exception) {
                err = "немає зв'язку з Deye Cloud"
            }
        }
        if (d != null) {
            lastData = now
            process(d)
            if (offlineNotified) {
                offlineNotified = false
                Notifier.cancel(ctx, Notifier.ID_OFFLINE)
            }
        } else {
            val quietMin = (now - lastData) / 60_000
            if (lastData > 0 && quietMin >= 20 && !offlineNotified && s.notifyOffline) {
                offlineNotified = true
                Notifier.alert(ctx, Notifier.ID_OFFLINE, "Немає даних від інвертора",
                    "${s.name} · ${err ?: "немає зв'язку"}", listOf("Без даних уже: ${Fmt.dur(quietMin * 60)}"), Notifier.GREY)
            }
            Hub.update { it.copy(error = err, running = true) }
        }
        if (now - lastPurge > 6 * 3600_000) { lastPurge = now; runCatching { store.purge(90) } }
        val local = d?.source == InverterData.Source.LOCAL
        return if (local) 10_000 else if (s.configured && Net.onLocalNetwork(ctx)) 20_000 else 30_000
    }

    private fun readLocal(): InverterData? {
        val c = SolarmanClient(s.loggerIp, s.loggerSerial, s.loggerPort)
        return try {
            c.readAll()
        } catch (e: java.io.IOException) {
            Thread.sleep(1500)              // стік міг бути зайнятий іншим клієнтом
            runCatching { c.readAll() }.getOrNull()
        } catch (e: Exception) {
            null
        }
    }

    private fun firstSetup() {
        runCatching { discoverLoggers(Net.localIpv4s(ctx)).firstOrNull() }.getOrNull()?.let {
            s.loggerIp = it.ip
            s.loggerSerial = it.serial
        }
    }

    /** Стік міг отримати нову IP-адресу — шукаємо за серійним номером. */
    private fun relocate() {
        runCatching { discoverLoggers(Net.localIpv4s(ctx)) }.getOrNull()
            ?.firstOrNull { it.serial == s.loggerSerial && it.ip != s.loggerIp }?.let { s.loggerIp = it.ip }
    }

    private fun process(d: InverterData) {
        val ts = d.ts / 1000
        val cloud = d.source == InverterData.Source.CLOUD
        val ok = d.gridVoltage >= s.gridMinVoltage
        val tag = if (cloud) " (за даними хмари)" else ""

        if (fresh && gridOk != null && ok != gridOk) {
            // стан змінився, поки стеження не працювало (телефон вимкнений, сервіс зупинений):
            // точного часу не знаємо — рахуємо від останніх відомих даних, а не від моменту запуску
            val last = store.lastSampleTs() ?: ts
            if (!ok) {
                val start = minOf(ts, maxOf(last + 60, since))
                store.startOutage(start)
                since = start
                socWarned.clear()
            } else {
                store.endOutage(maxOf(last, since))
                since = ts
            }
            gridOk = ok
            s.putKv("since", since.toString())
            pendingOk = null
        }
        fresh = false
        if (gridOk == null) {
            gridOk = ok
            s.putKv("grid_known", "1")
            if (!ok) { store.startOutage(ts); since = ts }
        } else if (ok != gridOk) {
            if (pendingOk != ok) { pendingOk = ok; pendingTs = ts; pendingN = 0 }
            pendingN++
            // з хмари точки рідкі (кожні ~5 хв) — одна точка вже достатнє підтвердження
            if (pendingN >= (if (cloud) 1 else 2)) {
                changeGrid(ok, pendingTs, d, tag)
                pendingOk = null
            }
        } else pendingOk = null

        if (gridOk == false) checkSoc(d, tag)
        if (!cloud) checkGen(d)

        val autonomy = autonomyHours(d)
        record(d)
        val state = (if (gridOk == true) "Світло є" else "Світла немає") + " · " + Fmt.dur(Store.now() - since) +
            (if (genOn) " · генератор" else "")
        Hub.update {
            it.copy(data = d, gridOk = gridOk, since = since, autonomyH = autonomy, genOn = genOn,
                genSince = genSince, status = state, error = null, running = true)
        }
        Notifier.updateMonitor(ctx, state, gridOk == false)
    }

    private fun changeGrid(ok: Boolean, ts: Long, d: InverterData, tag: String) {
        val prev = since
        gridOk = ok
        since = ts
        s.putKv("since", ts.toString())
        if (!ok) {
            store.startOutage(ts)
            socWarned.clear()
            if (s.notifyOutage) {
                val lines = mutableListOf("Світло було: ${Fmt.dur(ts - prev)}", "Заряд батареї: ${d.soc.toInt()}%",
                    "Споживання: ${Fmt.power(d.loadPower)}")
                Fmt.autonomy(autonomyHours(d))?.let { lines += "Батареї вистачить: $it" }
                Notifier.alert(ctx, Notifier.ID_GRID, "Світло зникло$tag", "${s.name} · ${Fmt.clock(ts)} · батарея ${d.soc.toInt()}%",
                    lines, Notifier.RED, sticky = true)
            }
        } else {
            val dur = store.endOutage(ts) ?: (ts - prev)
            if (s.notifyRestore) {
                Notifier.alert(ctx, Notifier.ID_GRID, "Світло з'явилося$tag",
                    "${s.name} · ${Fmt.clock(ts)} · не було ${Fmt.dur(dur)}",
                    listOf("Світла не було: ${Fmt.dur(dur)}", "Напруга: ${d.gridVoltage.toInt()} В",
                        "Заряд батареї: ${d.soc.toInt()}%"), Notifier.GREEN)
            }
        }
    }

    private fun checkSoc(d: InverterData, tag: String) {
        val crossed = s.thresholds().filter { d.soc <= it && it !in socWarned }
        if (crossed.isEmpty()) return
        socWarned += crossed
        if (!s.notifyLowSoc) return
        val lines = mutableListOf("Без світла вже: ${Fmt.dur(Store.now() - since)}", "Споживання: ${Fmt.power(d.loadPower)}")
        Fmt.autonomy(autonomyHours(d))?.let { lines += "Залишилось: $it" }
        Notifier.alert(ctx, Notifier.ID_SOC, "Заряд батареї ${d.soc.toInt()}%$tag",
            "${s.name} · нижче порогу ${crossed.min()}%", lines, if (d.soc <= 20) Notifier.RED else Notifier.AMBER)
    }

    private fun checkGen(d: InverterData) {
        val on = d.genPower >= s.genMinPower
        if (on && !s.hasGen) s.hasGen = true          // інвертор уперше показав генератор
        if (on == genOn) { genPending = 0; return }
        if (++genPending < 2) return
        genPending = 0
        val ts = d.ts / 1000
        genOn = on
        s.putKv("gen_on", if (on) "1" else "0")
        if (on) {
            genSince = ts
            s.putKv("gen_since", ts.toString())
            if (s.notifyGen) Notifier.alert(ctx, Notifier.ID_GEN, "Генератор запущено",
                "${s.name} · ${Fmt.power(d.genPower)}", listOf("Потужність: ${Fmt.power(d.genPower)}"), Notifier.BROWN)
        } else if (s.notifyGen) {
            Notifier.alert(ctx, Notifier.ID_GEN, "Генератор зупинено",
                "${s.name} · пропрацював ${Fmt.dur(ts - genSince)}", listOf("Пропрацював: ${Fmt.dur(ts - genSince)}"), Notifier.GREY)
        }
    }

    fun autonomyHours(d: InverterData): Double? {
        val cap = s.batteryKwh
        if (cap <= 0 || d.battPower < -20) return null       // заряджається — прогноз не має сенсу
        val usable = (d.soc - s.batteryMinSoc) / 100 * cap * 1000
        if (usable <= 0) return 0.0
        var w = maxOf(store.recentDischargeW(10) ?: 0.0, if (d.battPower > 0) d.battPower else 0.0)
        if (w < 30) w = d.loadPower - d.pvPower
        return if (w < 30) null else usable / w
    }

    /** Хвилинні записи: локальні опитування усереднюються за хвилину, точки з хмари пишуться як є. */
    private fun record(d: InverterData) {
        if (d.source == InverterData.Source.CLOUD) {
            store.addSample(sample(listOf(d), (d.ts / 60_000) * 60), cloud = true)
            bump()
            return
        }
        val m = (d.ts / 60_000) * 60
        if (minute >= 0 && m != minute && acc.isNotEmpty()) {
            store.addSample(sample(acc, minute), cloud = false)
            acc.clear()
            bump()
        }
        minute = m
        acc += d
    }

    private fun sample(a: List<InverterData>, ts: Long): Store.Sample {
        val ok = a.all { it.gridVoltage >= s.gridMinVoltage }
        return Store.Sample(ts, ok, if (ok) a.map { it.gridVoltage }.average() else null,
            a.map { it.loadPower }.average(), a.map { it.pvPower }.average(), a.map { it.gridPower }.average(),
            a.map { it.battPower }.average(), a.map { it.genPower }.average(), a.last().soc)
    }

    private fun bump() = Hub.update { it.copy(historyVersion = it.historyVersion + 1) }
}
