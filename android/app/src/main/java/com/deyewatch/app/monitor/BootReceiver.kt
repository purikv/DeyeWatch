package com.deyewatch.app.monitor

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Після перезавантаження телефону або оновлення застосунку — знову стежимо. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED || intent.action == Intent.ACTION_MY_PACKAGE_REPLACED) {
            runCatching { MonitorService.start(context) }
        }
    }
}
