#!/usr/bin/env bash
#
# Build the standalone Linux executable into dist/.
#
#   ./build.sh            one self-contained file  (dist/fileuploader)
#   ./build.sh --folder   a folder that starts faster (dist/fileuploader/)

set -Eeuo pipefail
cd "$(dirname "$(readlink -f "$0")")"

VENV=".venv"
PY="$VENV/bin/python"

green=$'\e[32m'; cyan=$'\e[36m'; red=$'\e[31m'; off=$'\e[0m'
say() { printf '%s\n' "${cyan}▸${off} $*"; }
ok()  { printf '%s\n' "${green}✓${off} $*"; }
die() { printf '%s\n' "${red}✗${off} $*" >&2; exit 1; }

[ -d "$VENV" ] || die "No virtualenv. Run ./run.sh once first."

if ! "$PY" -c "import PyInstaller" 2>/dev/null; then
  say "Installing build tools"
  "$VENV/bin/pip" install -q -r requirements-dev.txt
fi

say "Cleaning previous build"
rm -rf build dist

if [ "${1:-}" = "--folder" ]; then
  say "Building folder distribution"
  "$VENV/bin/pyinstaller" --noconfirm fileuploader.spec
  TARGET="dist/fileuploader/fileuploader"
else
  say "Building single-file executable"
  FILEUPLOADER_ONEFILE=1 "$VENV/bin/pyinstaller" --noconfirm fileuploader.spec
  TARGET="dist/fileuploader"
fi

[ -x "$TARGET" ] || die "Build finished but $TARGET is missing."
ok "Built $TARGET ($(du -h "$TARGET" | cut -f1))"
echo
echo "Run it:      $TARGET"
echo "Install it:  ./install.sh"
