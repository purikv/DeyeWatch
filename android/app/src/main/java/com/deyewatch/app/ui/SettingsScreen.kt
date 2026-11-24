package com.deyewatch.app.ui

import android.annotation.SuppressLint
import android.content.Intent
import android.net.Uri
import android.os.PowerManager
import android.provider.Settings as AndroidSettings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.deyewatch.app.BuildConfig
import com.deyewatch.app.data.DeyeCloud
import com.deyewatch.app.data.Fmt
import com.deyewatch.app.data.Settings
import com.deyewatch.app.data.SolarmanClient
import com.deyewatch.app.data.discoverLoggers
import com.deyewatch.app.monitor.MonitorService
import com.deyewatch.app.monitor.Net
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun SettingsScreen() {
    val ctx = LocalContext.current
    val s = remember { Settings(ctx) }
    val scope = rememberCoroutineScope()
    var rev by remember { mutableStateOf(0) }          // перемальовує форму після імпорту
    val p = pal

    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        key(rev) {
            // ---- підключення
            var ip by remember { mutableStateOf(s.loggerIp) }
            var sn by remember { mutableStateOf(if (s.loggerSerial > 0) s.loggerSerial.toString() else "") }
            var connMsg by remember { mutableStateOf("") }
            DCard(title = "Підключення до інвертора") {
                Note("Удома телефон читає дані напряму з WiFi-стіка інвертора. Найпростіше — «Знайти автоматично» " +
                    "(телефон має бути в домашній мережі Wi-Fi).")
                Field("IP-адреса стіка", ip, "Знаходиться автоматично; видно також у списку клієнтів роутера.",
                    KeyboardType.Uri) { ip = it.trim(); s.loggerIp = ip }
                Field("Серійний номер стіка (SN)", sn, "10 цифр на наклейці WiFi-стіка (не інвертора).",
                    KeyboardType.Number) { v -> sn = v.filter { it.isDigit() }; s.loggerSerial = sn.toLongOrNull() ?: 0 }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = {
                        connMsg = "Шукаю стік у мережі… (до 10 с)"
                        scope.launch {
                            val ips = Net.localIpv4s(ctx)
                            val r = withContext(Dispatchers.IO) { runCatching { discoverLoggers(ips) } }
                            val f = r.getOrNull()?.firstOrNull()
                            connMsg = when {
                                ips.isEmpty() -> "✗ Телефон не в мережі Wi-Fi"
                                f == null -> "✗ Стік не знайдено. Перевірте, що телефон у тій самій мережі Wi-Fi."
                                else -> {
                                    ip = f.ip; sn = f.serial.toString(); s.loggerIp = f.ip; s.loggerSerial = f.serial
                                    MonitorService.start(ctx)
                                    "✓ Знайдено: ${f.ip}, SN ${f.serial}"
                                }
                            }
                        }
                    }) { Text("Знайти автоматично") }
                    OutlinedButton(onClick = {
                        connMsg = "Перевіряю…"
                        scope.launch {
                            val r = withContext(Dispatchers.IO) {
                                runCatching { SolarmanClient(s.loggerIp, s.loggerSerial, s.loggerPort).readAll() }
                            }
                            connMsg = r.fold({ "✓ Є зв'язок: мережа ${it.gridVoltage.toInt()} В, батарея ${it.soc.toInt()}%, " +
                                "споживання ${Fmt.power(it.loadPower)}" }, { "✗ ${it.message ?: "немає зв'язку"}" })
                        }
                    }) { Text("Перевірити") }
                }
                if (connMsg.isNotEmpty()) SmallText(connMsg, p.muted)
            }

            // ---- батарея
            DCard(title = "Батарея, сонце, генератор") {
                Note("Від цих значень залежить прогноз «батареї вистачить на…».")
                NumField("Ємність батареї, кВт·год", s.batteryKwh.toString(), "Повна ємність усіх батарей разом.") {
                    it.replace(',', '.').toDoubleOrNull()?.let { v -> s.batteryKwh = v } }
                NumField("Мінімальний заряд, %", s.batteryMinSoc.toString(), "Нижче цього заряду інвертор вимикає живлення (Battery Shutdown).") {
                    it.toIntOrNull()?.let { v -> s.batteryMinSoc = v.coerceIn(0, 90) } }
                Field("Попереджати при заряді, %", s.lowSocThresholds, "Пороги для сповіщень під час відключення, через кому.") {
                    s.lowSocThresholds = it }
                Toggle("Є сонячні панелі", s.hasPv) { s.hasPv = it }
                Toggle("Є генератор (порт GEN)", s.hasGen, "Вмикається само, щойно інвертор уперше побачить генератор.") { s.hasGen = it }
            }

            // ---- сповіщення
            DCard(title = "Сповіщення") {
                Toggle("Стежити у фоні", s.monitorEnabled,
                    "Постійне сповіщення «DeyeWatch стежить» — так Android дозволяє застосунку працювати у фоні.") {
                    s.monitorEnabled = it
                    if (it) MonitorService.start(ctx) else MonitorService.stop(ctx)
                }
                Toggle("Світло зникло", s.notifyOutage) { s.notifyOutage = it }
                Toggle("Світло з'явилося", s.notifyRestore) { s.notifyRestore = it }
                Toggle("Низький заряд батареї", s.notifyLowSoc) { s.notifyLowSoc = it }
                Toggle("Генератор запущено / зупинено", s.notifyGen) { s.notifyGen = it }
                Toggle("Немає даних від інвертора", s.notifyOffline, "Якщо понад 20 хв немає даних ні зі стіка, ні з хмари.") {
                    s.notifyOffline = it }
                BatteryOptimization()
            }

            // ---- хмара
            var cloudMsg by remember { mutableStateOf("") }
            var appId by remember { mutableStateOf(s.cloudAppId) }
            var secret by remember { mutableStateOf(s.cloudAppSecret) }
            var email by remember { mutableStateOf(s.cloudEmail) }
            var pass by remember { mutableStateOf("") }
            var passKey by remember { mutableStateOf(0) }
            DCard(title = "Deye Cloud (поза домом)") {
                Note("Коли ви не вдома, телефон бере дані з Deye Cloud (із затримкою 5–15 хв). App ID і App Secret " +
                    "створюються на developer.deyecloud.com тим самим акаунтом, що й у застосунку Deye Cloud. " +
                    "Пароль зберігається лише як хеш SHA-256. Найпростіше — імпортувати налаштування з DeyeWatch для ПК.")
                Toggle("Використовувати Deye Cloud", s.cloudEnabled) { s.cloudEnabled = it }
                Field("App ID", appId, null, KeyboardType.Number) { appId = it.trim(); s.cloudAppId = appId }
                Field("App Secret", secret, null, secret = true) { secret = it.trim(); s.cloudAppSecret = secret }
                Field("Email акаунта Deye Cloud", email, null, KeyboardType.Email) { email = it.trim(); s.cloudEmail = email }
                androidx.compose.runtime.key(passKey) {
                    Field("Пароль", pass, if (s.cloudPasswordSha.isNotBlank()) "Збережено. Введіть новий, щоб змінити." else null,
                        secret = true) { pass = it }
                }
                OutlinedButton(onClick = {
                    if (pass.isNotEmpty()) { s.cloudPasswordSha = Settings.sha256(pass); pass = ""; passKey++ }
                    s.putKv("cloud_token", null); s.putKv("cloud_setup", null)
                    cloudMsg = "Підключаюся до Deye Cloud…"
                    scope.launch {
                        val r = withContext(Dispatchers.IO) { runCatching { DeyeCloud(s).latest() } }
                        cloudMsg = r.fold({ d -> if (d == null) "✓ Підключено, але свіжих даних у хмарі немає"
                            else "✓ Підключено: мережа ${d.gridVoltage.toInt()} В, батарея ${d.soc.toInt()}%" },
                            { "✗ ${it.message ?: "немає зв'язку"}" })
                    }
                }) { Text("Зберегти й перевірити") }
                if (cloudMsg.isNotEmpty()) SmallText(cloudMsg, p.muted)
            }
        }

        // ---- імпорт з ПК
        var importMsg by remember { mutableStateOf("") }
        val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
            if (uri == null) return@rememberLauncherForActivityResult
            importMsg = runCatching {
                val text = ctx.contentResolver.openInputStream(uri)!!.bufferedReader().use { it.readText() }
                val n = s.importDesktop(text)
                rev++
                MonitorService.start(ctx)
                "✓ Імпортовано налаштувань: $n"
            }.getOrElse { "✗ Це не файл налаштувань DeyeWatch" }
        }
        DCard(title = "Перенесення з комп'ютера") {
            Note("У DeyeWatch для ПК: Налаштування → Перенесення налаштувань → «Зберегти у файл…» (разом із паролями). " +
                "Перешліть файл на телефон і виберіть його тут — стік, батарея й Deye Cloud налаштуються одразу. " +
                "Після імпорту видаліть файл з телефона й месенджера.")
            Button(onClick = { picker.launch(arrayOf("application/json", "text/plain", "*/*")) }) { Text("Імпортувати файл налаштувань") }
            if (importMsg.isNotEmpty()) SmallText(importMsg, p.muted)
        }

        SmallText("DeyeWatch для Android ${BuildConfig.VERSION_NAME} · github.com/purikv/DeyeWatch")
        Spacer(Modifier.height(8.dp))
    }
}

@Composable
private fun key(k: Any, content: @Composable () -> Unit) = androidx.compose.runtime.key(k) { content() }

@Composable
private fun Note(text: String) = Text(text, color = pal.muted, fontSize = 13.sp, lineHeight = 18.sp)

@Composable
private fun Field(label: String, value: String, hint: String?, type: KeyboardType = KeyboardType.Text,
                  secret: Boolean = false, onChange: (String) -> Unit) {
    var v by remember { mutableStateOf(value) }
    OutlinedTextField(value = v, onValueChange = { v = it; onChange(it) }, label = { Text(label) },
        supportingText = hint?.let { { Text(it, fontSize = 12.sp) } }, singleLine = true,
        visualTransformation = if (secret) PasswordVisualTransformation() else VisualTransformation.None,
        keyboardOptions = KeyboardOptions(keyboardType = if (secret) KeyboardType.Password else type),
        colors = OutlinedTextFieldDefaults.colors(focusedTextColor = pal.text, unfocusedTextColor = pal.text,
            unfocusedBorderColor = pal.border, focusedLabelColor = pal.accent, unfocusedLabelColor = pal.muted,
            unfocusedSupportingTextColor = pal.faint, focusedSupportingTextColor = pal.faint),
        modifier = Modifier.fillMaxWidth())
}

@Composable
private fun NumField(label: String, value: String, hint: String?, onChange: (String) -> Unit) =
    Field(label, value, hint, KeyboardType.Decimal, onChange = onChange)

@Composable
private fun Toggle(label: String, value: Boolean, hint: String? = null, onChange: (Boolean) -> Unit) {
    var v by remember { mutableStateOf(value) }
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.weight(1f)) {
            Text(label, color = pal.text, fontSize = 15.sp)
            if (hint != null) Text(hint, color = pal.faint, fontSize = 12.sp, lineHeight = 16.sp)
        }
        Spacer(Modifier.width(12.dp))
        Switch(checked = v, onCheckedChange = { v = it; onChange(it) },
            colors = SwitchDefaults.colors(checkedTrackColor = pal.accent))
    }
}

/** Android може «приспати» фоновий застосунок — просимо дозволу працювати без обмежень. */
@SuppressLint("BatteryLife")
@Composable
private fun BatteryOptimization() {
    val ctx = LocalContext.current
    val pm = ctx.getSystemService(PowerManager::class.java)
    var ignoring by remember { mutableStateOf(pm.isIgnoringBatteryOptimizations(ctx.packageName)) }
    if (ignoring) {
        SmallText("✓ Обмеження батареї для DeyeWatch вимкнено — стеження не переривається.", pal.ok)
    } else {
        Note("Щоб Android не зупиняв стеження, дозвольте DeyeWatch працювати без обмежень батареї.")
        Button(onClick = {
            ctx.startActivity(Intent(AndroidSettings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                Uri.parse("package:${ctx.packageName}")))
            ignoring = pm.isIgnoringBatteryOptimizations(ctx.packageName)
        }, colors = ButtonDefaults.buttonColors(containerColor = pal.warn)) { Text("Дозволити роботу у фоні") }
    }
}
