# -*- coding: utf-8 -*-
"""Сторінка налаштувань."""
import threading

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from . import messages as M
from .config import autostart_state, set_autostart
from .core import SolarmanV5, Telegram, discover
from .pages import Page
from .theme import c
from .widgets import Card, tip_html


class Switch(QAbstractButton):
    def __init__(self, checked=False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(40, 22)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        p.setPen(Qt.NoPen)
        p.setBrush(c("accent") if on else c("border"))
        p.drawRoundedRect(QRectF(0, 0, 40, 22), 11, 11)
        p.setBrush(c("surface") if not on else Qt.white)
        p.drawEllipse(QRectF(21 if on else 3, 3, 16, 16))


class SettingsPage(Page):
    title = "Налаштування"
    found = Signal(object)
    tested = Signal(str, bool)
    tg_tested = Signal(str, bool)

    def __init__(self, app):
        super().__init__(app)
        self.w = {}
        self.cards = {}
        cfg = app.cfg
        self.save_btn = QPushButton("Зберегти")
        self.save_btn.setObjectName("primary")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self.save)
        self.saved_lbl = QLabel("")
        self.saved_lbl.setObjectName("faint")
        self.head.addWidget(self.saved_lbl)
        self.head.addWidget(self.save_btn)
        intro = QLabel("Наведіть мишу на назву будь-якого поля, щоб прочитати пояснення. Після змін натисніть "
                       "«Зберегти» вгорі праворуч. Поля, позначені «для досвідчених», зазвичай чіпати не треба.")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        self.v.addWidget(intro)

        # --- Підключення
        card, g = self.section("connection", "Підключення до інвертора",
                               "Програма читає дані напряму з WiFi-стіка Solarman, вставленого в інвертор, — "
                               "через вашу домашню мережу, без інтернету. Найпростіше натиснути "
                               "«Знайти автоматично»: програма сама знайде стік і заповнить IP та серійний номер.")
        self.text(g, "logger_ip", "IP-адреса стіка",
                  "Адреса стіка у вашій мережі, наприклад 192.168.1.50. Якщо роутер видасть стіку нову адресу, "
                  "програма сама знайде його за серійним номером.")
        self.num(g, "logger_serial", "Серійний номер стіка (SN)", 0, 9999999999, big=True,
                 hint="10 цифр на наклейці WiFi-стіка (не інвертора!). Без правильного номера стік не відповідає.")
        self.num(g, "logger_port", "Порт (для досвідчених)", 1, 65535,
                 hint="Порт протоколу Solarman. Майже завжди 8899 — змінювати не потрібно.")
        self.num(g, "poll_interval_sec", "Опитувати кожні, с", 3, 300,
                 hint="Як часто питати інвертор. 10 с — оптимально: відключення помічається за ~20 с. "
                      "Рідше — менше навантаження на стік, але сповіщення приходять пізніше.")
        row = QHBoxLayout()
        b1 = QPushButton("Знайти автоматично")
        b1.setObjectName("primary")
        b1.clicked.connect(self.do_discover)
        b2 = QPushButton("Перевірити зв'язок")
        b2.clicked.connect(self.do_test)
        self.conn_lbl = QLabel("")
        self.conn_lbl.setTextFormat(Qt.PlainText)
        self.conn_lbl.setObjectName("muted")
        self.conn_lbl.setWordWrap(True)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addWidget(self.conn_lbl, 1)
        card.lay.addLayout(row)
        self.found.connect(self.on_found)
        self.tested.connect(lambda t, ok: self.conn_lbl.setText(("✓ " if ok else "✗ ") + t))

        # --- Батарея
        card, g = self.section("battery", "Батарея, сонячні панелі, генератор",
                               "Від цих значень залежить прогноз «батареї вистачить на…». Їх можна подивитися "
                               "в документах до батареї або в налаштуваннях інвертора.")
        self.dbl(g, "battery_kwh", "Ємність батареї, кВт·год", 0, 200,
                 hint="Повна ємність усіх батарей разом. Наприклад, батарея 51,2 В × 200 А·год = 10,24 кВт·год.")
        self.num(g, "battery_min_soc", "Мінімальний заряд, %", 0, 90,
                 hint="Нижче цього заряду інвертор вимикає живлення від батареї (у меню інвертора — "
                      "Battery Shutdown). Прогноз рахується саме до нього.")
        self.text(g, "low_soc_thresholds", "Попереджати при заряді, %",
                  hint="Під час відключення програма надішле сповіщення, коли заряд опуститься до кожного "
                       "з цих рівнів. Кілька значень — через кому, наприклад: 50, 30, 20.",
                  fmt=lambda v: ", ".join(str(x) for x in v))
        self.toggle(g, "has_pv", "Є сонячні панелі",
                    "Вимкніть, якщо панелей немає, — тоді показники сонця зникнуть з екранів.")
        self.toggle(g, "has_gen", "Є генератор (порт GEN)",
                    "Генератор, підключений до порту GEN інвертора. Програма показує його на схемі й графіках, "
                    "рахує час роботи та енергію. Вмикається само, щойно інвертор уперше побачить генератор.")
        self.num(g, "gen_min_power", "Генератор працює, якщо дає понад, Вт", 5, 2000,
                 hint="Від цієї потужності на порту GEN генератор вважається запущеним. 30 Вт підходить майже "
                      "завжди; збільште, якщо бачите хибні запуски.")

        # --- Відключення
        card, g = self.section("outage", "Як визначати відключення",
                               "Стандартні значення підходять майже всім.")
        self.text(g, "name", "Назва об'єкта",
                  "Як підписувати сповіщення — зручно, якщо програма стоїть у кількох місцях: «Дім», «Дача».")
        self.dbl(g, "grid_min_voltage", "Світла немає, якщо напруга нижче, В", 50, 230,
                 hint="Коли напруга мережі падає нижче цього значення, вважається, що світла немає. "
                      "170 В — надійний поріг.")
        self.num(g, "confirm_polls", "Підтверджувати, опитувань (для досвідчених)", 1, 10,
                 hint="Скільки опитувань поспіль має підтвердити зміну, щоб не реагувати на миттєві "
                      "«блимання». 2 опитування × 10 с = 20 с.")
        self.num(g, "offline_alert_polls", "«Немає зв'язку» після, опитувань (для досвідчених)", 1, 100,
                 hint="Після скількох невдалих опитувань поспіль повідомити, що інвертор не відповідає "
                      "(стік перезавантажується, роутер вимкнено тощо).")

        # --- Якість мережі
        card, g = self.section("grid", "Якість мережі",
                               "Норма для побутової мережі в Україні — 230 В ±10%, тобто від 207 до 253 В.")
        self.dbl(g, "v_low", "Нижня межа норми, В", 150, 230,
                 hint="Нижче цієї напруги — «занижена». Довга занижена напруга шкодить двигунам "
                      "(холодильник, насос).")
        self.dbl(g, "v_high", "Верхня межа норми, В", 230, 300,
                 hint="Вище — «завищена». Небезпечно для електроніки.")
        self.num(g, "v_alert_minutes", "Сповіщати, якщо триває, хв", 0, 60,
                 hint="Повідомляти лише тоді, коли напруга поза нормою довше за цей час, щоб не реагувати "
                      "на короткі стрибки.")

        # --- Сповіщення
        card, g = self.section("notify", "Сповіщення",
                               "Що саме повідомляти. Натисніть «Приклад», щоб побачити, як виглядає сповіщення.")
        self.toggle(g, "notify_outage", "Світло зникло", "Одразу, щойно зникла напруга в мережі.")
        self.toggle(g, "notify_restore", "Світло з'явилося", "Разом зі сповіщенням — скільки тривало відключення.")
        self.toggle(g, "notify_low_soc", "Низький заряд батареї",
                    "Під час відключення — коли заряд досягає порогів із розділу «Батарея».")
        self.toggle(g, "notify_voltage", "Напруга поза нормою", "Занижена або завищена напруга, коли світло є.")
        self.toggle(g, "notify_offline", "Втрата зв'язку з інвертором",
                    "Коли програма не може отримати дані (стік, Wi-Fi або роутер не працюють).")
        self.toggle(g, "notify_gen", "Генератор запущено / зупинено",
                    "Коли генератор почав давати енергію і коли зупинився — з часом роботи й виробленою енергією.")
        self.toggle(g, "notify_daily_summary", "Підсумок дня о 21:00",
                    "Щовечора — скільки було відключень, вироблено й спожито енергії.")
        self.toggle(g, "desktop_notify", "Показувати на цьому комп'ютері",
                    "Спливаюча картка в правому нижньому куті екрана.")
        self.toggle(g, "sound", "Звук", "Короткий звуковий сигнал разом зі сповіщенням.")
        self.num(g, "toast_seconds", "Тривалість показу, с", 3, 120,
                 hint="Скільки секунд картка залишається на екрані. Сповіщення про відключення "
                      "висить, доки ви його не закриєте. Наведіть мишу на картку — вона не зникне.")
        row = QHBoxLayout()
        for kind, label in (("outage", "Приклад: світло зникло"), ("restore", "з'явилося"), ("low_soc", "батарея"),
                             ("gen", "генератор")):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, k=kind: self.app.demo_note(k))
            row.addWidget(b)
        row.addStretch()
        card.lay.addLayout(row)

        # --- Telegram
        card, g = self.section("telegram", "Telegram (необов'язково)",
                               "Сповіщення на телефон — вам і рідним.<br>"
                               "<b>1.</b> Відкрийте в Telegram <a href='https://t.me/BotFather'>@BotFather</a>, "
                               "надішліть <b>/newbot</b> і придумайте назву — отримаєте <b>токен</b>.<br>"
                               "<b>2.</b> Вставте токен нижче, увімкніть «Відповідати на команди» і натисніть «Зберегти».<br>"
                               "<b>3.</b> Кожен, хто хоче отримувати сповіщення, пише вашому боту <b>/start</b> — "
                               "бот відповість номером <b>chat_id</b>. Впишіть ці номери нижче через кому.<br>"
                               "Якщо бот на роутері вже використовує цей токен, для команд тут створіть окремого бота.")
        self.toggle(g, "telegram_enabled", "Надсилати сповіщення в Telegram",
                    "Ті самі сповіщення, що й на комп'ютері, але в Telegram.")
        self.text(g, "telegram_token", "Токен бота",
                  "Довгий рядок від @BotFather виду 123456789:AA… Нікому його не показуйте.", password=True)
        self.text(g, "telegram_chat_ids", "chat_id отримувачів",
                  "Номери чатів через кому. Для групи — номер групи (починається з мінуса).")
        self.toggle(g, "telegram_commands", "Відповідати на команди",
                    "Бот відповідає на /status (світло, батарея зараз) і /stats (статистика), "
                    "а незнайомим — їхнім chat_id.")
        row = QHBoxLayout()
        b = QPushButton("Надіслати тестове")
        b.clicked.connect(self.do_tg_test)
        self.tg_lbl = QLabel("")
        self.tg_lbl.setTextFormat(Qt.PlainText)
        self.tg_lbl.setObjectName("muted")
        self.tg_lbl.setWordWrap(True)
        row.addWidget(b)
        row.addWidget(self.tg_lbl, 1)
        card.lay.addLayout(row)
        self.tg_tested.connect(lambda t, ok: self.tg_lbl.setText(("✓ " if ok else "✗ ") + t))

        # --- Хмара
        card, g = self.section("cloud", "Хмара Deye Cloud (необов'язково)",
                               "Поки комп'ютер вимкнений або спить, програма не бачить інвертор. Інвертор тим часом "
                               "сам відправляє дані в Deye Cloud — звідти програма й догружає пропущене "
                               "(відключення з точністю ~5 хв, заряд, енергію).<br>"
                               "<b>1.</b> Увійдіть на <a href='https://developer.deyecloud.com'>developer.deyecloud.com</a> "
                               "тим самим акаунтом, що й у застосунку Deye Cloud.<br>"
                               "<b>2.</b> Створіть застосунок (Application) — отримаєте <b>App ID</b> і <b>App Secret</b>.<br>"
                               "<b>3.</b> Заповніть поля нижче й натисніть «Зберегти й синхронізувати».<br>"
                               "Пароль потрібен, бо без нього Deye Cloud не видає доступу до даних. "
                               "Програма зберігає не сам пароль, а його хеш SHA-256 і використовує лише для входу "
                               "в Deye Cloud раз на ~2 місяці.")
        self.toggle(g, "cloud_enabled", "Догружати пропущене з хмари",
                    "Перевірка — при запуску, після сну, після відновлення зв'язку та кожні 30 хв.")
        self.text(g, "cloud_app_id", "App ID", "Номер застосунку з developer.deyecloud.com (лише цифри).")
        self.text(g, "cloud_app_secret", "App Secret", "Секретний ключ застосунку з developer.deyecloud.com.",
                  password=True)
        self.text(g, "cloud_email", "Email акаунта Deye Cloud", "Той, з яким ви входите в застосунок Deye Cloud.")
        pw = QLineEdit()
        pw.setEchoMode(QLineEdit.Password)
        pw.setMinimumWidth(260)
        pw.setPlaceholderText("збережено" if cfg["cloud_password_sha"] else "пароль від Deye Cloud")
        self.cloud_pw = pw
        self._row(g, "Пароль", pw, "Пароль від акаунта Deye Cloud. Після збереження поле очищується — це нормально.")
        self.num(g, "cloud_backfill_days", "Догружати за останні, днів", 1, 365,
                 hint="За який період шукати пропуски. Хмара зберігає детальні дані обмежений час.")
        self.text(g, "cloud_base", "Сервер API (для досвідчених)",
                  "Сервер Deye Cloud для Європи. Змінювати лише якщо акаунт в іншому регіоні.")
        row = QHBoxLayout()
        b = QPushButton("Зберегти й синхронізувати")
        b.clicked.connect(self.do_cloud)
        self.cloud_lbl = QLabel(self._cloud_status())
        self.cloud_lbl.setTextFormat(Qt.PlainText)
        self.cloud_lbl.setObjectName("muted")
        self.cloud_lbl.setWordWrap(True)
        row.addWidget(b)
        row.addWidget(self.cloud_lbl, 1)
        card.lay.addLayout(row)
        app.monitor.cloud.connect(lambda ok, t: self.cloud_lbl.setText(("✓ " if ok else "✗ ") + t))

        # --- Аналітика
        card, g = self.section("stats", "Статистика та аналітика",
                               "Розділи ліворуч у меню. Непотрібні можна сховати.")
        self.toggle(g, "stats_enabled", "Записувати історію показників",
                    "Без цього графіки й статистика не працюватимуть — лише сповіщення.")
        self.toggle(g, "an_outages", "Розділ «Відключення»", "Скільки й коли вимикали світло, теплова карта.")
        self.toggle(g, "an_grid", "Розділ «Якість мережі»", "Напруга й частота, вихід за норму.")
        self.toggle(g, "an_energy", "Розділ «Енергія»", "Вироблено, спожито, куплено по днях.")
        self.toggle(g, "an_battery", "Розділ «Батарея»", "Заряд, температура, цикли.")
        self.num(g, "keep_days", "Зберігати детальну історію, днів", 7, 3650,
                 hint="Хвилинні записи старші за цей термін видаляються. Підсумки по днях і список "
                      "відключень зберігаються завжди. Рік займає ~30 МБ.")

        # --- Інтерфейс
        card, g = self.section("ui", "Інтерфейс")
        self.combo(g, "theme", "Тема", [("system", "Як у системі"), ("light", "Світла"), ("dark", "Темна")],
                   "«Як у системі» — автоматично світла вдень і темна, якщо так налаштовано в системі.")
        self.toggle(g, "autostart", "Запускати разом із системою",
                    "Рекомендовано: програма працюватиме у фоні після кожного ввімкнення комп'ютера.")
        self.auto_lbl = QLabel("")
        self.auto_lbl.setObjectName("hint")
        self.auto_lbl.setWordWrap(True)
        g.addWidget(self.auto_lbl, g.rowCount(), 0, 1, 2)
        self.show_autostart()
        self.toggle(g, "start_minimized", "Запускати згорнутим у трей",
                    "При автозапуску вікно не відкривається — лише іконка біля годинника.")
        row = QHBoxLayout()
        b = QPushButton("Показати «З чого почати» на Огляді")
        b.clicked.connect(self.show_onboarding)
        row.addWidget(b)
        row.addStretch()
        card.lay.addLayout(row)
        # --- Перенесення
        card, g = self.section("transfer", "Перенесення налаштувань",
                               "Збережіть усі налаштування у файл і завантажте його на іншому комп'ютері (Windows або "
                               "Linux) — не доведеться вводити все заново. Історія та статистика у файл не входять: "
                               "на новому пристрої їх догрузить Deye Cloud.")
        self.exp_secrets = Switch(True)
        self._row(g, "Разом із паролями й токенами", self.exp_secrets,
                  "Токен Telegram, App Secret і хеш пароля Deye Cloud. Тоді на новому пристрої все запрацює одразу. "
                  "Такий файл — як ключ від акаунтів: не пересилайте його стороннім і видаліть після перенесення.")
        row = QHBoxLayout()
        b = QPushButton("Зберегти у файл…")
        b.clicked.connect(self.do_export)
        row.addWidget(b)
        b = QPushButton("Завантажити з файлу…")
        b.clicked.connect(self.do_import)
        row.addWidget(b)
        self.tr_lbl = QLabel("")
        self.tr_lbl.setTextFormat(Qt.PlainText)
        self.tr_lbl.setObjectName("muted")
        self.tr_lbl.setWordWrap(True)
        row.addWidget(self.tr_lbl, 1)
        card.lay.addLayout(row)

        from . import __version__
        p = QLabel("DeyeWatch %s · налаштування та історія: %s" % (__version__,
                                                                   app.cfg.path.rsplit("settings.json", 1)[0]))
        self.path_lbl = p
        p.setObjectName("faint")
        p.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.v.addWidget(p)
        self.v.addStretch()

    # ---- побудова полів
    def section(self, key, title, hint=None):
        card = Card(title)
        if hint:
            h = QLabel(hint)
            h.setObjectName("muted")
            h.setWordWrap(True)
            h.setTextFormat(Qt.RichText)
            h.setOpenExternalLinks(True)
            card.lay.addWidget(h)
        g = QGridLayout()
        g.setHorizontalSpacing(18)
        g.setVerticalSpacing(12)
        g.setColumnStretch(0, 1)
        card.lay.addLayout(g)
        self.v.addWidget(card)
        self.cards[key] = card
        return card, g

    def goto(self, key):
        card = self.cards.get(key)
        if card:
            self.ensureWidgetVisible(card, 0, 40)
            self.verticalScrollBar().setValue(card.y() - 10)

    def show_onboarding(self):
        self.app.cfg["onboarding_done"] = False
        self.app.cfg.save()
        ov = self.app.win.pages["overview"]
        if not ov.onboard:
            ov.build_onboarding()
            ov.v.insertWidget(1, ov.v.takeAt(ov.v.indexOf(ov.onboard)).widget())
        self.app.win.show_page("overview")

    def _row(self, g, label, w, hint=None):
        r = g.rowCount()
        box = QVBoxLayout()
        box.setSpacing(1)
        lab = QLabel(label)
        box.addWidget(lab)
        if hint:
            h = QLabel(hint)
            h.setObjectName("hint")
            h.setWordWrap(True)
            box.addWidget(h)
            tip = tip_html(hint)
            lab.setToolTip(tip)
            w.setToolTip(tip)
        g.addLayout(box, r, 0)
        g.addWidget(w, r, 1, Qt.AlignRight | Qt.AlignTop)

    def text(self, g, key, label, hint=None, password=False, fmt=None):
        e = QLineEdit(fmt(self.app.cfg[key]) if fmt else str(self.app.cfg[key]))
        e.setMinimumWidth(260)
        if password:
            e.setEchoMode(QLineEdit.Password)
        self.w[key] = ("text", e)
        self._row(g, label, e, hint)

    def num(self, g, key, label, lo, hi, big=False, hint=None):
        if big:    # серійний номер > int32 — тримаємо як текст
            e = QLineEdit(str(self.app.cfg[key]))
            e.setMinimumWidth(260)
            self.w[key] = ("bigint", e)
        else:
            e = QSpinBox()
            e.setRange(lo, hi)
            e.setValue(int(self.app.cfg[key]))
            e.setMinimumWidth(120)
            self.w[key] = ("num", e)
        self._row(g, label, e, hint)

    def dbl(self, g, key, label, lo, hi, hint=None):
        e = QDoubleSpinBox()
        e.setRange(lo, hi)
        e.setDecimals(1)
        e.setValue(float(self.app.cfg[key]))
        e.setMinimumWidth(120)
        self.w[key] = ("num", e)
        self._row(g, label, e, hint)

    def toggle(self, g, key, label, hint=None):
        s = Switch(bool(self.app.cfg[key]))
        s.toggled.connect(self._autosave)
        self.w[key] = ("bool", s)
        self._row(g, label, s, hint)

    def combo(self, g, key, label, items, hint=None):
        cb = QComboBox()
        for v, t in items:
            cb.addItem(t, v)
        cb.setCurrentIndex(max(0, [v for v, _ in items].index(self.app.cfg[key])))
        cb.setMinimumWidth(160)
        cb.currentIndexChanged.connect(self._autosave)
        self.w[key] = ("combo", cb)
        self._row(g, label, cb, hint)

    def _autosave(self, *_):
        """Перемикачі й списки зберігаються одразу — щоб «галочка стоїть, а не працює» не траплялося."""
        if not getattr(self, "_loading", False):
            self.save()

    def show_autostart(self):
        if not hasattr(self, "auto_lbl"):
            return
        try:
            st = autostart_state()
        except Exception as e:
            st = "error: %s" % e
        on = self.app.cfg["autostart"]
        txt = {
            ("ok", True): "✓ Автозапуск працює: програма стартує після входу в систему, згорнута в трей.",
            ("missing", False): "",
            ("disabled", True): "⚠ Автозапуск вимкнено в системі (Диспетчер завдань → Автозавантаження → "
                                "DeyeWatch). Увімкніть його там — програма не може зробити це сама.",
            ("disabled", False): "",
        }.get((st, on))
        if txt is None:
            txt = ("⚠ Запис автозапуску не збігається з налаштуванням (%s). Натисніть перемикач ще раз." % st
                   if on else "")
        self.auto_lbl.setText(txt)
        self.auto_lbl.setVisible(bool(txt))

    def values(self):
        out = {}
        for k, (kind, w) in self.w.items():
            if kind == "text":
                v = w.text().strip()
                if k == "low_soc_thresholds":
                    v = sorted({int(x) for x in v.replace(";", ",").split(",") if x.strip().isdigit()}, reverse=True)
                out[k] = v
            elif kind == "bigint":
                out[k] = int("".join(ch for ch in w.text() if ch.isdigit()) or 0)
            elif kind == "num":
                out[k] = w.value()
            elif kind == "bool":
                out[k] = w.isChecked()
            elif kind == "combo":
                out[k] = w.currentData()
        return out

    def _cloud_status(self):
        st = self.app.store
        last = st.get("cloud_last")
        msg = st.get("cloud_last_msg", "")
        if msg:
            return "✗ " + msg
        if last:
            return "Остання синхронізація: %s %s" % (M.fmt_date(float(last)), M.fmt_clock(float(last)))
        return "Ще не синхронізовано"

    def do_cloud(self):
        self.save()
        self.cloud_lbl.setText("Підключаюся до Deye Cloud…")
        threading.Thread(target=self.app.monitor.cloud_sync, daemon=True).start()

    def save(self):
        cfg = self.app.cfg
        old_auto, old_theme = cfg["autostart"], cfg["theme"]
        old_cloud = (cfg["cloud_base"], cfg["cloud_app_id"], cfg["cloud_app_secret"], cfg["cloud_email"],
                     cfg["cloud_password_sha"])
        cfg.update(self.values())
        cfg["_battery_checked"] = True
        if getattr(self, "_pending_pw_sha", None) is not None:
            cfg["cloud_password_sha"] = self._pending_pw_sha
            self._pending_pw_sha = None
            self.cloud_pw.setPlaceholderText("збережено" if cfg["cloud_password_sha"] else "пароль від Deye Cloud")
        if self.cloud_pw.text():
            from .cloud import sha256
            cfg["cloud_password_sha"] = sha256(self.cloud_pw.text())
            self.cloud_pw.clear()
            self.cloud_pw.setPlaceholderText("збережено")
        if old_cloud != (cfg["cloud_base"], cfg["cloud_app_id"], cfg["cloud_app_secret"], cfg["cloud_email"],
                         cfg["cloud_password_sha"]):
            self.app.store.put("cloud_token", "")
            self.app.store.put("cloud_setup", "")
        cfg.save()
        try:
            from .config import ensure_autostart
            ensure_autostart(cfg["autostart"])
        except Exception as e:
            self.saved_lbl.setText("Автозапуск: %s" % e)
        self.show_autostart()
        self.app.settings_changed(cfg["theme"] != old_theme)
        try:
            self.app.win.pages["overview"].fill_onboarding()
        except Exception:
            pass
        self.saved_lbl.setText("Збережено ✓")
        QTimer.singleShot(2500, lambda: self.saved_lbl.setText(""))

    # ---- дії
    def do_discover(self):
        self.conn_lbl.setText("Шукаю стік у мережі… (до 15 с)")

        def run():
            try:
                self.found.emit(discover())
            except Exception as e:
                self.found.emit(str(e))
        threading.Thread(target=run, daemon=True).start()

    def on_found(self, res):
        if isinstance(res, str):
            self.conn_lbl.setText("✗ Помилка пошуку: " + res)
            return
        if not res:
            self.conn_lbl.setText("✗ Стік не знайдено. Перевірте, що ПК і стік в одній мережі.")
            return
        f = res[0]
        self.w["logger_ip"][1].setText(f["ip"])
        if f["serial"]:
            self.w["logger_serial"][1].setText(str(f["serial"]))
            self.conn_lbl.setText("✓ Знайдено: %s, SN %s%s. Натисніть «Зберегти»." % (
                f["ip"], f["serial"], " (ще %d)" % (len(res) - 1) if len(res) > 1 else ""))
        else:
            self.conn_lbl.setText("Знайдено пристрій з портом 8899: %s. Серійний номер введіть вручну." % f["ip"])

    def do_test(self):
        v = self.values()
        self.conn_lbl.setText("Перевіряю…")

        def run():
            try:
                d = SolarmanV5(v["logger_ip"], v["logger_serial"], v["logger_port"]).read_all()
                self.tested.emit("Є зв'язок: мережа %.0f В, батарея %d%%, споживання %s" % (
                    d["grid_voltage"], d["batt_soc"], M.fmt_power(d["load_power"])), True)
            except Exception as e:
                hint = " — перевірте серійний номер" if "timed out" in str(e) else ""
                self.tested.emit("%s%s" % (e, hint), False)
        threading.Thread(target=run, daemon=True).start()

    def do_tg_test(self):
        v = self.values()
        ids = [x.strip() for x in v["telegram_chat_ids"].replace(";", ",").split(",") if x.strip()]
        if not v["telegram_token"] or not ids:
            self.tg_lbl.setText("✗ Вкажіть токен і хоча б один chat_id")
            return
        note = M.Note("test", "DeyeWatch підключено", "%s · тестове повідомлення" % v["name"],
                      [("✅", "Сповіщення", "працюють")], None, "⚡")

        def run():
            try:
                tg = Telegram(v["telegram_token"])
                for cid in ids:
                    tg.send(cid, note.telegram_html())
                self.tg_tested.emit("Надіслано (%d)" % len(ids), True)
            except Exception as e:
                self.tg_tested.emit(str(e), False)
        threading.Thread(target=run, daemon=True).start()

    # ---- перенесення налаштувань
    SECRETS = ("telegram_token", "cloud_app_secret", "cloud_password_sha")

    def do_export(self):
        import datetime as dt
        import json
        import os
        from PySide6.QtWidgets import QFileDialog
        from .config import DEFAULTS
        self.save()     # у файл іде те, що зараз на екрані
        name = "DeyeWatch-налаштування-%s.json" % dt.date.today().isoformat()
        path, _ = QFileDialog.getSaveFileName(self, "Зберегти налаштування", os.path.join(os.path.expanduser("~"), name),
                                              "Налаштування DeyeWatch (*.json)")
        if not path:
            return
        with_secrets = self.exp_secrets.isChecked()
        data = {k: self.app.cfg[k] for k in DEFAULTS if with_secrets or k not in self.SECRETS}
        doc = {"app": "DeyeWatch", "kind": "settings", "version": 1,
               "exported": dt.datetime.now().isoformat(timespec="seconds"), "secrets": with_secrets, "settings": data}
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=2)
            from .config import private
            private(path)     # у файлі можуть бути токени — лише власнику (Linux)
            self.tr_lbl.setText("✓ Збережено: %s%s" % (path, "" if with_secrets else
                                " (без паролів — на новому пристрої їх треба ввести)"))
        except OSError as e:
            self.tr_lbl.setText("✗ Не вдалося зберегти: %s" % e)

    def do_import(self):
        import json
        import os
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from .config import DEFAULTS
        path, _ = QFileDialog.getOpenFileName(self, "Завантажити налаштування", os.path.expanduser("~"),
                                              "Налаштування DeyeWatch (*.json);;Усі файли (*)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError) as e:
            self.tr_lbl.setText("✗ Не вдалося прочитати файл: %s" % e)
            return
        # підтримуємо і наш файл експорту, і просто скопійований settings.json
        data = doc.get("settings") if isinstance(doc, dict) and doc.get("app") == "DeyeWatch" else doc
        if not isinstance(data, dict):
            self.tr_lbl.setText("✗ Це не файл налаштувань DeyeWatch")
            return
        data = {k: v for k, v in data.items() if k in DEFAULTS and type(v) is type(DEFAULTS[k])
                or (k in DEFAULTS and isinstance(DEFAULTS[k], float) and isinstance(v, int))}
        from .config import is_deye_cloud
        if "cloud_base" in data and not is_deye_cloud(data["cloud_base"]):
            # інакше чужий файл міг би відправити ваші ключі Deye Cloud на сторонній сервер
            data.pop("cloud_base")
        if not data:
            self.tr_lbl.setText("✗ У файлі немає налаштувань DeyeWatch")
            return
        changed = [k for k, v in data.items() if self.app.cfg.get(k) != v]
        if not changed:
            self.tr_lbl.setText("✓ Налаштування у файлі такі самі, як зараз")
            return
        missing = [k for k in self.SECRETS if k not in data]
        msg = "Буде змінено налаштувань: %d.\nПоточні значення замінюються значеннями з файлу." % len(changed)
        if missing:
            msg += "\n\nУ файлі немає паролів і токенів — поточні залишаться без змін."
        if QMessageBox.question(self, "Завантажити налаштування", msg) != QMessageBox.Yes:
            return
        self._loading = True
        try:
            for k, v in data.items():
                if k in self.w:
                    self.set_widget(k, v)
        finally:
            self._loading = False
        if "cloud_password_sha" in data:
            self._pending_pw_sha = data["cloud_password_sha"]
        self.save()
        n = len(changed)
        word = "налаштування" if n % 10 in (1, 2, 3, 4) and n % 100 not in (11, 12, 13, 14) else "налаштувань"
        self.tr_lbl.setText("✓ Завантажено: змінено %d %s (файл %s)" % (n, word, os.path.basename(path)))
        self.app.monitor.poke()
        if self.app.cfg["cloud_enabled"]:
            self.app.monitor.request_sync("імпорт налаштувань")

    def set_widget(self, k, v):
        kind, w = self.w[k]
        if kind == "text":
            w.setText(", ".join(str(x) for x in v) if isinstance(v, list) else str(v))
        elif kind == "bigint":
            w.setText(str(v))
        elif kind == "num":
            w.setValue(v)
        elif kind == "bool":
            w.setChecked(bool(v))
            w.update()
        elif kind == "combo":
            i = w.findData(v)
            if i >= 0:
                w.setCurrentIndex(i)
