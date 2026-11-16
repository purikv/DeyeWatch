# Розробка

[← До README](../README.md)

## Структура репозиторію

```
DeyeWatch/
├── desktop/                 Програма для Windows і Linux (Python + PySide6)
│   ├── deyewatch.py         Точка входу
│   ├── dw/
│   │   ├── core.py          Протокол Solarman V5, регістри, автопошук стіка, Telegram API
│   │   ├── monitor.py       Фонове опитування, події, сповіщення, синхронізація з хмарою
│   │   ├── store.py         SQLite: історія, відключення, аналітика
│   │   ├── cloud.py         Deye Cloud OpenAPI: догрузка пропущеної історії
│   │   ├── messages.py      Тексти сповіщень (спільні для робочого столу й Telegram)
│   │   ├── app.py           Головне вікно, трей, життєвий цикл
│   │   ├── pages.py         Екрани: Огляд, Відключення, Якість мережі, Енергія, Батарея
│   │   ├── settings_page.py Налаштування, експорт/імпорт
│   │   ├── widgets.py       Власні віджети: графіки, теплова карта, схема потоків, кільце заряду
│   │   ├── toast.py         Спливаючі сповіщення
│   │   ├── theme.py         Палітри світлої/темної теми, стилі
│   │   ├── icons.py         Векторні іконки
│   │   └── config.py        Налаштування за замовчуванням, автозапуск
│   ├── linux/               Інсталятор для Linux і збірка .deb
│   ├── tools/               Скріншоти для документації
│   ├── build_windows.bat    Збірка DeyeWatch.exe
│   └── build_linux.sh       Збірка одного виконуваного файлу для Linux
├── router-bot/              Легкий Telegram-бот для роутера (лише стандартна бібліотека Python)
└── docs/                    Документація та сайт продукту (GitHub Pages)
```

Версія програми — у `desktop/dw/__init__.py` (`__version__`); її використовують збірка `.deb` і вікно налаштувань.

## Запуск для розробки

```bash
cd desktop && pip install -r requirements.txt
```

```bash
python deyewatch.py
```

Окрему теку налаштувань і історії (щоб не чіпати робочу) задає змінна `DEYEWATCH_HOME`:

```bash
DEYEWATCH_HOME=/tmp/deyewatch-dev python deyewatch.py
```

З `DEYEWATCH_HOME` програма не змінює системний автозапуск.

## Перевірка без інвертора

`router-bot/fake_logger.py` імітує WiFi-стік на `127.0.0.1:8899` (серійний номер `2712345678`).
Запис числа у файл `fake_voltage.txt` поруч задає напругу мережі: `0` — відключення, `230` — світло є.

## Збірка Windows

Потрібен Python 3.9+ для Windows:

```bash
cd desktop && build_windows.bat
```

Результат — один файл `desktop/dist/DeyeWatch.exe` (PyInstaller, без консолі).

## Збірка .deb

Працює на будь-якій ОС, зокрема на Windows (`dpkg` не потрібен):

```bash
cd desktop && python linux/build_deb.py
```

Скрипт завантажує колеса PySide6 для Linux x86_64 у `desktop/build_deb/wheels` (≈ 180 МБ, один раз)
і збирає `desktop/dist/deyewatch_<версія>_amd64.deb`. У пакеті — два покоління PySide6:
6.12 (glibc ≥ 2.34, Python 3.10–3.15) і 6.9 (glibc ≥ 2.28, Python 3.9–3.13); `postinst` створює
середовище в `/opt/deyewatch/venv` і ставить те, що підходить системі, без інтернету.

## Архів для Linux

Вміст `DeyeWatch-linux.tar.gz`: `install.sh`, `README.txt` (з `desktop/linux/`) і тека `app/` з
`deyewatch.py`, `requirements.txt`, `deyewatch.png` та `dw/*.py`.

## Скріншоти

```bash
cd desktop && python tools/make_screenshots.py
```

Скрипт генерує **вигадану** історію за 35 днів (відключення за графіком, сонце, генератор, батарея),
запускає програму без опитування інвертора й зберігає знімки всіх екранів у світлій і темній темі в
`docs/assets/screenshots/`. Реальних даних у знімках немає.

## Реліз

1. Підніміть `__version__` у `desktop/dw/__init__.py` і допишіть [CHANGELOG](../CHANGELOG.md).
2. Зберіть `DeyeWatch.exe`, `.deb` і архів для Linux.
3. Створіть реліз на GitHub із тегом `v<версія>` і додайте файли з **незмінними іменами** —
   на них посилаються README й сайт:
   `DeyeWatch.exe`, `deyewatch_amd64.deb`, `DeyeWatch-linux.tar.gz`.
