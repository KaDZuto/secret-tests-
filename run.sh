#!/usr/bin/env bash
# Permanent launcher for the Living VN project.
#
# The Ren'Py 8.3.7 SDK lives outside /tmp, so this survives a reboot:
#   SDK     ~/.local/share/renpy/renpy-8.3.7-sdk
#   project ~/Downloads/LivingVN_MVP
#
# Any argument is passed to Ren'Py, so `run.sh lint` lints the project.

set -euo pipefail

SDK="${LIVINGVN_RENPY_SDK:-$HOME/.local/share/renpy/renpy-8.3.7-sdk}"
PROJECT="${LIVINGVN_PROJECT:-$HOME/Downloads/LivingVN_MVP}"

if [ ! -x "$SDK/renpy.sh" ]; then
    echo "Ren'Py SDK not found at $SDK" >&2
    echo "Set LIVINGVN_RENPY_SDK to the directory containing renpy.sh." >&2
    exit 1
fi

if [ ! -d "$PROJECT/game" ]; then
    echo "Project not found at $PROJECT" >&2
    echo "Set LIVINGVN_PROJECT to the directory containing game/." >&2
    exit 1
fi

cd "$SDK"
exec ./renpy.sh "$PROJECT" "$@"
