#!/usr/bin/env bash
# Build a self-contained Living VN: no SDK needed to run the result.
#
# A Ren'Py distribution is the game folder plus the engine plus the platform runtime. The
# runtime lives in the SDK under lib/py3-<platform>, so the same SDK produces both builds
# and the result is a folder you can copy anywhere, launch from a desktop shortcut, or zip
# and hand over.
#
#   tools/build_release.sh [sdk-path]
#
# Linux:   dist/LivingVN-linux-x86_64/LivingVN.sh
# Windows: dist/LivingVN-windows-x86_64/renpy.exe
#
# The Windows build is 64-bit. Ren'Py 8 ships no 32-bit runtime and no Windows 7 support;
# both of those targets need Ren'Py 7.x and its win32 SDK.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SDK="${1:-$HOME/.local/share/renpy/renpy-8.3.7-sdk}"
DIST="$REPO/dist"
VERSION="$(grep -oP 'define config\.version = "\K[^"]+' "$REPO/game/options.rpy")"
NAME="LivingVN-$VERSION"

if [ ! -d "$SDK/renpy" ]; then
    echo "Ren'Py SDK not found at $SDK" >&2
    exit 1
fi

# Development leftovers that must not ship.
strip_game() {
    local target="$1"
    mkdir -p "$target"
    cp -a "$REPO/game/." "$target/"
    rm -rf "$target/saves" "$target/cache" "$target/tools" "$target/__pycache__"
    find "$target" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
    find "$target" -maxdepth 1 -name 'zz_*.rpy*' -delete
    find "$target" -maxdepth 1 -name 'log.txt' -delete
    find "$target" -maxdepth 1 -name 'traceback.txt' -delete
    find "$target" -maxdepth 1 -name 'errors.txt' -delete
}

copy_runtime() {
    local platform="$1" target="$2"
    mkdir -p "$target/lib"
    # Hard links: the runtime is read-only and this keeps a second copy off the disk.
    cp -al "$SDK/renpy" "$target/renpy"
    cp -al "$SDK/lib/py3-$platform" "$target/lib/py3-$platform"
    cp -al "$SDK/lib/python3.9" "$target/lib/python3.9"
    # The runtime binary resolves renpy.py from the folder that holds lib/.
    cp -a "$SDK/renpy.py" "$target/renpy.py"
}

build_linux() {
    local out="$DIST/$NAME-linux-x86_64"
    echo "==> $out"
    rm -rf "$out"
    mkdir -p "$out"
    strip_game "$out/game"
    copy_runtime linux-x86_64 "$out"

    cat > "$out/LivingVN.sh" <<'LAUNCHER'
#!/bin/sh
# Living VN launcher. Runs the bundled runtime, so the SDK is not needed.
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/lib/py3-linux-x86_64/renpy" "$HERE"
LAUNCHER
    chmod +x "$out/LivingVN.sh"

    # Path is absolute because the spec requires it, and Exec stays relative to it. The
    # launcher resolves its own folder, so no `cd` and no quoting tricks are needed.
    cp "$REPO/game/gui/window_icon.png" "$out/window_icon.png" 2>/dev/null || true
    cat > "$out/LivingVN.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Version=1.0
Name=Living VN
Comment=Визуальная новелла, которая пишет себя в процессе игры
Exec=./LivingVN.sh
Path=$out
Icon=$out/window_icon.png
Terminal=false
Categories=Game;RolePlaying;
DESKTOP
    cp "$REPO/game/gui/window_icon.png" "$out/window_icon.png" 2>/dev/null || true
    sed -i 's|game/gui/window_icon.png|window_icon.png|' "$out/LivingVN.desktop"
}

build_windows() {
    local out="$DIST/$NAME-windows-x86_64"
    echo "==> $out"
    rm -rf "$out"
    mkdir -p "$out"
    strip_game "$out/game"
    copy_runtime windows-x86_64 "$out"
    cp "$SDK/lib/py3-windows-x86_64/renpy.exe" "$out/renpy.exe"
    echo "Windows: запускать $NAME-windows-x86_64\\renpy.exe (64-bit Windows 10/11)"
}

mkdir -p "$DIST"
build_linux
build_windows

echo
echo "Готово:"
du -sh "$DIST/$NAME-linux-x86_64" "$DIST/$NAME-windows-x86_64"
