package com.deyewatch.app.ui

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.deyewatch.app.data.Fmt
import com.deyewatch.app.data.InverterData
import com.deyewatch.app.data.RUNNING_STATUS
import com.deyewatch.app.data.Settings
import com.deyewatch.app.data.Store
import com.deyewatch.app.monitor.LiveState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.Calendar
import kotlin.math.log10

private class OverviewData(val outages24: List<Pair<Long, Long>>, val todayOutages: List<Pair<Long, Long>>,
                           val samples: List<Store.Sample>)

@Composable
fun OverviewScreen(st: LiveState) {
    val ctx = LocalContext.current
    val s = Settings(ctx)
    val now = Store.now()
    val hist by produceState<OverviewData?>(null, st.historyVersion, st.gridOk) {
        value = withContext(Dispatchers.IO) {
            val store = Store.get(ctx)
            val n = Store.now()
            val midnight = Calendar.getInstance().apply {
                set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0); set(Calendar.SECOND, 0)
            }.timeInMillis / 1000
            OverviewData(store.outagesBetween(n - 86400, n), store.outagesBetween(midnight, n), store.series(n - 86400))
        }
    }
    val d = st.data
    val p = pal

    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        // ---- стан
        DCard {
            Row(verticalAlignment = Alignment.CenterVertically) {
                StatusDot(when (st.gridOk) { true -> p.ok; false -> p.bad; null -> p.faint })
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(when (st.gridOk) { true -> "Світло є"; false -> "Світла немає"; null -> "Підключення…" },
                        color = p.text, fontSize = 28.sp, fontWeight = FontWeight.SemiBold)
                    val sub = if (st.gridOk == null) (st.error ?: "Отримую дані з інвертора")
                    else "${if (st.gridOk) "уже" else "вже"} ${Fmt.dur(now - st.since)} · з ${Fmt.clock(st.since)}, ${Fmt.date(st.since)}" +
                        if (st.genOn) " · працює генератор" else ""
                    Text(sub, color = p.muted, fontSize = 14.sp)
                }
            }
            if (d != null) {
                val src = if (d.source == InverterData.Source.LOCAL) "Удома · напряму зі стіка"
                else "Deye Cloud · дані ${Fmt.dur(now - d.ts / 1000)} тому"
                val inv = d.runningStatus?.let { " · інвертор: ${RUNNING_STATUS[it] ?: "?"}" } ?: ""
                SmallText(src + inv)
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                SmallText("Останні 24 години")
                Spacer(Modifier.weight(1f))
                Legend(p.ok, "було"); Spacer(Modifier.width(10.dp)); Legend(p.bad, "не було")
            }
            DayStrip(now - 86400, now, hist?.outages24 ?: emptyList())
        }

        // ---- підсумок дня
        hist?.let { h ->
            val tot = h.todayOutages.sumOf { it.second - it.first }
            Insight(buildAnnotatedString {
                if (h.todayOutages.isEmpty()) append("Сьогодні відключень не було.") else {
                    append("Сьогодні світло вимикали ")
                    withStyle(SpanStyle(fontWeight = FontWeight.Bold)) {
                        append("${h.todayOutages.size} ${Fmt.plural(h.todayOutages.size, "раз", "рази", "разів")}")
                    }
                    append(", без світла — "); withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(Fmt.dur(tot)) }; append(".")
                }
                if (st.genOn) { append(" Працює "); withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append("генератор") }; append(".") }
                else if (st.gridOk == false && st.autonomyH != null) {
                    append(" Батареї вистачить ще "); withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(Fmt.autonomy(st.autonomyH)!!) }; append(".")
                } else if (s.hasPv && (d?.dayPv ?: 0.0) > 0) {
                    append(" Сонячні панелі виробили "); withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(Fmt.kwh(d!!.dayPv)) }; append(".")
                }
            })
        }

        // ---- схема потоків
        if (d != null) DCard(title = "Куди йде енергія зараз",
            hint = "Звідки зараз береться електрика і куди вона йде. Точки рухаються в напрямку потоку — що швидше, " +
                "то більша потужність. Сіра лінія — потоку немає. Червоний пунктир до мережі — світла немає.") {
            EnergyFlow(d, st.gridOk != false, s.hasPv, s.hasGen, st.genOn, st.genSince)
        }

        // ---- батарея
        if (d != null) DCard(title = "Батарея", hint = "Заряд і прогноз, на скільки його вистачить при поточному " +
            "споживанні — до мінімального заряду ${s.batteryMinSoc}%, після якого інвертор вимикає живлення.") {
            Row(verticalAlignment = Alignment.CenterVertically) {
                val soc = d.soc
                Ring(soc, if (soc <= 20) p.bad else if (soc <= 40) p.warn else p.batt,
                    if (d.battPower > 20) "розряд" else if (d.battPower < -20) "заряд" else "спокій", 112.dp)
                Spacer(Modifier.width(16.dp))
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text((if (d.battPower > 20) "Розряд " else if (d.battPower < -20) "Заряд " else "") + Fmt.power(kotlin.math.abs(d.battPower)),
                        color = p.text, fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
                    val a = Fmt.autonomy(st.autonomyH)
                    Text(when {
                        a != null -> "Вистачить $a\nдо ${s.batteryMinSoc}% при поточному споживанні"
                        d.battPower < -20 -> "Батарея заряджається"
                        else -> ""
                    }, color = p.muted, fontSize = 14.sp)
                    if (d.battVoltage != null) SmallText("%.1f В · батарея %.0f °C · інвертор %.0f °C".format(
                        d.battVoltage, d.battTemp ?: 0.0, d.dcTemp ?: 0.0))
                }
            }
        }

        // ---- енергія за сьогодні
        if (d?.dayLoad != null) DCard(title = "Сьогодні", hint = "Лічильники інвертора з початку доби.") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (s.hasPv) Tile("Сонце", Fmt.kwh(d.dayPv), "", p.pv, "sun")
                Tile("Спожито", Fmt.kwh(d.dayLoad), "", p.load, "home")
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Tile("З мережі", Fmt.kwh(d.dayBought), "", p.grid, "grid")
                Tile("Розряд бат.", Fmt.kwh(d.dayBattDis), "", p.batt, "battery")
            }
        }

        // ---- графік
        hist?.let { h ->
            DCard(title = "Потужність за 24 години", hint = "Споживання, сонце, мережа й генератор за добу. " +
                "Торкніться графіка й ведіть пальцем, щоб побачити значення. Червоні ділянки — відключення.") {
                val series = buildList {
                    add(Series("Дім", p.load, h.samples.map { it.ts to it.load }, fill = true))
                    if (s.hasPv) add(Series("Сонце", p.pv, h.samples.map { it.ts to it.pv }, fill = true))
                    add(Series("Мережа", p.grid, h.samples.map { it.ts to it.grid }))
                    if (s.hasGen) add(Series("Генератор", p.gen, h.samples.map { it.ts to it.gen }))
                }
                LineChart(series, now - 86400, now, h.outages24,
                    yFmt = { if (kotlin.math.abs(it) >= 1000) "%.1fк".format(it / 1000) else "%d".format(it.toInt()) },
                    valueFmt = { Fmt.power(it) })
            }
        }
        Spacer(Modifier.height(8.dp))
    }
}

// --------------------------------------------------------------------- схема потоків енергії
@Composable
fun EnergyFlow(d: InverterData, gridOk: Boolean, hasPv: Boolean, hasGen: Boolean, genOn: Boolean, genSince: Long) {
    val tm = rememberTextMeasurer()
    val p = pal
    val phase by rememberInfiniteTransition(label = "flow").animateFloat(0f, 1f,
        infiniteRepeatable(tween(2600, easing = LinearEasing), RepeatMode.Restart), label = "phase")
    Canvas(Modifier.fillMaxWidth().height(if (hasGen) 340.dp else 290.dp)) {
        val w = size.width
        val h = size.height
        val cx = w / 2
        val cy = h / 2 - 8.dp.toPx()
        val dx = minOf(w * 0.33f, 150.dp.toPx())
        val dy = h * 0.32f
        val r = 26.dp.toPx()
        val nodes = mutableMapOf("pv" to Offset(cx, cy - dy), "grid" to Offset(cx - dx, cy),
            "home" to Offset(cx + dx, cy), "batt" to Offset(cx, cy + dy))
        if (hasGen) { nodes["grid"] = Offset(cx - dx, cy - 58.dp.toPx()); nodes["gen"] = Offset(cx - dx, cy + 58.dp.toPx()) }
        val center = Offset(cx, cy)
        // (потужність, напрямок: +1 до інвертора / −1 від інвертора, колір)
        val flows = buildMap {
            put("grid", Triple(if (gridOk) kotlin.math.abs(d.gridPower) else 0.0, if (d.gridPower > 0) 1 else -1, p.grid))
            put("batt", Triple(kotlin.math.abs(d.battPower), if (d.battPower > 0) 1 else -1, p.batt))
            put("home", Triple(d.loadPower, -1, p.load))
            if (hasPv) put("pv", Triple(d.pvPower, 1, p.pv))
            if (hasGen) put("gen", Triple(d.genPower, 1, p.gen))
        }
        for ((k, f) in flows) {
            val a = nodes.getValue(k)
            val (pw, sign, col) = f
            val active = pw >= 15
            if (k == "grid" && !gridOk) drawLine(p.bad.copy(alpha = 0.6f), a, center, 2.dp.toPx(),
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 8f)))
            else drawLine(if (active) col.copy(alpha = 0.5f) else p.border, a, center,
                (if (active) 3 else 2).dp.toPx(), StrokeCap.Round)
            if (active) {
                val speed = 1 + minOf(2.5, maxOf(0.0, log10(maxOf(pw, 10.0)) - 1.5)).toFloat()
                for (i in 0 until 3) {
                    val fr = (phase * speed + i / 3f) % 1f
                    val pt = if (sign < 0) center + (a - center) * fr else a + (center - a) * fr
                    drawCircle(col, 4.dp.toPx(), pt)
                }
            }
        }
        drawRoundRect(p.surface2, Offset(cx - 22.dp.toPx(), cy - 22.dp.toPx()), Size(44.dp.toPx(), 44.dp.toPx()),
            CornerRadius(12.dp.toPx()))
        drawGlyph("bolt", Offset(cx - 11.dp.toPx(), cy - 11.dp.toPx()), 22.dp.toPx(), p.accent)
        val socCol = if (d.soc <= 20) p.bad else if (d.soc <= 40) p.warn else p.batt
        data class Info(val icon: String, val col: Color, val title: String, val value: String, val sub: String)
        val info = buildMap {
            if (hasPv) put("pv", Info("sun", p.pv, "Сонячні панелі", Fmt.power(d.pvPower), if (d.pvPower >= 15) "генерують" else "не генерують"))
            put("grid", Info("grid", if (gridOk) p.grid else p.bad, "Мережа", if (gridOk) Fmt.power(kotlin.math.abs(d.gridPower)) else "Немає світла",
                if (!gridOk) (if (genOn) "живлення від генератора" else "живлення від батареї")
                else "${d.gridVoltage.toInt()} В · " + when { d.gridPower >= 15 -> "беремо"; d.gridPower <= -15 -> "віддаємо"; else -> "без обміну" }))
            put("home", Info("home", p.load, "Дім", Fmt.power(d.loadPower), "споживає"))
            put("batt", Info("battery", socCol, "Батарея ${d.soc.toInt()}%", Fmt.power(kotlin.math.abs(d.battPower)),
                when { d.battPower >= 15 -> "розряджається"; d.battPower <= -15 -> "заряджається"; else -> "у спокої" }))
            if (hasGen) put("gen", Info("gen", p.gen, "Генератор", if (genOn || d.genPower >= 15) Fmt.power(d.genPower) else "Вимкнений",
                if (genOn && genSince > 0) "працює ${Fmt.dur(Store.now() - genSince)}" else "порт GEN"))
        }
        for ((k, inf) in info) {
            val a = nodes.getValue(k)
            drawCircle(p.surface, r, a)
            drawCircle(inf.col.copy(alpha = 0.12f), r - 2, a)
            drawCircle(inf.col, r, a, style = Stroke(2.dp.toPx()))
            drawGlyph(inf.icon, Offset(a.x - 12.dp.toPx(), a.y - 12.dp.toPx()), 24.dp.toPx(), inf.col,
                if (inf.icon == "battery") d.soc else null)
            val t1 = tm.measure(inf.title, TextStyle(color = p.muted, fontSize = 11.sp))
            val t2 = tm.measure(inf.value, TextStyle(color = if (inf.col == p.bad) p.bad else p.text, fontSize = 15.sp, fontWeight = FontWeight.SemiBold))
            val t3 = tm.measure(inf.sub, TextStyle(color = p.faint, fontSize = 10.sp))
            if (k == "grid" || k == "home" || k == "gen") {           // підпис під вузлом
                var y = a.y + r + 4.dp.toPx()
                for (t in listOf(t1, t2, t3)) { drawText(t, topLeft = Offset(a.x - t.size.width / 2, y)); y += t.size.height }
            } else {                                                   // підпис праворуч
                var y = a.y - (t1.size.height + t2.size.height + t3.size.height) / 2f
                for (t in listOf(t1, t2, t3)) { drawText(t, topLeft = Offset(a.x + r + 8.dp.toPx(), y)); y += t.size.height }
            }
        }
    }
}

