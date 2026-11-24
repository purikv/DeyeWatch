package com.deyewatch.app

import android.app.Application
import com.deyewatch.app.monitor.Notifier

class DeyeApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Notifier.createChannels(this)
    }
}
