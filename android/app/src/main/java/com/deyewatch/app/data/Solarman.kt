package com.deyewatch.app.data

import java.io.ByteArrayOutputStream
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.Socket
import java.net.SocketTimeoutException

/**
 * Протокол Solarman V5 (обгортка над Modbus RTU) для WiFi-стіка інвертора Deye.
 * Порт перевіреної реалізації DeyeWatch для ПК (desktop/dw/core.py).
 * Карта регістрів — deye_hybrid.yaml (StephanJoubert/home_assistant_solarman).
 */
class SolarmanException(message: String) : Exception(message)

/** Один знімок стану інвертора. Поля, яких немає в хмарі, — null. */
data class InverterData(
    val ts: Long,                 // мс
    val source: Source,
    val gridVoltage: Double,
    val gridFreq: Double?,
    val gridPower: Double,        // + беремо з мережі, − віддаємо
    val loadPower: Double,
    val pvPower: Double,
    val battPower: Double,        // + розряд, − заряд
    val soc: Double,
    val battVoltage: Double?,
    val battTemp: Double?,
    val dcTemp: Double?,
    val genPower: Double,
    val dayPv: Double?,
    val dayLoad: Double?,
    val dayBought: Double?,
    val daySold: Double?,
    val dayBattCharge: Double?,
    val dayBattDis: Double?,
    val runningStatus: Int?,
) {
    enum class Source { LOCAL, CLOUD }
}

private data class Reg(val addr: Int, val scale: Double, val signed: Boolean, val offset: Int = 0)

private val REGISTERS = mapOf(
    "running_status" to Reg(0x003B, 1.0, false),
    "day_batt_charge" to Reg(0x0046, 0.1, false),
    "day_batt_dis" to Reg(0x0047, 0.1, false),
    "day_bought" to Reg(0x004C, 0.1, false),
    "day_sold" to Reg(0x004D, 0.1, false),
    "grid_freq" to Reg(0x004F, 0.01, false),
    "day_load" to Reg(0x0054, 0.1, false),
    "dc_temp" to Reg(0x005A, 0.1, true, 1000),
    "day_pv" to Reg(0x006C, 0.1, false),
    "grid_voltage" to Reg(0x0096, 0.1, false),
    "gen_power" to Reg(0x00A6, 1.0, true),
    "grid_power" to Reg(0x00A9, 1.0, true),
    "load_power" to Reg(0x00B2, 1.0, false),
    "batt_temp" to Reg(0x00B6, 0.1, false, 1000),
    "batt_voltage" to Reg(0x00B7, 0.01, false),
    "batt_soc" to Reg(0x00B8, 1.0, false),
    "pv1_power" to Reg(0x00BA, 1.0, false),
    "pv2_power" to Reg(0x00BB, 1.0, false),
    "batt_power" to Reg(0x00BE, 1.0, true),
)
private val READ_BLOCKS = listOf(0x003B to (0x0070 - 0x003B + 1), 0x0096 to (0x00C2 - 0x0096 + 1))

val RUNNING_STATUS = mapOf(0 to "Очікування", 1 to "Самоперевірка", 2 to "Працює", 3 to "Аварія")

fun modbusCrc(data: ByteArray, len: Int = data.size): Int {
    var crc = 0xFFFF
    for (i in 0 until len) {
        crc = crc xor (data[i].toInt() and 0xFF)
        repeat(8) { crc = if (crc and 1 != 0) (crc ushr 1) xor 0xA001 else crc ushr 1 }
    }
    return crc
}

class SolarmanClient(
    private val ip: String,
    serial: Long,
    private val port: Int = 8899,
    private val timeoutMs: Int = 6000,
) {
    private val serial = serial and 0xFFFFFFFFL
    private var seq = 0x10

    private fun frame(modbus: ByteArray): ByteArray {
        seq = (seq + 1) and 0xFF
        val payload = ByteArray(15 + modbus.size)
        payload[0] = 0x02
        System.arraycopy(modbus, 0, payload, 15, modbus.size)
        val body = ByteArrayOutputStream()
        body.write(0xA5)
        body.write(payload.size and 0xFF); body.write(payload.size shr 8 and 0xFF)
        body.write(0x10); body.write(0x45)                      // control 0x4510 (LE)
        body.write(seq); body.write(0)
        for (i in 0 until 4) body.write((serial shr (8 * i) and 0xFF).toInt())
        body.write(payload)
        val b = body.toByteArray()
        var sum = 0
        for (i in 1 until b.size) sum += b[i].toInt() and 0xFF
        return b + byteArrayOf((sum and 0xFF).toByte(), 0x15)
    }

    private fun recv(s: Socket): ByteArray {
        val input = s.getInputStream()
        val buf = ByteArrayOutputStream()
        val chunk = ByteArray(1024)
        while (true) {
            val n = input.read(chunk)
            if (n < 0) throw SolarmanException("стік закрив з'єднання")
            buf.write(chunk, 0, n)
            val b = buf.toByteArray()
            if (b.size > 8192) throw SolarmanException("некоректна відповідь стіка")
            val start = b.indexOfFirst { it == 0xA5.toByte() }
            if (start >= 0 && b.size - start >= 3) {
                val len = (b[start + 1].toInt() and 0xFF) or ((b[start + 2].toInt() and 0xFF) shl 8)
                val need = 11 + len + 2
                if (b.size - start >= need) return b.copyOfRange(start, start + need)
            }
        }
    }

    private fun readBlock(s: Socket, start: Int, count: Int): IntArray {
        val req = byteArrayOf(1, 3, (start shr 8).toByte(), start.toByte(), (count shr 8).toByte(), count.toByte())
        val crc = modbusCrc(req)
        s.getOutputStream().write(frame(req + byteArrayOf(crc.toByte(), (crc shr 8).toByte())))
        repeat(3) {
            val fr = recv(s)
            var sum = 0
            for (i in 1 until fr.size - 2) sum += fr[i].toInt() and 0xFF
            if (fr.last() != 0x15.toByte() || (sum and 0xFF) != (fr[fr.size - 2].toInt() and 0xFF))
                throw SolarmanException("пошкоджений кадр")
            val control = (fr[3].toInt() and 0xFF) or ((fr[4].toInt() and 0xFF) shl 8)
            if (control != 0x1510) return@repeat
            val mb = fr.copyOfRange(25, fr.size - 2)
            if (mb.size < 5) throw SolarmanException("порожня відповідь — перевірте серійний номер стіка")
            if (mb[1].toInt() and 0x80 != 0) throw SolarmanException("помилка Modbus ${mb[2].toInt() and 0xFF}")
            val got = (mb[mb.size - 2].toInt() and 0xFF) or ((mb[mb.size - 1].toInt() and 0xFF) shl 8)
            if (modbusCrc(mb, mb.size - 2) != got) throw SolarmanException("помилка CRC")
            val n = mb[2].toInt() and 0xFF
            if (n != count * 2 || mb.size < 3 + n + 2) throw SolarmanException("неповна відповідь Modbus")
            return IntArray(count) { ((mb[3 + 2 * it].toInt() and 0xFF) shl 8) or (mb[4 + 2 * it].toInt() and 0xFF) }
        }
        throw SolarmanException("немає відповіді")
    }

    fun readAll(): InverterData {
        val raw = HashMap<Int, Int>()
        Socket().use { s ->
            s.connect(InetSocketAddress(ip, port), timeoutMs)
            s.soTimeout = timeoutMs
            for ((start, count) in READ_BLOCKS) {
                readBlock(s, start, count).forEachIndexed { i, v -> raw[start + i] = v }
            }
        }
        fun v(name: String): Double {
            val r = REGISTERS.getValue(name)
            var x = raw[r.addr] ?: throw SolarmanException("немає регістра ${r.addr}")
            if (r.signed && x >= 0x8000) x -= 0x10000
            return (x - r.offset) * r.scale
        }
        val d = InverterData(
            ts = System.currentTimeMillis(), source = InverterData.Source.LOCAL,
            gridVoltage = v("grid_voltage"), gridFreq = v("grid_freq"), gridPower = v("grid_power"),
            loadPower = v("load_power"), pvPower = v("pv1_power") + v("pv2_power"), battPower = v("batt_power"),
            soc = v("batt_soc"), battVoltage = v("batt_voltage"), battTemp = v("batt_temp"), dcTemp = v("dc_temp"),
            genPower = v("gen_power"), dayPv = v("day_pv"), dayLoad = v("day_load"), dayBought = v("day_bought"),
            daySold = v("day_sold"), dayBattCharge = v("day_batt_charge"), dayBattDis = v("day_batt_dis"),
            runningStatus = v("running_status").toInt(),
        )
        // Після перезавантаження стік інколи віддає кадр із нулів (температура тоді −100 °C).
        // Напруга мережі 0 у такому кадрі дала б хибне «світло зникло» — такі дані відкидаємо.
        if ((d.dcTemp ?: 0.0) <= -50 || d.soc !in 0.0..100.0 || d.gridVoltage > 400)
            throw SolarmanException("некоректні дані від інвертора")
        return d
    }
}

data class FoundLogger(val ip: String, val serial: Long)

/**
 * Автопошук стіка: UDP «WIFIKIT-214028-READ» на порт 48899 — широкомовно й адресно кожному хосту
 * підмережі /24 (крізь ретранслятори широкомовні пакети часто не проходять).
 * Відповідь приймаємо, лише якщо вона прийшла з тієї адреси, яку називає.
 */
fun discoverLoggers(localIps: List<String>, timeoutMs: Long = 3000): List<FoundLogger> {
    val found = LinkedHashMap<String, FoundLogger>()
    DatagramSocket().use { sock ->
        sock.broadcast = true
        sock.soTimeout = 300
        val msg = "WIFIKIT-214028-READ".toByteArray()
        val targets = mutableListOf("255.255.255.255")
        for (ip in localIps) {
            val base = ip.substringBeforeLast('.')
            targets += "$base.255"
            for (i in 1..254) targets += "$base.$i"
        }
        repeat(2) {
            for (t in targets) runCatching { sock.send(DatagramPacket(msg, msg.size, InetAddress.getByName(t), 48899)) }
        }
        val end = System.currentTimeMillis() + timeoutMs
        val buf = ByteArray(1024)
        while (System.currentTimeMillis() < end) {
            val p = DatagramPacket(buf, buf.size)
            try {
                sock.receive(p)
            } catch (e: SocketTimeoutException) {
                continue
            }
            val parts = String(p.data, 0, p.length, Charsets.US_ASCII).trim().split(",")
            val serial = parts.getOrNull(2)?.toLongOrNull()
            if (parts.size >= 3 && serial != null && parts[0] == p.address.hostAddress) {
                found[parts[0]] = FoundLogger(parts[0], serial)
            }
        }
    }
    return found.values.toList()
}
