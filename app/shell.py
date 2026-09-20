"""Handing a URL or a folder to whatever the desktop uses to open it.

The pywebview build reached these through a JavaScript bridge. The Pake window
has no such bridge -- it is a separate process drawing a page over HTTP -- so
the page asks the server instead, and both entry points share the code here.
"""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"


def open_url(url: str) -> None:
    """Open a link in the real browser rather than inside the app window."""
    if not url.startswith(("http://", "https://")):
        raise ValueError("Not a URL.")
    webbrowser.open(url)


def reveal(folder: Path) -> None:
    """Show a directory in the system file manager."""
    folder.mkdir(parents=True, exist_ok=True)
    if IS_WINDOWS:
        # Hands the folder to Explorer without spawning a shell.
        os.startfile(folder)  # noqa: S606 - a directory this app owns
    else:
        subprocess.Popen(["xdg-open", str(folder)])
