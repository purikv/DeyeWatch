package com.deyewatch.app.monitor

import com.deyewatch.app.data.InverterData
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

/** Поточний стан, спільний для фонового сервісу та екранів. Час — у секундах. */
data class LiveState(
    val data: InverterData? = null,
    val gridOk: Boolean? = null,
    val since: Long = 0,
    val autonomyH: Double? = null,
    val genOn: Boolean = false,
    val genSince: Long = 0,
    val status: String = "Підключення…",
    val error: String? = null,
    val running: Boolean = false,
    val historyVersion: Int = 0,      // збільшується після запису в історію — екрани оновлюють графіки
)

object Hub {
    private val _state = MutableStateFlow(LiveState())
    val state: StateFlow<LiveState> = _state.asStateFlow()

    fun update(f: (LiveState) -> LiveState) = _state.update(f)
}
