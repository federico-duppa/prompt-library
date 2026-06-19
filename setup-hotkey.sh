#!/usr/bin/env bash
# Registers (or removes with --remove) a GNOME global hotkey that shows the app.
# Works on X11 and Wayland because it is GNOME that captures the key and runs the command.
#
#   ./setup-hotkey.sh                  # uses <Super><Shift>p
#   ./setup-hotkey.sh '<Control><Alt>p'
#   ./setup-hotkey.sh --remove
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
LAUNCHER="$HERE/prompt-library"

SCHEMA="org.gnome.settings-daemon.plugins.media-keys"
LISTKEY="custom-keybindings"
NAME="prompt-library"
KEYPATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/${NAME}/"
SUB="${SCHEMA}.custom-keybinding:${KEYPATH}"

current="$(gsettings get "$SCHEMA" "$LISTKEY")"

if [[ "${1:-}" == "--remove" ]]; then
    if [[ "$current" == *"$KEYPATH"* ]]; then
        # remove this entry from the list
        new="$(printf '%s' "$current" | sed "s|'${KEYPATH}', ||; s|, '${KEYPATH}'||; s|'${KEYPATH}'||")"
        [[ "$new" == "[]" || "$new" == "" ]] && new="@as []"
        gsettings set "$SCHEMA" "$LISTKEY" "$new"
    fi
    gsettings reset-recursively "$SUB" 2>/dev/null || true
    echo "Hotkey removed."
    exit 0
fi

BINDING="${1:-<Super><Shift>p}"

# 1) make sure the path is in the list of custom hotkeys
if [[ "$current" != *"$KEYPATH"* ]]; then
    if [[ "$current" == "@as []" || "$current" == "[]" ]]; then
        new="['${KEYPATH}']"
    else
        new="${current%]}, '${KEYPATH}']"
    fi
    gsettings set "$SCHEMA" "$LISTKEY" "$new"
fi

# 2) set name, command and key combination
gsettings set "$SUB" name "Prompt Library"
gsettings set "$SUB" command "${LAUNCHER} --show"
gsettings set "$SUB" binding "$BINDING"

echo "Hotkey configured:"
echo "  ${BINDING}  ->  ${LAUNCHER} --show"
echo
echo "Verification:"
gsettings get "$SUB" binding
gsettings get "$SUB" command
