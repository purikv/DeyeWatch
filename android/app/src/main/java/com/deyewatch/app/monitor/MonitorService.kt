package com.deyewatch.app.monitor

import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.deyewatch.app.data.Settings
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Фонове стеження: сервіс переднього плану з постійним сповіщенням (так вимагає Android). */
class MonitorService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var job: Job? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val n = Notifier.monitorNotification(this, Hub.state.value.status, Hub.state.value.gridOk == false)
        ServiceCompat.startForeground(this, Notifier.ID_MONITOR, n,
            if (Build.VERSION.SDK_INT >= 34) ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE else 0)
        if (job?.isActive != true) {
            job = scope.launch {
                val m = Monitor(applicationContext)
                while (true) {
                    // збій одного циклу не має зупиняти стеження
                    runCatching { m.run() }.onFailure { if (it is kotlinx.coroutines.CancellationException) throw it }
                    delay(10_000)
                }
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        scope.cancel()
        Hub.update { it.copy(running = false) }
        super.onDestroy()
    }

    companion object {
        fun start(ctx: Context) {
            if (!Settings(ctx).monitorEnabled) return
            ContextCompat.startForegroundService(ctx, Intent(ctx, MonitorService::class.java))
        }

        fun stop(ctx: Context) = ctx.stopService(Intent(ctx, MonitorService::class.java))
    }
}
