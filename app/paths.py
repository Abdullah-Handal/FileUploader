"""Where everything lives, in a source checkout and inside a frozen bundle.

PyInstaller unpacks the application into a temporary directory and rewrites
``__file__`` to point inside it, so the usual ``Path(__file__).parent.parent``
trick silently resolves somewhere useless once packaged. Every path question is
answered here instead, so exactly one module has to know that.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "fileuploader"


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle rather than the source tree."""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Read-only files shipped with the app.

    ``sys._MEIPASS`` is the directory PyInstaller unpacks into; it only exists
    in a frozen build.
    """
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled)
    return Path(__file__).resolve().parent.parent


def web_dir() -> Path:
    """The single-page UI served to the webview."""
    return resource_dir() / "web"


def data_dir() -> Path:
    """Writable per-user directory for history and generated text files.

    The bundle itself must be treated as read-only: a packaged build may sit
    anywhere, including a read-only mount.
    """
    root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return root / APP_NAME


def texts_dir() -> Path:
    """Where text snippets are written before upload, so they outlive the link."""
    return data_dir() / "texts"


def history_file() -> Path:
    return data_dir() / "history.json"
