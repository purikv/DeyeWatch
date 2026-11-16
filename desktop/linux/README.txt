DeyeWatch для Linux
====================

Встановлення (без root, у домашню теку):

    tar xzf DeyeWatch-linux.tar.gz
    cd DeyeWatch-linux
    sh install.sh

Інсталятор створює власне середовище Python, ставить у нього PySide6, додає
DeyeWatch у меню програм і команду `deyewatch`. Потрібні Python 3.9+ та python3-venv
(Ubuntu/Debian: sudo apt install python3 python3-venv).

Оновлення — розпакувати новий архів і знову виконати `sh install.sh`.
Видалення — `sh install.sh --uninstall`.

Налаштування та історія: ~/.config/deyewatch
Автозапуск: Налаштування → «Запускати разом із системою».

Працює на x86_64 і ARM64 (наприклад, Raspberry Pi 4/5 з 64-бітною ОС).
GNOME: для іконки в треї потрібне розширення «AppIndicator and KStatusNotifierItem Support».
