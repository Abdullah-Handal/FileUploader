"""Desktop entry point: a native window over the local upload server.

The server and the upload machinery are the ones the browser build already
uses. This module only arranges them into something that opens like an
application: pick a free port, serve on loopback, and point an OS webview at it.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

# A windowed build has no console attached, so Python leaves these as None.
# Anything that writes to them -- a stray print, a library's warning -- then
# fails at an unpredictable moment, so they are pointed at a sink up front.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")  # noqa: SIM115 - lives for the process
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")  # noqa: SIM115

from app import paths, shell  # noqa: E402
from server.main import app as fastapi_app  # noqa: E402

log = logging.getLogger("fileuploader")

IS_WINDOWS = sys.platform == "win32"

# Spawning a helper from a windowed build pops a console window for as long as
# the helper lives. On Windows that is a black rectangle flashing over the app;
# this flag suppresses it, and is meaningless elsewhere.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0

WINDOW_TITLE = "FileUploader"
WINDOW_SIZE = (720, 760)
MIN_SIZE = (520, 560)

# The Windows window is a separate binary: a Pake (Tauri) shell that draws the
# page with WebView2 through Rust rather than through pywebview's pythonnet
# bridge, which opened a window and then never painted anything into it.
#
# A Tauri shell is built against one URL and cannot be told another at launch,
# so the port it expects is fixed here and in pake.json. They must agree.
SHELL_PORT = 8765
SHELL_EXE = "FileUploaderWindow.exe" if IS_WINDOWS else "FileUploaderWindow"

# WebView2's Evergreen runtime registers itself under this GUID. Windows 11
# ships it and Windows 10 was given it years ago, but it can be absent, and a
# shell started without it repeats the blank window it was meant to replace.
_WEBVIEW2_KEY = (
    r"SOFTWARE\Microsoft\EdgeUpdate\Clients"
    r"\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
)


def _reserve_port(preferred: int = 0) -> tuple[socket.socket, int]:
    """Bind a port and keep the socket. 0 lets the OS assign a free one.

    The socket is handed to uvicorn rather than closed and reopened, so nothing
    can take the port in between. A fixed port would collide with whatever else
    is running, including a second copy of this app.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", preferred))
    sock.listen(128)
    return sock, sock.getsockname()[1]


class _Server:
    """uvicorn on a background thread, with a shutdown that actually returns."""

    def __init__(self, sock: socket.socket) -> None:
        import uvicorn

        self._sock = sock
        self._config = uvicorn.Config(
            fastapi_app,
            log_level="warning",
            access_log=False,
            lifespan="off",
            # uvicorn's default logging config declares handlers writing to
            # ext://sys.stderr. In a windowed build that is None, and
            # dictConfig dies before the server ever starts. Nothing here needs
            # uvicorn's log formatting, so the config is skipped.
            log_config=None,
            # Stated rather than auto-detected: uvloop and httptools are
            # optional C accelerators that a loopback server serving one user
            # gains nothing from. Naming the pure-Python pair here means
            # excluding them from the bundle cannot alter behaviour.
            loop="asyncio",
            http="h11",
        )
        self._server = uvicorn.Server(self._config)
        self._thread = threading.Thread(target=self._run, name="server", daemon=True)

    def _run(self) -> None:
        self._server.run(sockets=[self._sock])

    def start(self, timeout: float = 20.0) -> bool:
        self._thread.start()
        waiter = threading.Event()
        waited = 0.0
        while waited < timeout:
            if self._server.started:
                return True
            waiter.wait(0.05)
            waited += 0.05
        return False

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=10)


class Api:
    """Methods the page can call as ``window.pywebview.api.*``."""

    def __init__(self) -> None:
        self.window = None

    def pick_file(self) -> dict:
        """Open the OS file picker and report what was chosen.

        A native dialog rather than an HTML file input: the server is on this
        machine, so it only needs the path. That avoids pushing a gigabyte
        through the page and back out again just to reach a local process.
        """
        import webview

        if self.window is None:
            return {"ok": False, "error": "No window."}

        picked = self.window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False)
        if not picked:
            return {"ok": False, "cancelled": True}

        target = picked[0] if isinstance(picked, (list, tuple)) else picked
        try:
            size = os.path.getsize(target)
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "path": str(target), "name": os.path.basename(target), "size": size}

    def copy(self, text: str) -> dict:
        """Put text on the clipboard.

        The page tries navigator.clipboard first; this is the fallback for
        webview backends where that is unavailable.
        """
        if IS_WINDOWS:
            commands = [["clip"]]
            missing = "clip.exe is missing from PATH."
        else:
            commands = [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "-ib"]]
            missing = "No clipboard tool found (install wl-clipboard or xclip)."

        # UTF-8 rather than the console codepage: what gets copied is a short
        # ASCII link, for which the two are identical, and guessing the codepage
        # wrongly would corrupt the one thing this method exists to hand over.
        payload = text.encode("utf-8", "replace")
        for command in commands:
            try:
                subprocess.run(
                    command, input=payload, check=True, timeout=5, creationflags=_NO_WINDOW
                )
                return {"ok": True}
            except (OSError, subprocess.SubprocessError):
                continue
        return {"ok": False, "error": missing}

    def reveal_texts(self) -> dict:
        """Open the saved-text folder in the system file manager."""
        try:
            shell.reveal(paths.texts_dir())
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True}

    def open_external(self, url: str) -> dict:
        """Open a link in the real browser instead of inside the app window."""
        try:
            shell.open_url(url)
        except (ValueError, OSError) as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True}


def _open_window(url: str, api: Api) -> bool:
    """Show the app in a native window. False if no webview is available."""
    try:
        import webview
    except ImportError:
        log.warning("pywebview is not installed")
        return False

    try:
        window = webview.create_window(
            WINDOW_TITLE,
            url,
            width=WINDOW_SIZE[0],
            height=WINDOW_SIZE[1],
            min_size=MIN_SIZE,
            js_api=api,
        )
        api.window = window
        webview.start()
        return True
    except Exception as exc:  # noqa: BLE001 - any backend failure falls back
        log.warning("native window unavailable: %s", exc)
        return False


def _app_dir() -> Path:
    """The directory the app was started from, bundled or from source."""
    if paths.is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _find_shell() -> Path | None:
    """The Pake window binary shipped beside this one, if it was shipped."""
    root = _app_dir()
    for candidate in (root / "window" / SHELL_EXE, root / SHELL_EXE):
        if candidate.is_file():
            return candidate
    return None


def _webview2_present() -> bool:
    """Whether the runtime the Pake shell renders with is installed."""
    if not IS_WINDOWS:
        return True
    import winreg

    # Per-machine installs land in the 32-bit view of HKLM; per-user ones in
    # HKCU. A version string that is empty or all zeroes means the key was left
    # behind by an uninstall rather than an install.
    views = (
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_READ | winreg.KEY_WOW64_32KEY),
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_READ),
        (winreg.HKEY_CURRENT_USER, winreg.KEY_READ),
    )
    for root, access in views:
        try:
            with winreg.OpenKey(root, _WEBVIEW2_KEY, 0, access) as handle:
                version = winreg.QueryValueEx(handle, "pv")[0]
        except OSError:
            continue
        if version and version != "0.0.0.0":
            return True
    return False


def _ours(port: int) -> bool:
    """Whether the thing already holding ``port`` is another copy of this app."""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/config", timeout=2
        ) as response:
            return "lifetimes" in json.load(response)
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _open_shell(shell: Path) -> bool:
    """Run the Pake window and block until the person closes it.

    The shell knows its own URL -- it was compiled with it -- so there is
    nothing to pass. False means it would not start at all.
    """
    try:
        process = subprocess.Popen(
            [str(shell)], cwd=str(shell.parent), creationflags=_NO_WINDOW
        )
    except OSError as exc:
        log.warning("the window would not start: %s", exc)
        return False

    started = time.monotonic()
    try:
        code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        return True

    # Closing a window takes a person at least a moment. An exit this fast with
    # something to complain about is the window failing to come up, not being
    # dismissed, and the browser should still get its turn.
    if code != 0 and time.monotonic() - started < 3.0:
        log.warning("the window exited immediately (status %s)", code)
        return False
    return True


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="fileuploader",
        description="Pick a file, get a short link that expires.",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="run the server without opening a window (used by the smoke test)",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="open in the default browser instead of a native window",
    )
    parser.add_argument(
        "--port", type=int, default=0, help="port to listen on; 0 lets the OS choose"
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    if not paths.web_dir().is_dir():
        print(f"The interface is missing: {paths.web_dir()}", file=sys.stderr)
        return 1

    paths.data_dir().mkdir(parents=True, exist_ok=True)

    headless = args.serve or args.browser
    shell = None if headless else _find_shell()
    if shell and not _webview2_present():
        # Starting it anyway would reproduce the empty window this replaced.
        print(
            "The WebView2 runtime is missing, so the app window cannot draw.\n"
            "Install it from https://go.microsoft.com/fwlink/p/?LinkId=2124703 "
            "-- opening in your browser for now."
        )
        shell = None

    # A Tauri shell only ever loads the URL it was built with, so when one is
    # going to be used the server has to be on that exact port.
    wanted = args.port or (SHELL_PORT if shell else 0)
    try:
        sock, port = _reserve_port(wanted)
    except OSError as exc:
        if shell and not args.port and _ours(SHELL_PORT):
            # Already running. Put a second window on the copy that is serving
            # rather than starting a competing one.
            print(f"FileUploader is already running on http://127.0.0.1:{SHELL_PORT}")
            _open_shell(shell)
            return 0
        if args.port:
            print(f"Port {args.port} is not free: {exc}", file=sys.stderr)
            return 1
        # Something unrelated holds the port. The window cannot follow us
        # anywhere else, so the browser takes over.
        shell = None
        sock, port = _reserve_port(0)

    url = f"http://127.0.0.1:{port}"
    server = _Server(sock)

    if not server.start():
        print("The server did not start.", file=sys.stderr)
        return 1

    # Announced on stdout so a caller never has to scrape ss/netstat for it.
    print(f"FileUploader listening on {url}", flush=True)

    if args.serve:
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            server.stop()
        return 0

    try:
        if shell and _open_shell(shell):
            return 0

        # No Pake shell here. Linux still has a working GTK webview; on Windows
        # pywebview is the thing being replaced, so it is not tried at all.
        if args.browser or IS_WINDOWS or not _open_window(url, Api()):
            if not args.browser:
                print(f"Opening {url} in your browser (no native window available).")
            webbrowser.open(url)
            try:
                threading.Event().wait()
            except KeyboardInterrupt:
                pass
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
