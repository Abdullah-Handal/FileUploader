#!/usr/bin/env bash
#
# Put FileUploader in the applications menu, pointing at the built executable.
# Run ./build.sh first.

set -Eeuo pipefail
cd "$(dirname "$(readlink -f "$0")")"

green=$'\e[32m'; red=$'\e[31m'; off=$'\e[0m'
die() { printf '%s\n' "${red}✗${off} $*" >&2; exit 1; }

if   [ -x "dist/fileuploader" ];              then TARGET="$PWD/dist/fileuploader"
elif [ -x "dist/fileuploader/fileuploader" ]; then TARGET="$PWD/dist/fileuploader/fileuploader"
else die "No build found. Run ./build.sh first."
fi

APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$APPS"

cat > "$APPS/fileuploader.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=FileUploader
GenericName=Temporary File Sharing
Comment=Share a file or some text as a short link that expires
Exec=$TARGET
Path=$PWD
Icon=document-send
Terminal=false
Categories=Utility;FileTransfer;
Keywords=upload;share;link;temporary;shorten;
DESKTOP

chmod +x "$APPS/fileuploader.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true

printf '%s\n' "${green}✓${off} Installed. Look for \"FileUploader\" in your applications."
printf '%s\n' "  Pointing at: $TARGET"
