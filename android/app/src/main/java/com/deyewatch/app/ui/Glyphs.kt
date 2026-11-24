package com.deyewatch.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import kotlin.math.cos
import kotlin.math.sin

/** Векторні іконки DeyeWatch (ті самі, що в програмі для ПК), без сторонніх бібліотек. */
@Composable
fun Glyph(name: String, color: Color, size: Dp = 20.dp, level: Double? = null, modifier: Modifier = Modifier) {
    Canvas(modifier.size(size)) { drawGlyph(name, Offset.Zero, this.size.minDimension, color, level) }
}

fun DrawScope.drawGlyph(name: String, topLeft: Offset, s: Float, col: Color, level: Double? = null) {
    val x = topLeft.x
    val y = topLeft.y
    val lw = maxOf(1.6f, s * 0.085f)
    val stroke = Stroke(width = lw, cap = StrokeCap.Round)
    fun p(fx: Float, fy: Float) = Offset(x + fx * s, y + fy * s)
    fun bolt(l: Float, t: Float, w: Float, h: Float) = Path().apply {
        val pts = listOf(0.58f to 0.04f, 0.18f to 0.56f, 0.47f to 0.56f, 0.40f to 0.96f, 0.82f to 0.42f, 0.53f to 0.42f)
        pts.forEachIndexed { i, (a, b) ->
            val o = Offset(x + (l + a * w) * s, y + (t + b * h) * s)
            if (i == 0) moveTo(o.x, o.y) else lineTo(o.x, o.y)
        }
        close()
    }
    when (name) {
        "bolt" -> drawPath(bolt(0.06f, 0.02f, 0.88f, 0.96f), col)
        "bolt_off" -> {
            drawPath(bolt(0.06f, 0.02f, 0.88f, 0.96f), col)
            drawLine(col, p(0.12f, 0.1f), p(0.88f, 0.9f), lw * 1.1f, StrokeCap.Round)
        }
        "sun" -> {
            drawCircle(col, s * 0.18f, p(0.5f, 0.5f), style = stroke)
            for (k in 0 until 8) {
                val a = Math.toRadians(k * 45.0)
                drawLine(col, p(0.5f + 0.3f * cos(a).toFloat(), 0.5f + 0.3f * sin(a).toFloat()),
                    p(0.5f + 0.42f * cos(a).toFloat(), 0.5f + 0.42f * sin(a).toFloat()), lw, StrokeCap.Round)
            }
        }
        "home" -> {
            val path = Path().apply {
                moveTo(p(0.14f, 0.48f).x, p(0.14f, 0.48f).y); lineTo(p(0.5f, 0.16f).x, p(0.5f, 0.16f).y)
                lineTo(p(0.86f, 0.48f).x, p(0.86f, 0.48f).y)
            }
            drawPath(path, col, style = stroke)
            drawRoundRect(col, p(0.24f, 0.44f), Size(s * 0.52f, s * 0.4f), CornerRadius(s * 0.05f), style = stroke)
        }
        "battery" -> {
            drawRoundRect(col, p(0.2f, 0.16f), Size(s * 0.6f, s * 0.74f), CornerRadius(s * 0.09f), style = stroke)
            drawLine(col, p(0.4f, 0.08f), p(0.6f, 0.08f), lw, StrokeCap.Round)
            if (level != null) {
                val h = (0.54f * (level.coerceIn(0.0, 100.0) / 100.0)).toFloat()
                drawRoundRect(col, p(0.3f, 0.8f - h), Size(s * 0.4f, s * h), CornerRadius(s * 0.03f))
            }
        }
        "grid" -> {
            drawLine(col, p(0.5f, 0.1f), p(0.25f, 0.9f), lw, StrokeCap.Round)
            drawLine(col, p(0.5f, 0.1f), p(0.75f, 0.9f), lw, StrokeCap.Round)
            drawLine(col, p(0.2f, 0.3f), p(0.8f, 0.3f), lw, StrokeCap.Round)
            drawLine(col, p(0.3f, 0.55f), p(0.7f, 0.55f), lw, StrokeCap.Round)
        }
        "gen" -> {
            drawRoundRect(col, p(0.1f, 0.22f), Size(s * 0.8f, s * 0.56f), CornerRadius(s * 0.1f), style = stroke)
            drawLine(col, p(0.25f, 0.78f), p(0.25f, 0.9f), lw, StrokeCap.Round)
            drawLine(col, p(0.75f, 0.78f), p(0.75f, 0.9f), lw, StrokeCap.Round)
            drawLine(col, p(0.35f, 0.1f), p(0.65f, 0.1f), lw, StrokeCap.Round)
            drawPath(bolt(0.36f, 0.28f, 0.28f, 0.44f), col)
        }
        "clock" -> {
            drawCircle(col, s * 0.4f, p(0.5f, 0.5f), style = stroke)
            drawLine(col, p(0.5f, 0.28f), p(0.5f, 0.5f), lw, StrokeCap.Round)
            drawLine(col, p(0.5f, 0.5f), p(0.66f, 0.6f), lw, StrokeCap.Round)
        }
        "chart" -> for ((i, h) in listOf(0.35f, 0.6f, 0.45f, 0.75f).withIndex()) {
            val cx = 0.2f + i * 0.2f
            drawLine(col, p(cx, 0.86f), p(cx, 0.86f - h), lw * 1.2f, StrokeCap.Round)
        }
        "overview" -> for (dx in 0..1) for (dy in 0..1) {
            drawRoundRect(col, p(0.14f + dx * 0.38f, 0.14f + dy * 0.38f), Size(s * 0.3f, s * 0.3f),
                CornerRadius(s * 0.06f), style = stroke)
        }
        "gear" -> {
            drawCircle(col, s * 0.14f, p(0.5f, 0.5f), style = stroke)
            drawCircle(col, s * 0.3f, p(0.5f, 0.5f), style = stroke)
            for (k in 0 until 8) {
                val a = Math.toRadians(k * 45.0)
                drawLine(col, p(0.5f + 0.3f * cos(a).toFloat(), 0.5f + 0.3f * sin(a).toFloat()),
                    p(0.5f + 0.42f * cos(a).toFloat(), 0.5f + 0.42f * sin(a).toFloat()), lw * 1.3f, StrokeCap.Round)
            }
        }
        "wave" -> {
            val path = Path()
            for (i in 0..40) {
                val fx = 0.08f + i / 40f * 0.84f
                val fy = 0.5f - 0.22f * sin(fx * 2 * Math.PI * 1.2).toFloat()
                if (i == 0) path.moveTo(p(fx, fy).x, p(fx, fy).y) else path.lineTo(p(fx, fy).x, p(fx, fy).y)
            }
            drawPath(path, col, style = stroke)
        }
    }
}
