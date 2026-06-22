#!/usr/bin/env bash
# Full installation: venv + dependencies + icon + menu entry + autostart + global hotkey.
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
LAUNCHER="$HERE/prompt-library"
BINDING="${1:-<Super><Shift>p}"

echo "==> Creating virtual environment…"
if [[ ! -d "$HERE/.venv" ]]; then
    python3 -m venv "$HERE/.venv"
fi
"$HERE/.venv/bin/python" -m pip install --upgrade pip -q
echo "==> Installing the app and PySide6 (this may take a while)…"
"$HERE/.venv/bin/python" -m pip install -q -e "$HERE"

chmod +x "$LAUNCHER" "$HERE/setup-hotkey.sh"

echo "==> Generating icon…"
ICON_DIR="$HOME/.local/share/icons"
mkdir -p "$ICON_DIR"
ICON_PATH="$ICON_DIR/prompt-library.png"
QT_QPA_PLATFORM=offscreen PYTHONPATH="$HERE" "$HERE/.venv/bin/python" - "$ICON_PATH" <<'PY'
import sys
from PySide6.QtGui import QGuiApplication
from prompt_library.app import make_icon
app = QGuiApplication([])
make_icon().pixmap(128, 128).save(sys.argv[1], "PNG")
PY

echo "==> Creating menu entry…"
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"
cat > "$APPS_DIR/prompt-library.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Prompt Library
Comment=Copy prompts to the clipboard
Exec=$LAUNCHER --show
Icon=$ICON_PATH
Terminal=false
Categories=Utility;
StartupNotify=false
EOF

echo "==> Configuring autostart (starts hidden in the tray)…"
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
cat > "$AUTOSTART_DIR/prompt-library.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Prompt Library
Comment=Copy prompts to the clipboard
Exec=$LAUNCHER --tray
Icon=$ICON_PATH
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
EOF

echo "==> Registering global hotkey ($BINDING)…"
"$HERE/setup-hotkey.sh" "$BINDING"

echo
echo "Done. Launch the app now with:  $LAUNCHER"
echo "The global hotkey $BINDING will show it at any time."
