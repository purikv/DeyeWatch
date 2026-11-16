#!/bin/sh
# Встановлення DeyeWatch для Linux (без прав root, у домашню теку).
#   sh install.sh            — встановити / оновити
#   sh install.sh --uninstall — видалити (налаштування та історія в ~/.config/deyewatch лишаються)
set -e

APP_DIR="$HOME/.local/share/deyewatch"
BIN="$HOME/.local/bin/deyewatch"
DESKTOP="$HOME/.local/share/applications/deyewatch.desktop"
ICON="$HOME/.local/share/icons/hicolor/256x256/apps/deyewatch.png"
SRC="$(cd "$(dirname "$0")" && pwd)"

say()  { printf '\033[1;32m›\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m✗\033[0m %s\n' "$*"; exit 1; }

if [ "$1" = "--uninstall" ]; then
    rm -rf "$APP_DIR" "$BIN" "$DESKTOP" "$ICON" "$HOME/.config/autostart/deyewatch.desktop"
    say "DeyeWatch видалено. Налаштування й історія лишились у ~/.config/deyewatch"
    exit 0
fi

# --- Python
PY=""
for p in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
    if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
        PY="$p"; break
    fi
done
[ -n "$PY" ] || die "Потрібен Python 3.9+. Ubuntu/Debian: sudo apt install python3 python3-venv"
"$PY" -c 'import venv, ensurepip' 2>/dev/null || die "Немає модуля venv. Ubuntu/Debian: sudo apt install python3-venv  ·  Fedora: вже є"
say "Python: $($PY --version)"

# --- Файли програми
say "Копіюю програму в $APP_DIR"
mkdir -p "$APP_DIR"
rm -rf "$APP_DIR/app"
cp -r "$SRC/app" "$APP_DIR/app"

# --- Віртуальне середовище з PySide6
if [ ! -x "$APP_DIR/venv/bin/python" ]; then
    say "Створюю віртуальне середовище"
    "$PY" -m venv "$APP_DIR/venv"
fi
say "Встановлюю PySide6 (≈ 100 МБ, один раз)"
"$APP_DIR/venv/bin/python" -m pip install --quiet --upgrade pip
"$APP_DIR/venv/bin/python" -m pip install --quiet -r "$SRC/app/requirements.txt"

# --- Запускач
mkdir -p "$(dirname "$BIN")"
cat > "$BIN" <<EOF
#!/bin/sh
# Сповіщення в куті екрана потребують X11/XWayland (на чистому Wayland вікна не можуть самі вибрати місце)
export QT_QPA_PLATFORM="\${QT_QPA_PLATFORM:-xcb;wayland}"
export DEYEWATCH_LAUNCHER="$BIN"
exec "$APP_DIR/venv/bin/python" "$APP_DIR/app/deyewatch.py" "\$@"
EOF
chmod +x "$BIN"

# --- Іконка та ярлик у меню
mkdir -p "$(dirname "$ICON")" "$(dirname "$DESKTOP")"
cp "$SRC/app/deyewatch.png" "$ICON"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=DeyeWatch
GenericName=Відключення світла
Comment=Сповіщення про відключення світла та статистика інвертора Deye
Exec=$BIN
Icon=deyewatch
Terminal=false
Categories=Utility;Monitor;
StartupWMClass=DeyeWatch
EOF
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$(dirname "$DESKTOP")" 2>/dev/null || true

# --- Системні бібліотеки Qt (перевірка, без встановлення)
missing=""
if command -v ldconfig >/dev/null 2>&1; then
    for lib in libxcb-cursor.so.0 libxkbcommon-x11.so.0 libEGL.so.1 libfontconfig.so.1; do
        ldconfig -p 2>/dev/null | grep -q "$lib" || missing="$missing $lib"
    done
fi
if [ -n "$missing" ]; then
    warn "Не знайдено бібліотек:$missing"
    warn "Ubuntu/Debian: sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1 libfontconfig1"
    warn "Fedora:        sudo dnf install xcb-util-cursor libxkbcommon-x11 mesa-libEGL fontconfig"
fi

case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) warn "Додайте ~/.local/bin у PATH або запускайте з меню програм" ;; esac
if [ "${XDG_CURRENT_DESKTOP#*GNOME}" != "$XDG_CURRENT_DESKTOP" ]; then
    warn "GNOME: для іконки в треї увімкніть розширення «AppIndicator and KStatusNotifierItem Support»"
fi

say "Готово! Запуск: меню програм → DeyeWatch, або команда: deyewatch"
