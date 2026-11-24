package com.deyewatch.app.ui

import android.Manifest
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.deyewatch.app.data.Settings
import com.deyewatch.app.monitor.Hub
import com.deyewatch.app.monitor.MonitorService

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        setContent { DeyeTheme { App() } }
    }

    override fun onResume() {
        super.onResume()
        runCatching { MonitorService.start(this) }
    }
}

private val TABS = listOf(Triple("Огляд", "overview", 0), Triple("Відключення", "bolt_off", 1), Triple("Налаштування", "gear", 2))

@Composable
private fun App() {
    val ctx = LocalContext.current
    val st by Hub.state.collectAsStateWithLifecycle()
    val s = Settings(ctx)
    var tab by rememberSaveable { mutableIntStateOf(if (s.configured || s.cloudReady) 0 else 2) }
    val notifPerm = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        MonitorService.start(ctx)
    }
    LaunchedEffect(Unit) {
        if (Build.VERSION.SDK_INT >= 33) notifPerm.launch(Manifest.permission.POST_NOTIFICATIONS)
    }
    val p = pal
    Scaffold(containerColor = p.bg, bottomBar = {
        NavigationBar(containerColor = p.surface) {
            for ((label, icon, i) in TABS) NavigationBarItem(selected = tab == i, onClick = { tab = i },
                icon = { Glyph(icon, if (tab == i) p.accent else p.muted, 22.dp) },
                label = { Text(label, fontSize = 12.sp) },
                colors = NavigationBarItemDefaults.colors(selectedTextColor = p.accent, unselectedTextColor = p.muted,
                    indicatorColor = p.insight))
        }
    }) { pad ->
        Column(Modifier.fillMaxSize().background(p.bg).padding(pad).verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp)) {
            Row(Modifier.statusBarsPadding().padding(top = 8.dp, bottom = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(TABS[tab].first, color = p.text, fontSize = 26.sp, fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f))
                if (tab == 0) Text(s.name, color = p.faint, fontSize = 14.sp)
            }
            when (tab) {
                0 -> if (st.data == null && !s.configured && !s.cloudReady) Welcome { tab = 2 } else OverviewScreen(st)
                1 -> OutagesScreen(st)
                else -> SettingsScreen()
            }
        }
    }
}

@Composable
private fun Welcome(onSetup: () -> Unit) {
    DCard(title = "Ласкаво просимо до DeyeWatch") {
        Text("Застосунок стежить за гібридним інвертором Deye й одразу повідомляє, коли зникає чи з'являється світло. " +
            "Удома дані йдуть напряму з WiFi-стіка, поза домом — з Deye Cloud.", color = pal.muted, fontSize = 14.sp)
        Text("Щоб почати, в налаштуваннях натисніть «Знайти автоматично» (у домашній мережі Wi-Fi) або імпортуйте " +
            "файл налаштувань з DeyeWatch для ПК.", color = pal.muted, fontSize = 14.sp)
        androidx.compose.material3.Button(onClick = onSetup) { Text("Відкрити налаштування") }
    }
}
