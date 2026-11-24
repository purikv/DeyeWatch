package com.deyewatch.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.deyewatch.app.data.Fmt
import com.deyewatch.app.data.Store
import com.deyewatch.app.monitor.LiveState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private class OutageData(val stats: Store.Stats, val perDay: List<Pair<Long, Double>>, val heat: List<List<Double?>>,
                         val recent: List<Store.Outage>)

@Composable
fun OutagesScreen(st: LiveState) {
    val ctx = LocalContext.current
    var range by rememberSaveable { mutableIntStateOf(1) }
    val days = listOf(7, 30, 90)[range]
    val data by produceState<OutageData?>(null, days, st.gridOk, st.historyVersion / 10) {
        value = withContext(Dispatchers.IO) {
            val store = Store.get(ctx)
            OutageData(store.outageStats(days), store.hoursPerDay(minOf(days, 30)), store.heatmap(days), store.recentOutages(40))
        }
    }
    val p = pal
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Період", color = p.muted, fontSize = 14.sp, modifier = Modifier.weight(1f))
            Segmented(listOf("7 днів", "30 днів", "90 днів"), range) { range = it }
        }
        val d = data ?: return@Column
        val s = d.stats
        Insight(buildAnnotatedString {
            if (s.count == 0) append("За останні $days днів відключень не зафіксовано.") else {
                append("За $days днів світло вимикали ")
                withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append("${s.count} ${Fmt.plural(s.count, "раз", "рази", "разів")}") }
                append(" — разом ")
                withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(Fmt.dur(s.total)) }
                append(" без світла (${"%.0f".format(s.share * 100)}% часу).")
                worstWindow(d.heat)?.let { (w, h) ->
                    append(" Найчастіше світла немає в ")
                    withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append("${Fmt.WDAYS_IN[w]} з %02d:00 до %02d:00".format(h, h + 3)) }
                    append(".")
                }
            }
        }, icon = "bolt_off")
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Tile("Відключень", "${s.count}", "%.1f на добу".format(s.count.toDouble() / days), p.bad, "bolt_off",
                "Скільки разів зникало світло за період. Короткі «блимання» не рахуються.")
            Tile("Без світла", Fmt.dur(s.total), "%.0f%% часу".format(s.share * 100), p.warn, "clock",
                "Сумарний час без світла за період і яка це частка від усього часу.")
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Tile("Найдовше", if (s.count > 0) Fmt.dur(s.longest) else "—", "", p.orange, "clock",
                "Найдовше безперервне відключення за період.")
            Tile("В середньому", if (s.count > 0) Fmt.dur(s.avg) else "—", "", p.accent, "chart",
                "Скільки в середньому триває одне відключення.")
        }
        DCard(title = "Годин без світла по днях", hint = "Кожен стовпчик — один день. Торкніться стовпчика, щоб побачити дату й значення.") {
            BarChart(d.perDay, p.bad, { if (it % 1.0 == 0.0) "${it.toInt()} год" else "%.1f год".format(it) })
        }
        DCard(title = "Коли найчастіше вимикають", hint = "Рядки — дні тижня, стовпці — години. Що червоніша клітинка, " +
            "то частіше в цей час немає світла. Допомагає побачити графік відключень.") {
            Heatmap(d.heat)
        }
        DCard(title = "Останні відключення") {
            if (d.recent.isEmpty()) SmallText("Відключень ще не зафіксовано")
            d.recent.forEachIndexed { i, o ->
                if (i > 0) HorizontalDivider(color = p.gridLine)
                Row(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                    Text(Fmt.date(o.start), color = p.text, fontSize = 14.sp, modifier = Modifier.weight(1.4f))
                    Text("${Fmt.clock(o.start)}–${o.end?.let { Fmt.clock(it) } ?: "…"}", color = p.muted, fontSize = 14.sp,
                        modifier = Modifier.weight(1.2f))
                    Text(o.end?.let { Fmt.dur(it - o.start) } ?: "триває", color = if (o.end == null) p.bad else p.text,
                        fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                }
            }
        }
        Spacer(Modifier.height(8.dp))
    }
}

/** День тижня й 3 години поспіль, коли найчастіше немає світла (якщо в середньому понад 30 % часу). */
private fun worstWindow(heat: List<List<Double?>>): Pair<Int, Int>? {
    var best = -1.0
    var at: Pair<Int, Int>? = null
    for (w in 0 until 7) for (h in 0 until 22) {
        val v = (0 until 3).mapNotNull { heat[w][h + it] }
        if (v.size == 3 && v.sum() > best) { best = v.sum(); at = w to h }
    }
    return if (best > 0.9) at else null
}
