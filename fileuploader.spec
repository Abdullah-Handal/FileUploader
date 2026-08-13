# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build for the desktop app.

    pyinstaller fileuploader.spec                  -> dist/fileuploader/ (a folder)
    FILEUPLOADER_ONEFILE=1 pyinstaller fileuploader.spec   -> dist/fileuploader (one file)
"""

import os

from PyInstaller.utils.hooks import collect_submodules

ONEFILE = os.environ.get("FILEUPLOADER_ONEFILE") == "1"

datas = [("web", "web")]

hiddenimports = collect_submodules("uvicorn") + [
    # pywebview picks its backend at runtime, so static analysis never sees this.
    "webview.platforms.gtk",
]

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Trimmed: large libraries pulled in transitively that this app never uses.
    excludes=[
        "tkinter", "matplotlib", "numpy", "PIL", "pytest",
        "PySide6", "PyQt5", "PyQt6",
        # Optional uvicorn accelerators; desktop.py asks for asyncio/h11 instead.
        "uvloop", "httptools",
    ],
    noarchive=False,
)

# PyInstaller follows GTK's data files and sweeps up every installed icon and
# desktop theme -- well over a hundred megabytes of artwork for widgets this app
# never draws, since the entire interface is HTML rendered inside the webview.
# GTK reads these from the system at runtime anyway.
_DROP_PREFIXES = (
    "share/icons",
    "share/themes",
    "share/fontconfig",
    "share/mime",
)


def _wanted(entry):
    dest = entry[0].replace("\\", "/")
    return not dest.startswith(_DROP_PREFIXES)


_before = len(a.datas)
a.datas = [entry for entry in a.datas if _wanted(entry)]
print(f"[fileuploader] dropped {_before - len(a.datas)} theme/icon data files")

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    *([] if ONEFILE else [[]]),
    *([a.binaries, a.datas] if ONEFILE else []),
    exclude_binaries=not ONEFILE,
    name="fileuploader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

if not ONEFILE:
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="fileuploader",
    )
