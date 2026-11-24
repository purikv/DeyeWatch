package com.deyewatch.app.monitor

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.deyewatch.app.R
import com.deyewatch.app.ui.MainActivity

object Notifier {
    const val CH_ALERTS = "alerts"
    const val CH_MONITOR = "monitor"
    const val ID_MONITOR = 1

    fun createChannels(ctx: Context) {
        val nm = ctx.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CH_ALERTS, "Світло й батарея",
            NotificationManager.IMPORTANCE_HIGH).apply {
            description = "Світло зникло / з'явилося, низький заряд, генератор, втрата зв'язку"
        })
        nm.createNotificationChannel(NotificationChannel(CH_MONITOR, "Фонове стеження",
            NotificationManager.IMPORTANCE_LOW).apply {
            description = "Постійне сповіщення, поки DeyeWatch стежить за інвертором"
            setShowBadge(false)
        })
    }

    private fun openApp(ctx: Context) = PendingIntent.getActivity(ctx, 0,
        Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

    fun monitorNotification(ctx: Context, text: String, outage: Boolean?): Notification =
        NotificationCompat.Builder(ctx, CH_MONITOR)
            .setSmallIcon(R.drawable.ic_stat_bolt)
            .setContentTitle(text)
            .setContentText("DeyeWatch стежить за інвертором")
            .setColor(if (outage == true) 0xFFE5484D.toInt() else 0xFF30A46C.toInt())
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setContentIntent(openApp(ctx))
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .build()

    fun updateMonitor(ctx: Context, text: String, outage: Boolean?) = post(ctx, ID_MONITOR, monitorNotification(ctx, text, outage))

    /** Сповіщення про подію. lines — рядки «підпис: значення», показуються в розгорнутому вигляді. */
    fun alert(ctx: Context, id: Int, title: String, text: String, lines: List<String>, color: Int, sticky: Boolean = false) {
        val style = NotificationCompat.InboxStyle().setBigContentTitle(title)
        lines.forEach { style.addLine(it) }
        val n = NotificationCompat.Builder(ctx, CH_ALERTS)
            .setSmallIcon(R.drawable.ic_stat_bolt)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(style)
            .setColor(color)
            .setCategory(NotificationCompat.CATEGORY_STATUS)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(!sticky)
            .setContentIntent(openApp(ctx))
            .build()
        post(ctx, id, n)
    }

    fun cancel(ctx: Context, id: Int) = NotificationManagerCompat.from(ctx).cancel(id)

    private fun post(ctx: Context, id: Int, n: Notification) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        NotificationManagerCompat.from(ctx).notify(id, n)
    }

    const val ID_GRID = 10
    const val ID_SOC = 11
    const val ID_GEN = 12
    const val ID_OFFLINE = 13
    const val RED = 0xFFE5484D.toInt()
    const val GREEN = 0xFF30A46C.toInt()
    const val AMBER = 0xFFF5A524.toInt()
    const val BROWN = 0xFFB5651D.toInt()
    const val GREY = 0xFF8B8D98.toInt()
}
