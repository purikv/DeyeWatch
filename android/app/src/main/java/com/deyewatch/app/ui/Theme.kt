package com.deyewatch.app.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

/** Палітра DeyeWatch — та сама, що в програмі для ПК (desktop/dw/theme.py). */
@Immutable
data class Palette(
    val bg: Color, val surface: Color, val surface2: Color, val border: Color,
    val text: Color, val muted: Color, val faint: Color,
    val accent: Color, val ok: Color, val bad: Color, val warn: Color, val orange: Color,
    val pv: Color, val load: Color, val grid: Color, val batt: Color, val gen: Color,
    val gridLine: Color, val insight: Color, val insightBorder: Color, val dark: Boolean,
)

val LightPalette = Palette(
    bg = Color(0xFFF6F7F9), surface = Color.White, surface2 = Color(0xFFF0F1F4), border = Color(0xFFE3E5EA),
    text = Color(0xFF1A1C22), muted = Color(0xFF6B6F7B), faint = Color(0xFF9A9EA8),
    accent = Color(0xFF3E63DD), ok = Color(0xFF30A46C), bad = Color(0xFFE5484D), warn = Color(0xFFF5A524),
    orange = Color(0xFFF76B15), pv = Color(0xFFF5A524), load = Color(0xFF3E63DD), grid = Color(0xFF8E4EC6),
    batt = Color(0xFF30A46C), gen = Color(0xFFB5651D), gridLine = Color(0xFFECEEF2),
    insight = Color(0xFFEEF2FD), insightBorder = Color(0xFFD9E1FA), dark = false,
)

val DarkPalette = Palette(
    bg = Color(0xFF111215), surface = Color(0xFF191A1F), surface2 = Color(0xFF212329), border = Color(0xFF2B2D35),
    text = Color(0xFFEDEEF0), muted = Color(0xFFA0A4AE), faint = Color(0xFF6B6F7B),
    accent = Color(0xFF7090F0), ok = Color(0xFF3DD68C), bad = Color(0xFFFF6369), warn = Color(0xFFFFC53D),
    orange = Color(0xFFFF8B3E), pv = Color(0xFFFFC53D), load = Color(0xFF7090F0), grid = Color(0xFFBF7AF0),
    batt = Color(0xFF3DD68C), gen = Color(0xFFE0975A), gridLine = Color(0xFF23252B),
    insight = Color(0xFF1B2033), insightBorder = Color(0xFF28304A), dark = true,
)

val LocalPalette = staticCompositionLocalOf { LightPalette }

@Composable
fun DeyeTheme(content: @Composable () -> Unit) {
    val p = if (isSystemInDarkTheme()) DarkPalette else LightPalette
    val scheme = if (p.dark)
        darkColorScheme(primary = p.accent, background = p.bg, surface = p.surface, onSurface = p.text,
            onBackground = p.text, surfaceVariant = p.surface2, outline = p.border, secondaryContainer = p.surface2)
    else
        lightColorScheme(primary = p.accent, background = p.bg, surface = p.surface, onSurface = p.text,
            onBackground = p.text, surfaceVariant = p.surface2, outline = p.border, secondaryContainer = p.insight)
    CompositionLocalProvider(LocalPalette provides p) {
        MaterialTheme(colorScheme = scheme, content = content)
    }
}

val pal: Palette @Composable get() = LocalPalette.current
