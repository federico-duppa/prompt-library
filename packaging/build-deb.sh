#!/usr/bin/env bash
# Build a self-contained .deb for Prompt Library.
#
# "Self-contained" means PySide6 (and its bundled Qt) ship *inside* the package
# under /opt/prompt-library/lib, so the .deb installs and runs on any reasonably
# recent Debian/Ubuntu desktop regardless of whether the distro packages PySide6
# (the native python3-pyside6.* packages only exist on Ubuntu 24.10+/Debian 13+).
#
# Run it on a Debian/Ubuntu host (ideally the OLDEST distro you want to support,
# e.g. Ubuntu 22.04, so the dependency names resolve everywhere). It needs
# internet access to download the PySide6 wheel.
#
#   packaging/build-deb.sh                 # build for the host architecture
#   PRUNE=1 packaging/build-deb.sh         # also drop unused Qt extras (smaller)
#
# Output: dist/prompt-library_<version>_<arch>.deb
set -euo pipefail

# --- locate the project ------------------------------------------------------
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

PKG="prompt-library"
PREFIX="/opt/prompt-library"          # where the app + vendored libs live
LIBDIR_REL="$PREFIX/lib"              # PYTHONPATH target

# Version is single-sourced in prompt_library/__init__.py (pyproject reads it
# dynamically via hatchling), so parse it from there.
VERSION="$(grep -m1 '^__version__' prompt_library/__init__.py | sed -E 's/.*"([^"]+)".*/\1/')"
ARCH="$(dpkg --print-architecture)"
MAINTAINER="Federico De Malmayne Duppa <fduppa@gmail.com>"

STAGE="$ROOT/build/deb/${PKG}_${VERSION}_${ARCH}"
OUT="$ROOT/dist"

echo "==> Building ${PKG} ${VERSION} (${ARCH})"

# --- clean staging -----------------------------------------------------------
rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" \
         "$STAGE$LIBDIR_REL" \
         "$STAGE/usr/bin" \
         "$STAGE/usr/share/applications" \
         "$STAGE/etc/xdg/autostart" \
         "$STAGE/usr/share/icons/hicolor/128x128/apps" \
         "$STAGE/usr/share/doc/$PKG"

# --- vendor the app + PySide6 into the lib dir -------------------------------
# pip --target installs the project and its deps (PySide6-Essentials) as plain
# files; no venv, so there are no absolute paths to relocate. The launcher just
# points PYTHONPATH at this dir, exactly like the source launcher does.
echo "==> Installing app + PySide6 into $LIBDIR_REL (downloads the wheel)…"
python3 -m pip install \
    --quiet --upgrade \
    --target "$STAGE$LIBDIR_REL" \
    --only-binary=:all: \
    "$ROOT"

# pip --target drops console scripts and a bin/ we don't use; trim noise.
rm -rf "$STAGE$LIBDIR_REL/bin" "$STAGE$LIBDIR_REL"/*.dist-info/RECORD 2>/dev/null || true

# Optional: shrink by removing Qt pieces this app never imports (Core/Gui/
# Widgets/Network only). Off by default because Qt modules interlink; the dirs
# listed here are safe extras (examples, sources, translations, qml runtime).
if [[ "${PRUNE:-0}" == "1" ]]; then
    echo "==> Pruning unused Qt extras…"
    PS="$STAGE$LIBDIR_REL/PySide6"
    rm -rf "$PS/examples" "$PS/scripts" "$PS/glue" "$PS/typesystems" \
           "$PS/support" "$PS/Qt/qml" "$PS/Qt/translations" \
           "$PS/Qt/resources" 2>/dev/null || true
    find "$STAGE$LIBDIR_REL" -name '*.pyi' -delete 2>/dev/null || true
fi

# --- launcher ----------------------------------------------------------------
cat > "$STAGE/usr/bin/$PKG" <<EOF
#!/usr/bin/env bash
# Run Prompt Library against its vendored PySide6 using the system python3.
set -euo pipefail
exec env PYTHONPATH="$LIBDIR_REL\${PYTHONPATH:+:\$PYTHONPATH}" \\
     python3 -m prompt_library "\$@"
EOF
chmod 0755 "$STAGE/usr/bin/$PKG"

# --- hotkey helper (the app invokes this on first launch) --------------------
install -m 0755 "$ROOT/setup-hotkey.sh" "$STAGE/usr/bin/$PKG-hotkey"

# --- icon (generated at build time; never run Qt in postinst) ----------------
echo "==> Generating icon…"
ICON="$STAGE/usr/share/icons/hicolor/128x128/apps/$PKG.png"
QT_QPA_PLATFORM=offscreen PYTHONPATH="$STAGE$LIBDIR_REL" python3 - "$ICON" <<'PY'
import sys
from PySide6.QtGui import QGuiApplication
from prompt_library.app import make_icon
app = QGuiApplication([])
make_icon().pixmap(128, 128).save(sys.argv[1], "PNG")
PY

# --- desktop entries ---------------------------------------------------------
# Menu entry (--show wakes/opens the window).
cat > "$STAGE/usr/share/applications/$PKG.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Prompt Library
Comment=Copy prompts to the clipboard
Exec=/usr/bin/$PKG --show
Icon=$PKG
Terminal=false
Categories=Utility;
StartupNotify=false
EOF

# System-wide autostart (--tray starts hidden) — applies to every user account.
cat > "$STAGE/etc/xdg/autostart/$PKG.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Prompt Library
Comment=Copy prompts to the clipboard
Exec=/usr/bin/$PKG --tray
Icon=$PKG
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
EOF

# --- docs --------------------------------------------------------------------
install -m 0644 "$ROOT/LICENSE" "$STAGE/usr/share/doc/$PKG/LICENSE"
install -m 0644 "$ROOT/NOTICE" "$STAGE/usr/share/doc/$PKG/NOTICE" 2>/dev/null || true

# --- sanity check: are any bundled .so files missing a system lib? -----------
# This validates the curated Depends below. ldd can't see dlopen'd plugins
# (xcb, etc.), which is why the list is curated rather than auto-generated.
echo "==> Checking bundled libraries for unresolved dependencies…"
MISSING="$(find "$STAGE$LIBDIR_REL" -name '*.so*' -type f -print0 \
    | LD_LIBRARY_PATH="$STAGE$LIBDIR_REL/PySide6/Qt/lib" xargs -0 ldd 2>/dev/null \
    | awk '/not found/ {print $1}' | sort -u || true)"
if [[ -n "$MISSING" ]]; then
    echo "    WARNING: these libraries were not found on the build host:" >&2
    echo "$MISSING" | sed 's/^/      /' >&2
    echo "    Add the providing packages to Depends in this script." >&2
fi

# --- control file ------------------------------------------------------------
INSTALLED_KB="$(du -sk "$STAGE" | cut -f1)"

# Curated runtime deps for a PySide6/Qt6 xcb (X11) + Wayland desktop app.
# `a | b` alternatives cover Ubuntu 24.04's t64 renames while staying valid on
# pre-t64 distros (22.04, Debian 12). PySide6 bundles Qt itself, so these are
# only the low-level system libs Qt links against or dlopens.
DEPENDS="python3 (>= 3.9), \
libc6, libstdc++6, zlib1g, \
libglib2.0-0t64 | libglib2.0-0, \
libdbus-1-3, \
libgl1 | libgl1-mesa-glx, libegl1, libopengl0, \
libxkbcommon0, libxkbcommon-x11-0, \
libfontconfig1, libfreetype6, \
libx11-6, libx11-xcb1, \
libxcb1, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, \
libxcb-randr0, libxcb-render-util0, libxcb-render0, libxcb-shape0, \
libxcb-shm0, libxcb-sync1, libxcb-util1, libxcb-xfixes0, libxcb-xinerama0, \
libxcb-xkb1, \
libxkbcommon0"

cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Architecture: $ARCH
Maintainer: $MAINTAINER
Installed-Size: $INSTALLED_KB
Depends: $DEPENDS
Recommends: gnome-shell-extension-appindicator | libappindicator3-1
Section: utils
Priority: optional
Homepage: https://github.com/federico-duppa/prompt-library
Description: Tray app to copy reusable prompts to the clipboard
 Prompt Library scans a folder for *.prompt files and shows them as clickable
 cards in a centered overlay. Clicking a card (or pressing Alt+1..9) copies that
 prompt to the clipboard and hides back to the tray. Bundles its own PySide6/Qt
 runtime, so it does not depend on the distribution's Qt packages.
EOF

# --- maintainer scripts ------------------------------------------------------
cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    update-desktop-database -q /usr/share/applications 2>/dev/null || true
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor 2>/dev/null || true
    fi
fi
exit 0
EOF
chmod 0755 "$STAGE/DEBIAN/postinst"

cat > "$STAGE/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    update-desktop-database -q /usr/share/applications 2>/dev/null || true
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor 2>/dev/null || true
    fi
fi
exit 0
EOF
chmod 0755 "$STAGE/DEBIAN/postrm"

# --- build -------------------------------------------------------------------
mkdir -p "$OUT"
DEB="$OUT/${PKG}_${VERSION}_${ARCH}.deb"
echo "==> Packing $DEB"
dpkg-deb --build --root-owner-group "$STAGE" "$DEB"

echo
echo "Built: $DEB"
echo "Size:  $(du -h "$DEB" | cut -f1)"
echo
echo "Inspect:  dpkg-deb --info '$DEB'  /  dpkg-deb --contents '$DEB'"
echo "Install:  sudo apt install '$DEB'   (resolves dependencies)"
