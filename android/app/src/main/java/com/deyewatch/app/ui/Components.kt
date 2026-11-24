package com.deyewatch.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.deyewatch.app.data.Fmt
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.log10
import kotlin.math.pow

// --------------------------------------------------------------------- базові блоки
@Composable
fun DCard(modifier: Modifier = Modifier, title: String? = null, hint: String? = null,
          content: @Composable ColumnScope.() -> Unit) {
    Column(modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(pal.surface)
        .border(1.dp, pal.border, RoundedCornerShape(16.dp)).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)) {
        if (title != null) Row(verticalAlignment = Alignment.CenterVertically) {
            Text(title, color = pal.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
            if (hint != null) { Spacer(Modifier.width(6.dp)); Hint(title, hint) }
        }
        content()
    }
}

/** Кружечок «?» — по дотику показує пояснення. */
@Composable
fun Hint(title: String, text: String) {
    var open by remember { mutableStateOf(false) }
    Box(Modifier.size(20.dp).clip(CircleShape).border(1.dp, pal.faint, CircleShape).clickable { open = true },
        contentAlignment = Alignment.Center) {
        Text("?", color = pal.faint, fontSize = 11.sp, fontWeight = FontWeight.Bold)
    }
    if (open) AlertDialog(onDismissRequest = { open = false },
        confirmButton = { TextButton(onClick = { open = false }) { Text("Зрозуміло") } },
        title = { Text(title) }, text = { Text(text) },
        containerColor = pal.surface, titleContentColor = pal.text, textContentColor = pal.muted)
}

@Composable
fun Insight(text: androidx.compose.ui.text.AnnotatedString, icon: String = "clock") {
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(pal.insight)
        .border(1.dp, pal.insightBorder, RoundedCornerShape(14.dp)).padding(14.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Glyph(icon, pal.accent, 20.dp)
        Text(text, color = pal.text, fontSize = 14.sp, lineHeight = 20.sp)
    }
}

@Composable
fun RowScope.Tile(label: String, value: String, sub: String, color: Color, icon: String, hint: String? = null) {
    Column(Modifier.weight(1f).clip(RoundedCornerShape(16.dp)).background(pal.surface)
        .border(1.dp, pal.border, RoundedCornerShape(16.dp)).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(28.dp).clip(RoundedCornerShape(9.dp)).background(color.copy(alpha = 0.14f)),
                contentAlignment = Alignment.Center) { Glyph(icon, color, 16.dp) }
            Spacer(Modifier.width(8.dp))
            Text(label, color = pal.muted, fontSize = 13.sp, modifier = Modifier.weight(1f), maxLines = 1)
            if (hint != null) Hint(label, hint)
        }
        Text(value, color = pal.text, fontSize = 22.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
        if (sub.isNotEmpty()) Text(sub, color = pal.faint, fontSize = 12.sp, lineHeight = 15.sp)
    }
}

@Composable
fun Segmented(options: List<String>, selected: Int, onSelect: (Int) -> Unit) {
    Row(Modifier.clip(RoundedCornerShape(10.dp)).background(pal.surface2).padding(3.dp)) {
        options.forEachIndexed { i, o ->
            val on = i == selected
            Box(Modifier.clip(RoundedCornerShape(8.dp)).background(if (on) pal.surface else Color.Transparent)
                .clickable { onSelect(i) }.padding(horizontal = 12.dp, vertical = 6.dp)) {
                Text(o, color = if (on) pal.text else pal.muted, fontSize = 13.sp,
                    fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal)
            }
        }
    }
}

@Composable
fun Legend(color: Color, text: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(9.dp).clip(RoundedCornerShape(2.dp)).background(color))
        Spacer(Modifier.width(5.dp))
        Text(text, color = pal.muted, fontSize = 12.sp)
    }
}

// --------------------------------------------------------------------- кільце заряду
@Composable
fun Ring(value: Double?, color: Color, caption: String, diameter: Dp = 128.dp) {
    val tm = rememberTextMeasurer()
    val p = pal
    Canvas(Modifier.size(diameter)) {
        val w = this.size.minDimension * 0.09f
        val tl = Offset(w / 2 + 2, w / 2 + 2)
        val sz = Size(this.size.minDimension - w - 4, this.size.minDimension - w - 4)
        drawArc(p.surface2, 0f, 360f, false, tl, sz, style = Stroke(w, cap = StrokeCap.Round))
        if (value != null) {
            drawArc(color, -90f, (360 * value.coerceIn(0.0, 100.0) / 100).toFloat(), false, tl, sz,
                style = Stroke(w, cap = StrokeCap.Round))
            val big = tm.measure("${value.toInt()}%", TextStyle(color = p.text, fontSize = (diameter.value * 0.22f).sp,
                fontWeight = FontWeight.SemiBold))
            drawText(big, topLeft = Offset((this.size.width - big.size.width) / 2, this.size.height * 0.5f - big.size.height * 0.75f))
            val small = tm.measure(caption, TextStyle(color = p.muted, fontSize = 11.sp))
            drawText(small, topLeft = Offset((this.size.width - small.size.width) / 2, this.size.height * 0.6f))
        }
    }
}

// --------------------------------------------------------------------- смуга 24 годин
@Composable
fun DayStrip(a: Long, b: Long, outages: List<Pair<Long, Long>>) {
    val tm = rememberTextMeasurer()
    val p = pal
    Canvas(Modifier.fillMaxWidth().height(40.dp)) {
        val h = 16.dp.toPx()
        val w = size.width
        fun x(t: Long) = ((t - a).toFloat() / (b - a)) * w
        drawRoundRect(p.ok.copy(alpha = 0.55f), Offset(0f, 2f), Size(w, h), CornerRadius(6.dp.toPx()))
        for ((s, e) in outages) drawRect(p.bad, Offset(x(s), 2f), Size(maxOf(2f, x(e) - x(s)), h))
        val fmt = SimpleDateFormat("HH:mm", Locale.US)
        for (k in 0..4) {
            val t = a + k * (b - a) / 4
            val l = tm.measure(if (k == 4) "зараз" else fmt.format(Date(t * 1000)), TextStyle(color = p.faint, fontSize = 10.sp))
            val tx = when (k) { 0 -> 0f; 4 -> w - l.size.width; else -> x(t) - l.size.width / 2 }
            drawText(l, topLeft = Offset(tx, h + 6))
        }
    }
}

// --------------------------------------------------------------------- лінійний графік
data class Series(val name: String, val color: Color, val points: List<Pair<Long, Double?>>, val fill: Boolean = false)

fun niceTicks(lo: Double, hi: Double, n: Int = 4): List<Double> {
    if (hi <= lo) return listOf(lo, lo + 1)
    val raw = (hi - lo) / n
    val mag = 10.0.pow(floor(log10(raw)))
    val step = listOf(1.0, 2.0, 2.5, 5.0, 10.0).map { it * mag }.first { it >= raw }
    val start = floor(lo / step) * step
    val out = mutableListOf<Double>()
    var v = start
    while (v <= hi + step * 0.001) { out += v; v += step }
    if (out.last() < hi) out += out.last() + step
    return out
}

@Composable
fun LineChart(series: List<Series>, x0: Long, x1: Long, shade: List<Pair<Long, Long>>, yFmt: (Double) -> String,
              valueFmt: (Double) -> String, height: Dp = 200.dp, yMin: Double? = null, yMax: Double? = null) {
    val tm = rememberTextMeasurer()
    val p = pal
    var cursor by remember { mutableStateOf<Float?>(null) }
    Column {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) { series.forEach { Legend(it.color, it.name) } }
        Spacer(Modifier.height(6.dp))
        Canvas(Modifier.fillMaxWidth().height(height)
            .pointerInput(Unit) { detectTapGestures(onPress = { cursor = it.x; tryAwaitRelease(); cursor = null }) }
            .pointerInput(Unit) {
                detectDragGestures(onDragEnd = { cursor = null }, onDragCancel = { cursor = null }) { ch, _ -> cursor = ch.position.x }
            }) {
            val left = 40.dp.toPx()
            val bottom = 18.dp.toPx()
            val pw = size.width - left
            val ph = size.height - bottom
            val vals = series.flatMap { s -> s.points.mapNotNull { it.second } }
            if (vals.isEmpty()) {
                val l = tm.measure("Ще немає даних — вони з'являться за кілька хвилин", TextStyle(color = p.faint, fontSize = 13.sp))
                drawText(l, topLeft = Offset((size.width - l.size.width) / 2, (size.height - l.size.height) / 2))
                return@Canvas
            }
            var lo = yMin ?: vals.min()
            var hi = yMax ?: vals.max()
            val pad = (hi - lo) * 0.08 + if (hi == lo) 1.0 else 0.0
            if (yMin == null) lo -= pad
            if (yMax == null) hi += pad
            val ticks = niceTicks(lo, hi)
            lo = minOf(lo, ticks.first()); hi = maxOf(hi, ticks.last())
            fun x(t: Long) = left + ((t - x0).toFloat() / (x1 - x0)) * pw
            fun y(v: Double) = (ph - ((v - lo) / (hi - lo)) * ph).toFloat()
            for ((s, e) in shade) drawRect(p.bad.copy(alpha = 0.08f), Offset(x(s), 0f), Size(maxOf(1f, x(e) - x(s)), ph))
            for (t in ticks) {
                drawLine(p.gridLine, Offset(left, y(t)), Offset(size.width, y(t)), 1f)
                val l = tm.measure(yFmt(t), TextStyle(color = p.faint, fontSize = 10.sp))
                drawText(l, topLeft = Offset(left - l.size.width - 6, y(t) - l.size.height / 2))
            }
            val fmt = SimpleDateFormat("HH:mm", Locale.US)
            for (k in 1..3) {
                val t = x0 + k * (x1 - x0) / 4
                val l = tm.measure(fmt.format(Date(t * 1000)), TextStyle(color = p.faint, fontSize = 10.sp))
                drawText(l, topLeft = Offset(x(t) - l.size.width / 2, ph + 4))
            }
            val gap = maxOf(900L, (x1 - x0) / 300)
            for (s in series) {
                val segs = mutableListOf<MutableList<Pair<Long, Double>>>()
                var cur = mutableListOf<Pair<Long, Double>>()
                var prev: Long? = null
                for ((t, v) in s.points) {
                    if (v == null || (prev != null && t - prev > gap)) { if (cur.isNotEmpty()) segs += cur; cur = mutableListOf() }
                    if (v != null) cur += t to v
                    prev = t
                }
                if (cur.isNotEmpty()) segs += cur
                for (seg in segs) {
                    if (seg.size == 1) { drawCircle(s.color, 2.5.dp.toPx(), Offset(x(seg[0].first), y(seg[0].second))); continue }
                    val path = Path().apply {
                        moveTo(x(seg[0].first), y(seg[0].second))
                        for ((t, v) in seg.drop(1)) lineTo(x(t), y(v))
                    }
                    if (s.fill) {
                        val base = if (lo < 0 && hi > 0) y(0.0) else ph
                        val fp = Path().apply {
                            addPath(path)
                            lineTo(x(seg.last().first), base); lineTo(x(seg[0].first), base); close()
                        }
                        drawPath(fp, s.color.copy(alpha = 0.12f))
                    }
                    drawPath(path, s.color, style = Stroke(2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
                }
            }
            // підказка під пальцем
            cursor?.let { cx ->
                if (cx < left) return@let
                val t = x0 + ((cx - left) / pw * (x1 - x0)).toLong()
                drawLine(p.faint, Offset(cx, 0f), Offset(cx, ph), 1f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 6f)))
                val lines = mutableListOf(fmt.format(Date(t * 1000)))
                for (s in series) {
                    val near = s.points.minByOrNull { abs(it.first - t) } ?: continue
                    if (abs(near.first - t) > gap) continue
                    near.second?.let { lines += "${s.name}: ${valueFmt(it)}" }
                }
                val l = tm.measure(lines.joinToString("\n"), TextStyle(color = p.text, fontSize = 12.sp))
                val bx = if (cx + l.size.width + 20 > size.width) cx - l.size.width - 18 else cx + 8
                drawRoundRect(p.surface, Offset(bx, 4f), Size(l.size.width + 12f, l.size.height + 10f), CornerRadius(8f))
                drawRoundRect(p.border, Offset(bx, 4f), Size(l.size.width + 12f, l.size.height + 10f), CornerRadius(8f), style = Stroke(1f))
                drawText(l, topLeft = Offset(bx + 6, 9f))
            }
        }
    }
}

// --------------------------------------------------------------------- стовпчики
@Composable
fun BarChart(days: List<Pair<Long, Double>>, color: Color, fmt: (Double) -> String, height: Dp = 180.dp) {
    val tm = rememberTextMeasurer()
    val p = pal
    var sel by remember { mutableStateOf<Int?>(null) }
    Canvas(Modifier.fillMaxWidth().height(height).pointerInput(days) {
        detectTapGestures(onPress = { pos ->
            val left = 34.dp.toPx()
            val bw = (size.width - left) / maxOf(1, days.size)
            sel = ((pos.x - left) / bw).toInt().takeIf { it in days.indices }
            tryAwaitRelease(); sel = null
        })
    }) {
        val left = 34.dp.toPx()
        val bottom = 18.dp.toPx()
        val ph = size.height - bottom
        val maxV = maxOf(1.0, days.maxOfOrNull { it.second } ?: 1.0)
        val ticks = niceTicks(0.0, maxV, 3)
        val top = ticks.last()
        fun y(v: Double) = (ph - v / top * ph).toFloat()
        for (t in ticks) {
            drawLine(p.gridLine, Offset(left, y(t)), Offset(size.width, y(t)), 1f)
            val l = tm.measure(fmt(t), TextStyle(color = p.faint, fontSize = 10.sp))
            drawText(l, topLeft = Offset(left - l.size.width - 4, y(t) - l.size.height / 2))
        }
        val bw = (size.width - left) / maxOf(1, days.size)
        val every = ceil(days.size / 6.0).toInt().coerceAtLeast(1)
        days.forEachIndexed { i, (d, v) ->
            val bx = left + i * bw + bw * 0.2f
            if (v > 0) drawRoundRect(if (sel == null || sel == i) color else color.copy(alpha = 0.4f),
                Offset(bx, y(v)), Size(bw * 0.6f, ph - y(v)), CornerRadius(3.dp.toPx()))
            if (i % every == 0 || i == days.lastIndex) {
                val l = tm.measure(Fmt.dayShort(d), TextStyle(color = p.faint, fontSize = 10.sp))
                drawText(l, topLeft = Offset(bx + bw * 0.3f - l.size.width / 2, ph + 4))
            }
        }
        sel?.let { i ->
            val (d, v) = days[i]
            val l = tm.measure("${Fmt.date(d)}\n${fmt(v)}", TextStyle(color = p.text, fontSize = 12.sp))
            val bx = (left + i * bw).coerceAtMost(size.width - l.size.width - 14)
            drawRoundRect(p.surface, Offset(bx, 2f), Size(l.size.width + 12f, l.size.height + 10f), CornerRadius(8f))
            drawRoundRect(p.border, Offset(bx, 2f), Size(l.size.width + 12f, l.size.height + 10f), CornerRadius(8f), style = Stroke(1f))
            drawText(l, topLeft = Offset(bx + 6, 7f))
        }
    }
}

// --------------------------------------------------------------------- теплова карта
@Composable
fun Heatmap(m: List<List<Double?>>) {
    val tm = rememberTextMeasurer()
    val p = pal
    Canvas(Modifier.fillMaxWidth().height(190.dp)) {
        val left = 24.dp.toPx()
        val bottom = 16.dp.toPx()
        val cw = (size.width - left) / 24
        val ch = (size.height - bottom) / 7
        for (w in 0 until 7) {
            val l = tm.measure(Fmt.WDAYS[w], TextStyle(color = p.faint, fontSize = 10.sp))
            drawText(l, topLeft = Offset(0f, w * ch + (ch - l.size.height) / 2))
            for (h in 0 until 24) {
                val v = m[w][h]
                val c = when {
                    v == null -> p.surface2
                    v < 0.02 -> p.ok.copy(alpha = 0.18f)
                    else -> p.bad.copy(alpha = (0.2 + 0.8 * v).toFloat().coerceAtMost(1f))
                }
                drawRoundRect(c, Offset(left + h * cw + 1.5f, w * ch + 1.5f), Size(cw - 3f, ch - 3f), CornerRadius(3f))
            }
        }
        for (h in listOf(0, 6, 12, 18)) {
            val l = tm.measure("%02d".format(h), TextStyle(color = p.faint, fontSize = 10.sp))
            drawText(l, topLeft = Offset(left + h * cw, size.height - l.size.height))
        }
    }
}

// --------------------------------------------------------------------- великий стан
@Composable
fun StatusDot(color: Color) {
    Box(Modifier.size(14.dp).clip(CircleShape).background(color))
}

@Composable
fun SmallText(text: String, color: Color = pal.faint, align: TextAlign? = null) =
    Text(text, color = color, fontSize = 12.sp, textAlign = align)
