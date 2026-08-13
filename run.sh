#!/usr/bin/env bash
#
# Run FileUploader from source. Sets up whatever is missing on the first run,
# then just starts. Safe to run repeatedly.

set -Eeuo pipefail
cd "$(dirname "$(readlink -f "$0")")"

VENV=".venv"
PY="$VENV/bin/python"

cyan=$'\e[36m'; green=$'\e[32m'; red=$'\e[31m'; dim=$'\e[2m'; off=$'\e[0m'
say() { printf '%s\n' "${cyan}▸${off} $*"; }
ok()  { printf '%s\n' "${green}✓${off} $*"; }
die() { printf '%s\n' "${red}✗${off} $*" >&2; exit 1; }

# A launcher opened by double-click closes the moment it exits, taking the
# error with it. Hold the window open so the message can actually be read.
on_error() {
  printf '%s\n' "${red}✗${off} Startup failed on line $1." >&2
  if [ -t 0 ]; then printf '%s' "${dim}Press Enter to close…${off}"; read -r _; fi
}
trap 'on_error $LINENO' ERR

command -v python3 >/dev/null || die "python3 is not installed."

if [ ! -d "$VENV" ]; then
  # --system-site-packages so pywebview can reach the system PyGObject.
  # Building PyGObject from source needs cairo and girepository headers, and
  # every Linux desktop already ships a working copy.
  say "Creating virtualenv"
  python3 -m venv --system-site-packages "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
fi

if ! "$PY" -c "import fastapi, webview, requests_toolbelt" 2>/dev/null; then
  say "Installing dependencies"
  "$VENV/bin/pip" install -q -r requirements.txt
fi

if ! "$PY" -c "import gi; gi.require_version('WebKit2', '4.1')" 2>/dev/null; then
  printf '%s\n' "${red}!${off} WebKit2GTK is missing, so there will be no native window."
  printf '%s\n' "  Install it with:  sudo apt install python3-gi gir1.2-webkit2-4.1"
  printf '%s\n' "  Falling back to your browser."
fi

ok "Starting"
exec "$PY" desktop.py "$@"
