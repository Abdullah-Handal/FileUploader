"""The one share the window is watching, and the record of finished ones.

The uploading itself lives in ``app.hosts``; this module runs it on a background
thread and keeps the state the page polls for.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from app import hosts, paths, shortener
from app.hosts import UploadError

HISTORY_LIMIT = 30


def human_size(num_bytes) -> str:
    if not num_bytes:
        return "0 B"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


@dataclass
class Job:
    """The share currently in flight, as the window needs to see it."""

    state: str = "idle"  # idle | uploading | shortening | done | error
    name: str = ""
    sent: int = 0
    total: int = 0
    link: str = ""
    direct: str = ""
    lifetime: str = hosts.DEFAULT
    error: str = ""
    alias_rejected: bool = False
    revision: int = 0

    def as_dict(self) -> dict:
        host = hosts.HOSTS.get(self.lifetime)
        percent = round(self.sent / self.total * 100, 1) if self.total else 0.0
        return {
            "state": self.state,
            "name": self.name,
            "sent": self.sent,
            "total": self.total,
            "percent": percent,
            "sent_text": human_size(self.sent),
            "total_text": human_size(self.total),
            "link": self.link,
            "direct": self.direct,
            "lifetime": self.lifetime,
            "lifetime_label": host.label if host else self.lifetime,
            "hours": host.hours if host else 72,
            "origin": host.origin if host else "",
            "error": self.error,
            "alias_rejected": self.alias_rejected,
            "revision": self.revision,
        }


class Registry:
    """Holds the active job, safely across threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._job = Job()

    def snapshot(self) -> dict:
        with self._lock:
            return self._job.as_dict()

    def busy(self) -> bool:
        with self._lock:
            return self._job.state in ("uploading", "shortening")

    def _set(self, **fields) -> None:
        with self._lock:
            for key, value in fields.items():
                setattr(self._job, key, value)
            self._job.revision += 1

    def reset(self) -> None:
        with self._lock:
            self._job = Job()

    def start(self, file_path, alias="", lifetime=hosts.DEFAULT, cleanup=False) -> None:
        """Begin a share in the background. Raises if one is already running.

        ``cleanup`` deletes the source afterwards, for the temporary copy a
        browser-mode upload has to make. Files picked natively, and saved text
        snippets, are left alone.
        """
        if self.busy():
            raise UploadError("An upload is already running.")

        host = hosts.get(lifetime)
        path = Path(file_path)
        if not path.is_file():
            raise UploadError(f"No such file: {path}")

        size = path.stat().st_size
        if size > host.max_bytes:
            raise UploadError(
                f"That file is {human_size(size)} — too big for a {host.label} link "
                f"({host.origin} accepts {host.max_label})."
            )

        with self._lock:
            self._job = Job(
                state="uploading", name=path.name, total=size, lifetime=lifetime
            )

        threading.Thread(
            target=self._run,
            args=(path, alias, lifetime, cleanup),
            name="share",
            daemon=True,
        ).start()

    def retry_alias(self, alias) -> None:
        """Shorten the already-uploaded file at a different alias.

        Kept separate from start() so a rejected alias never costs a second
        upload of what might be several gigabytes.
        """
        with self._lock:
            direct = self._job.direct
            name = self._job.name
            lifetime = self._job.lifetime
        if not direct:
            raise UploadError("Nothing has been uploaded yet.")

        self._set(state="shortening", alias_rejected=False, error="")
        threading.Thread(
            target=self._shorten_step,
            args=(direct, alias, name, lifetime),
            name="shorten",
            daemon=True,
        ).start()

    def _run(self, path: Path, alias, lifetime, cleanup) -> None:
        def progress(sent, total):
            self._set(sent=sent, total=total)

        try:
            direct = hosts.send(path, lifetime, on_progress=progress)
        except Exception as exc:  # noqa: BLE001 - the host's reason is the useful part
            self._set(state="error", error=str(exc))
            return
        finally:
            if cleanup:
                try:
                    path.unlink()
                except OSError:
                    pass

        self._set(direct=direct, state="shortening")
        self._shorten_step(direct, alias, path.name, lifetime)

    def _shorten_step(self, direct, alias, name, lifetime) -> None:
        try:
            link = shortener.shorten(direct, alias)
        except shortener.AliasTakenError as exc:
            self._set(state="error", error=str(exc), alias_rejected=True)
            return
        except Exception as exc:  # noqa: BLE001
            # The file is up; a failed shortening must not lose the direct link.
            self._set(state="done", link=direct, error=f"Could not shorten: {exc}")
            remember(name, direct, direct, lifetime)
            return

        self._set(state="done", link=link, alias_rejected=False, error="")
        remember(name, link, direct, lifetime)


registry = Registry()


# --------------------------------------------------------------------------- history


def _read_history() -> list:
    try:
        data = json.loads(paths.history_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def remember(name, link, direct, lifetime) -> None:
    """Record a finished share so the link survives closing the window."""
    entries = _read_history()
    entries.insert(
        0,
        {
            "name": name,
            "link": link,
            "direct": direct,
            "lifetime": lifetime,
            "created": int(time.time()),
        },
    )
    del entries[HISTORY_LIMIT:]
    try:
        paths.data_dir().mkdir(parents=True, exist_ok=True)
        paths.history_file().write_text(json.dumps(entries, indent=2), encoding="utf-8")
    except OSError:
        pass  # history is a convenience; never fail a share over it


def history() -> list:
    """Recent shares, newest first, each marked expired or not."""
    now = int(time.time())
    entries = []
    for raw in _read_history():
        entry = dict(raw)
        host = hosts.HOSTS.get(entry.get("lifetime"))
        hours = host.hours if host else 72
        entry["expired"] = (now - int(entry.get("created", 0))) > hours * 3600
        entries.append(entry)
    return entries
