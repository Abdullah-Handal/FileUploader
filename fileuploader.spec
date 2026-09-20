# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build for the desktop app.

    pyinstaller fileuploader.spec                  -> dist/fileuploader/ (a folder)
    FILEUPLOADER_ONEFILE=1 pyinstaller fileuploader.spec   -> dist/fileuploader (one file)
"""

import os
import sys

from PyInstaller.utils.hooks import collect_submodules

ONEFILE = os.environ.get("FILEUPLOADER_ONEFILE") == "1"
IS_WINDOWS = sys.platform == "win32"

datas = [("web", "web")]

# pywebview picks its backend at runtime, so static analysis never sees the one
# that actually gets imported, and the backend has to be named here.
#
# Only Linux names one. The Windows build draws its window with the Pake shell
# in pake.json instead: pywebview's winforms backend reaches WebView2 through
# pythonnet, and that is what opened a window and then never painted the page
# into it. Leaving the whole stack out keeps a broken path from being taken and
# drops the .NET interop assemblies from the bundle.
hiddenimports = collect_submodules("uvicorn")
webview_excludes = ["webview", "clr", "clr_loader", "pythonnet"]

if not IS_WINDOWS:
    hiddenimports.append("webview.platforms.gtk")
    webview_excludes = []

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
        *webview_excludes,
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


if not IS_WINDOWS:
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
