package com.deyewatch.app.monitor

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import java.net.Inet4Address

object Net {
    /** Телефон у локальній мережі (Wi-Fi / Ethernet) — тоді є сенс звертатися до стіка напряму. */
    fun onLocalNetwork(ctx: Context): Boolean {
        val cm = ctx.getSystemService(ConnectivityManager::class.java) ?: return false
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
        return caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) ||
            caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)
    }

    /** IPv4-адреси телефону в локальній мережі — для автопошуку стіка в підмережі /24. */
    fun localIpv4s(ctx: Context): List<String> {
        val cm = ctx.getSystemService(ConnectivityManager::class.java) ?: return emptyList()
        return cm.allNetworks.flatMap { n ->
            val caps = cm.getNetworkCapabilities(n)
            val local = caps != null && (caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) ||
                caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET))
            if (!local) emptyList() else cm.getLinkProperties(n)?.linkAddresses.orEmpty()
                .mapNotNull { (it.address as? Inet4Address)?.hostAddress }
        }.filter { !it.startsWith("127.") && !it.startsWith("169.254.") }.distinct()
    }
}
