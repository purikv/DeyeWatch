# DeyeWatch Router Bot — сповіщення про відключення світла в Telegram

> Легка версія DeyeWatch без графічного інтерфейсу: один файл на Python, що працює цілодобово
> на роутері (або будь-якому Linux-пристрої) і надсилає сповіщення в Telegram.
> Для комп'ютера з графіками й аналітикою дивіться [головний README](../README.md).

Бот опитує гібридний інвертор **Deye SUN-6K-SG03LP1** через WiFi-стік Solarman
у локальній мережі (протокол Solarman V5, порт 8899) і пише в Telegram:

- 🔴 світло зникло / 🟢 світло з'явилося (з тривалістю);
- 🪫 низький заряд батареї під час відключення (пороги 50 / 30 / 15 %);
- ⚠️ немає зв'язку з інвертором / ✅ зв'язок відновлено;
- команди `/status`, `/history [N]`, `/id`.

Потрібен лише Python 3 без додаткових бібліотек. Працює на роутері ASUS TUF-AX3000 V2
з прошивкою Asuswrt-Merlin (форк Gnuton) + Entware на USB-флешці.

| Файл | Призначення |
|---|---|
| `deyebot.py` | сам бот |
| `config.example.json` | приклад налаштувань → скопіювати в `config.json` |
| `S99deyebot` | автозапуск на роутері (Entware) |
| `fake_logger.py` | імітатор WiFi-стіка для перевірки без інвертора |

---

## Як визначається відключення

Регістр `0x0096` — напруга мережі L1. Якщо вона нижча за `grid_min_voltage`
(170 В) у `confirm_polls` (2) опитуваннях поспіль — світла немає. Опитування раз на 10 с,
тож сповіщення приходить приблизно через 10–20 с після події.

Адреси регістрів взято з карти `deye_hybrid.yaml` проєкту
[StephanJoubert/home_assistant_solarman](https://github.com/StephanJoubert/home_assistant_solarman).

> **Важливо:** роутер, оптичний термінал/модем провайдера і WiFi-стік мають живитися від
> виходу інвертора (LOAD/резерв). Якщо під час відключення зникне інтернет у провайдера,
> повідомлення не загубляться: вони стоять у черзі (у `state.json`) і прийдуть, коли зв'язок
> повернеться, з правильним часом події.

---

## Крок 1. Telegram-бот

1. У Telegram напишіть **@BotFather** → `/newbot` → задайте назву → отримайте **токен**.
2. Скопіюйте `config.example.json` у `config.json`, вставте токен у `telegram_token`.
3. `chat_ids` поки залиште порожнім `[]`. Коли бот запуститься, кожен, хто має отримувати
   сповіщення, пише боту `/start`, а бот відповідає йому його `chat_id`. Додайте ці числа
   в `chat_ids` і перезапустіть бота.
   Для групи: додайте бота в групу, напишіть у групі `/id@ім'я_бота`; `chat_id` групи буде від'ємним числом.

## Крок 2. Дані WiFi-стіка

- **Серійний номер логера** (`logger_serial`) — 10 цифр на наклейці стіка (SN),
  або у вебінтерфейсі стіка `http://<IP стіка>` (зазвичай логін/пароль admin/admin).
  Це **не** серійний номер інвертора.
- **IP стіка** (`logger_ip`) — у вебінтерфейсі роутера: *Network Map → Clients*.
  Закріпіть за ним постійну адресу: *LAN → DHCP Server → Manual Assignment*.

## Крок 3. Перевірка з комп'ютера (до налаштування роутера)

На комп'ютері, у теці `router-bot` репозиторію:

```bash
python deyebot.py -c config.json --probe
```

Має вивести напругу мережі, SOC батареї тощо. Якщо `timed out` — перевірте серійний номер
логера (при неправильному номері стік просто мовчить) і IP.
Деякі нові стіки не підтримують локальний порт 8899 — тоді цей спосіб не підійде;
опишіть модель стіка в [issue](https://github.com/purikv/DeyeWatch/issues).

```bash
python deyebot.py -c config.json --test-telegram
```

Можна запустити бота на ПК, щоб зібрати `chat_id` (Ctrl+C — зупинити):

```bash
python deyebot.py -c config.json
```

Перевірка без інвертора: у `config.json` вкажіть `"logger_ip": "127.0.0.1"` і серійний
`2712345678`, запустіть `python fake_logger.py`, а в іншому вікні — бота. Запис `0` у файл
`fake_voltage.txt` імітує відключення, `230` — появу світла.

## Крок 4. Прошивка роутера (Asuswrt-Merlin, форк Gnuton)

Заводська прошивка ASUS не дозволяє запускати власні програми. Офіційний Merlin
TUF-AX3000 V2 не підтримує, але є форк **Gnuton** зі збірками саме для цієї моделі:
<https://github.com/gnuton/asuswrt-merlin.ng/releases>.

1. *Administration → Restore/Save/Upload Setting* — збережіть резервну копію налаштувань.
2. Завантажте з релізів Gnuton файл `TUF-AX3000_V2_..._nand_squashfs.pkgtb`
   (варіант `_tuf_` — з фірмовою темою TUF; беріть стабільну збірку `gnuton1`, не `beta`).
3. *Administration → Firmware Upgrade → Upload* — вкажіть файл, дочекайтеся перезавантаження.
4. Повернутися на заводську прошивку можна так само, завантаживши офіційний файл ASUS.

> Це стороння прошивка — ризик лежить на вас. Не вимикайте живлення під час прошивки.

## Крок 5. Entware і Python на флешці

1. *Administration → System*: **Enable JFFS custom scripts and configs = Yes**,
   **Enable SSH = LAN only**. Застосувати.
2. Вставте флешку в USB роутера.
3. На ПК відкрийте термінал: `ssh admin@192.168.50.1` (адреса вашого роутера, пароль — від вебінтерфейсу).
4. Запустіть `amtm`:
   - `fd` — відформатувати флешку в **ext4** (усі дані на ній буде стерто);
   - `ep` — встановити Entware.
5. Встановіть Python:

```bash
opkg update && opkg install python3 ca-bundle
```

```bash
python3 -c "import ssl, json, urllib.request; print('OK')"
```

## Крок 6. Встановлення бота на роутер

На роутері:

```bash
mkdir -p /opt/deyebot
```

На комп'ютері (з теки `router-bot`; ключ `-O` потрібен, бо на роутері немає SFTP):

```bash
scp -O deyebot.py config.json S99deyebot admin@192.168.50.1:/opt/deyebot/
```

Знову на роутері:

```bash
mv /opt/deyebot/S99deyebot /opt/etc/init.d/ && chmod +x /opt/etc/init.d/S99deyebot
```

```bash
python3 /opt/deyebot/deyebot.py -c /opt/deyebot/config.json --probe
```

```bash
/opt/etc/init.d/S99deyebot start
```

Сторож (перезапуск, якщо процес упаде) — додати рядок у `/jffs/scripts/services-start`:

```bash
echo 'cru a deyebot "*/5 * * * * /opt/etc/init.d/S99deyebot check"' >> /jffs/scripts/services-start && chmod +x /jffs/scripts/services-start
```

Після перезавантаження роутера Entware сам запускає `S99deyebot`.

Корисне:

```bash
tail -f /opt/deyebot/deyebot.log
```

```bash
/opt/etc/init.d/S99deyebot restart
```

---

## Налаштування (`config.json`)

| Параметр | За замовч. | Що це |
|---|---|---|
| `name` | Дім | назва в повідомленнях |
| `telegram_token` | — | токен від @BotFather |
| `chat_ids` | — | хто отримує сповіщення і може виконувати команди |
| `logger_ip`, `logger_serial`, `logger_port` | —, —, 8899 | WiFi-стік |
| `poll_interval_sec` | 10 | частота опитування, с |
| `grid_min_voltage` | 170 | нижче цієї напруги — світла немає |
| `confirm_polls` | 2 | скільки опитувань підтверджують зміну (захист від стрибків) |
| `offline_alert_polls` | 6 | скільки невдалих опитувань → «немає зв'язку з інвертором» |
| `low_soc_thresholds` | [50, 30, 15] | пороги заряду для попереджень під час відключення |
| `timezone` | Київ | часовий пояс у форматі POSIX TZ |

Історія відключень і черга повідомлень зберігаються в `state.json` поруч з конфігом.
