package com.deyewatch.app.data

import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

/** Форматування для інтерфейсу й сповіщень — як у DeyeWatch для ПК. */
object Fmt {
    private val MONTHS = listOf("січня", "лютого", "березня", "квітня", "травня", "червня", "липня",
        "серпня", "вересня", "жовтня", "листопада", "грудня")
    val WDAYS = listOf("пн", "вт", "ср", "чт", "пт", "сб", "нд")
    val WDAYS_IN = listOf("понеділок", "вівторок", "середу", "четвер", "п'ятницю", "суботу", "неділю")

    fun dur(sec: Long): String {
        val s = maxOf(0, sec)
        val d = s / 86400
        val h = s % 86400 / 3600
        val m = s % 3600 / 60
        return when {
            d > 0 -> "$d д $h год"
            h > 0 -> "%d год %02d хв".format(h, m)
            else -> "$m хв"
        }
    }

    fun power(w: Double?): String {
        val x = w ?: 0.0
        return if (kotlin.math.abs(x) >= 1000) "%.2f кВт".format(Locale.US, x / 1000).replace('.', ',')
        else "${Math.round(x)} Вт"
    }

    fun kwh(v: Double?) = "%.1f кВт·год".format(Locale.US, v ?: 0.0).replace('.', ',')

    fun clock(sec: Long): String = SimpleDateFormat("HH:mm", Locale.US).format(Date(sec * 1000))

    fun date(sec: Long): String {
        val c = Calendar.getInstance().apply { timeInMillis = sec * 1000 }
        val w = (c.get(Calendar.DAY_OF_WEEK) + 5) % 7
        return "${WDAYS[w]}, ${c.get(Calendar.DAY_OF_MONTH)} ${MONTHS[c.get(Calendar.MONTH)]}"
    }

    fun dayShort(sec: Long): String = SimpleDateFormat("dd.MM", Locale.US).format(Date(sec * 1000))

    fun autonomy(hours: Double?): String? = when {
        hours == null -> null
        hours > 48 -> "понад 2 доби"
        else -> "≈ " + dur((hours * 3600).toLong())
    }

    fun plural(n: Int, one: String, few: String, many: String): String {
        val a = kotlin.math.abs(n)
        return when {
            a % 10 == 1 && a % 100 != 11 -> one
            a % 10 in 2..4 && a % 100 !in 12..14 -> few
            else -> many
        }
    }
}
