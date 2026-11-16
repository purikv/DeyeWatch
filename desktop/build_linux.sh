#!/bin/sh
# Збірка DeyeWatch для Linux (один виконуваний файл) + ярлик у меню програм.
# Потрібні: python3, python3-venv. Для трею в GNOME — розширення AppIndicator.
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --name DeyeWatch deyewatch.py
mkdir -p ~/.local/bin ~/.local/share/applications ~/.local/share/icons
cp dist/DeyeWatch ~/.local/bin/DeyeWatch
cp deyewatch.png ~/.local/share/icons/deyewatch.png
cat > ~/.local/share/applications/deyewatch.desktop <<EOF
[Desktop Entry]
Type=Application
Name=DeyeWatch
Comment=Сповіщення про відключення світла (інвертор Deye)
Exec=$HOME/.local/bin/DeyeWatch
Icon=$HOME/.local/share/icons/deyewatch.png
Categories=Utility;
EOF
echo "Готово: ~/.local/bin/DeyeWatch (є в меню програм)"
