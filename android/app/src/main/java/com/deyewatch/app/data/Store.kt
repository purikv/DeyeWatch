package com.deyewatch.app.data

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import java.util.Calendar

/** Історія на телефоні (SQLite): хвилинні записи та журнал відключень. Час — у секундах. */
class Store private constructor(context: Context) :
    SQLiteOpenHelper(context.applicationContext, "history.db", null, 1) {

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("""CREATE TABLE samples(ts INTEGER PRIMARY KEY, grid_ok INTEGER, v REAL, load_p REAL,
                      pv_p REAL, grid_p REAL, batt_p REAL, gen_p REAL, soc REAL, src INTEGER)""")
        db.execSQL("CREATE TABLE outages(id INTEGER PRIMARY KEY AUTOINCREMENT, start INTEGER, end INTEGER)")
        db.execSQL("CREATE INDEX outages_start ON outages(start)")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {}

    data class Sample(val ts: Long, val gridOk: Boolean, val v: Double?, val load: Double, val pv: Double,
                      val grid: Double, val batt: Double, val gen: Double, val soc: Double)

    data class Outage(val start: Long, val end: Long?)

    @Synchronized
    fun addSample(s: Sample, cloud: Boolean) {
        writableDatabase.insertWithOnConflict("samples", null, ContentValues().apply {
            put("ts", s.ts); put("grid_ok", if (s.gridOk) 1 else 0); put("v", s.v); put("load_p", s.load)
            put("pv_p", s.pv); put("grid_p", s.grid); put("batt_p", s.batt); put("gen_p", s.gen); put("soc", s.soc)
            put("src", if (cloud) 1 else 0)
        }, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun series(since: Long): List<Sample> = readableDatabase.rawQuery(
        "SELECT ts,grid_ok,v,load_p,pv_p,grid_p,batt_p,gen_p,soc FROM samples WHERE ts>=? ORDER BY ts",
        arrayOf(since.toString())).use { c ->
        buildList {
            while (c.moveToNext()) add(Sample(c.getLong(0), c.getInt(1) == 1, if (c.isNull(2)) null else c.getDouble(2),
                c.getDouble(3), c.getDouble(4), c.getDouble(5), c.getDouble(6), c.getDouble(7), c.getDouble(8)))
        }
    }

    fun lastSampleTs(): Long? = readableDatabase.rawQuery("SELECT max(ts) FROM samples", null).use {
        if (it.moveToFirst() && !it.isNull(0)) it.getLong(0) else null
    }

    fun recentDischargeW(minutes: Int): Double? = readableDatabase.rawQuery(
        "SELECT avg(batt_p) FROM samples WHERE ts>=? AND batt_p>0",
        arrayOf((now() - minutes * 60).toString())).use { if (it.moveToFirst() && !it.isNull(0)) it.getDouble(0) else null }

    // ---- відключення
    fun openOutage(): Pair<Long, Long>? = readableDatabase.rawQuery(
        "SELECT id,start FROM outages WHERE end IS NULL ORDER BY id DESC LIMIT 1", null).use {
        if (it.moveToFirst()) it.getLong(0) to it.getLong(1) else null
    }

    @Synchronized
    fun startOutage(ts: Long) {
        if (openOutage() == null) writableDatabase.execSQL("INSERT INTO outages(start,end) VALUES(?,NULL)", arrayOf<Any>(ts))
    }

    /** Закриває відкрите відключення; повертає його тривалість, с. */
    @Synchronized
    fun endOutage(ts: Long): Long? {
        val (id, start) = openOutage() ?: return null
        writableDatabase.execSQL("UPDATE outages SET end=? WHERE id=?", arrayOf<Any>(ts, id))
        return ts - start
    }

    fun lastOutageEnd(): Long? = readableDatabase.rawQuery("SELECT max(end) FROM outages", null).use {
        if (it.moveToFirst() && !it.isNull(0)) it.getLong(0) else null
    }

    /** Відключення, що перетинають [a, b], обрізані цим проміжком. */
    fun outagesBetween(a: Long, b: Long): List<Pair<Long, Long>> {
        val n = now()
        return readableDatabase.rawQuery(
            "SELECT start, coalesce(end, ?) FROM outages WHERE coalesce(end, ?)>? AND start<? ORDER BY start",
            arrayOf(n.toString(), n.toString(), a.toString(), b.toString())).use { c ->
            buildList { while (c.moveToNext()) add(maxOf(c.getLong(0), a) to minOf(c.getLong(1), b)) }
        }
    }

    fun recentOutages(limit: Int): List<Outage> = readableDatabase.rawQuery(
        "SELECT start,end FROM outages ORDER BY start DESC LIMIT ?", arrayOf(limit.toString())).use { c ->
        buildList { while (c.moveToNext()) add(Outage(c.getLong(0), if (c.isNull(1)) null else c.getLong(1))) }
    }

    data class Stats(val count: Int, val total: Long, val longest: Long, val avg: Long, val share: Double)

    fun outageStats(days: Int): Stats {
        val n = now()
        val a = n - days * 86400L
        val rows = readableDatabase.rawQuery(
            "SELECT start, coalesce(end, ?) FROM outages WHERE coalesce(end, ?)>? ORDER BY start",
            arrayOf(n.toString(), n.toString(), a.toString())).use { c ->
            buildList { while (c.moveToNext()) add(c.getLong(0) to c.getLong(1)) }
        }
        val clipped = rows.sumOf { (s, e) -> e - maxOf(s, a) }
        val full = rows.map { (s, e) -> e - s }
        return Stats(rows.size, clipped, full.maxOrNull() ?: 0, if (full.isEmpty()) 0 else full.sum() / full.size,
            clipped.toDouble() / (days * 86400.0))
    }

    /** [(початок доби, годин без світла)] за останні days днів, включно з сьогодні. */
    fun hoursPerDay(days: Int): List<Pair<Long, Double>> {
        val cal = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0); set(Calendar.SECOND, 0); set(Calendar.MILLISECOND, 0)
            add(Calendar.DAY_OF_YEAR, -(days - 1))
        }
        return List(days) {
            val a = cal.timeInMillis / 1000
            cal.add(Calendar.DAY_OF_YEAR, 1)
            val b = cal.timeInMillis / 1000
            a to outagesBetween(a, b).sumOf { (s, e) -> e - s } / 3600.0
        }
    }

    /** Матриця 7×24 (пн..нд × години): частка часу без світла; null — немає спостережень. */
    fun heatmap(days: Int): List<List<Double?>> {
        val n = now()
        val first = readableDatabase.rawQuery(
            "SELECT min(x) FROM (SELECT min(start) x FROM outages UNION SELECT min(ts) FROM samples)", null)
            .use { if (it.moveToFirst() && !it.isNull(0)) it.getLong(0) else n }
        var t = maxOf(n - days * 86400L, first)
        t -= t % 3600
        val off = Array(7) { DoubleArray(24) }
        val tot = Array(7) { DoubleArray(24) }
        val rows = outagesBetween(n - days * 86400L, n)
        val cal = Calendar.getInstance()
        while (t < n) {
            cal.timeInMillis = t * 1000
            val w = (cal.get(Calendar.DAY_OF_WEEK) + 5) % 7     // пн = 0
            val h = cal.get(Calendar.HOUR_OF_DAY)
            val end = minOf(t + 3600, n)
            tot[w][h] += (end - t).toDouble()
            for ((s, e) in rows) {
                val ov = minOf(e, end) - maxOf(s, t)
                if (ov > 0) off[w][h] += ov.toDouble()
            }
            t += 3600
        }
        return List(7) { w -> List(24) { h -> if (tot[w][h] > 0) off[w][h] / tot[w][h] else null } }
    }

    @Synchronized
    fun purge(keepDays: Int) {
        writableDatabase.execSQL("DELETE FROM samples WHERE ts<?", arrayOf<Any>(now() - keepDays * 86400L))
    }

    companion object {
        fun now() = System.currentTimeMillis() / 1000

        @Volatile private var inst: Store? = null
        fun get(context: Context): Store = inst ?: synchronized(this) { inst ?: Store(context).also { inst = it } }
    }
}
