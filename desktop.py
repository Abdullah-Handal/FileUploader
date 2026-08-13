"""Desktop entry point: a native window over the local upload server.

The server and the upload machinery are the ones the browser build already
uses. This module only arranges them into something that opens like an
application: pick a free port, serve on loopback, and point an OS webview at it.
"""

from __future__ import annotations

import argparse
import logging
import os
import socket
import subprocess
import sys
import threading
import webbrowser

# A windowed build has no console attached, so Python leaves these as None.
# Anything that writes to them -- a stray print, a library's warning -- then
# fails at an unpredictable moment, so they are pointed at a sink up front.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")  # noqa: SIM115 - lives for the process
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")  # noqa: SIM115

from app import paths  # noqa: E402
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
        folder = paths.texts_dir()
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if IS_WINDOWS:
                # Hands the folder to Explorer without spawning a shell.
                os.startfile(folder)  # noqa: S606 - a directory this app owns
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True}

    def open_external(self, url: str) -> dict:
        """Open a link in the real browser instead of inside the app window."""
        if not url.startswith(("http://", "https://")):
            return {"ok": False, "error": "Not a URL."}
        try:
            webbrowser.open(url)
        except Exception as exc:  # noqa: BLE001
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

    sock, port = _reserve_port(args.port)
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
        if args.browser or not _open_window(url, Api()):
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
