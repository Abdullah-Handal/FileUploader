#!/usr/bin/env bash
#
# Put FileUploader in the applications menu.
#
#   ./install.sh                    use the executable from ./build.sh
#   ./install.sh ~/Downloads/fileuploader   use one downloaded from Releases

set -Eeuo pipefail
HERE="$(dirname "$(readlink -f "$0")")"

green=$'\e[32m'; red=$'\e[31m'; off=$'\e[0m'
die() { printf '%s\n' "${red}✗${off} $*" >&2; exit 1; }

if [ $# -gt 0 ]; then
  [ -f "$1" ] || die "No such file: $1"
  TARGET="$(readlink -f "$1")"
  # A browser download arrives without the executable bit.
  [ -x "$TARGET" ] || chmod +x "$TARGET"
elif [ -x "$HERE/dist/fileuploader" ];              then TARGET="$HERE/dist/fileuploader"
elif [ -x "$HERE/dist/fileuploader/fileuploader" ]; then TARGET="$HERE/dist/fileuploader/fileuploader"
elif [ -x "$HERE/fileuploader" ];                   then TARGET="$HERE/fileuploader"
else die "No executable found. Run ./build.sh, or pass the path to a downloaded one."
fi

cd "$HERE"

APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$APPS"

cat > "$APPS/fileuploader.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=FileUploader
GenericName=Temporary File Sharing
Comment=Share a file or some text as a short link that expires
Exec=$TARGET
Path=$(dirname "$TARGET")
Icon=document-send
Terminal=false
Categories=Utility;FileTransfer;
Keywords=upload;share;link;temporary;shorten;
DESKTOP

chmod +x "$APPS/fileuploader.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true

printf '%s\n' "${green}✓${off} Installed. Look for \"FileUploader\" in your applications."
printf '%s\n' "  Pointing at: $TARGET"
