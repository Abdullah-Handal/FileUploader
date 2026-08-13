"""The temporary file hosts, and the durations they map to.

A host is chosen by how long the link should live, because that is the only
thing the person sharing actually cares about. Each entry below was verified by
uploading a file and downloading it again byte-for-byte.

Litterbox is deliberately absent. It is the obvious choice on paper -- selectable
1h/12h/24h/72h windows and 1 GB -- but its upload endpoint answers HTTP 412
"No file!" to a correctly formed request, including the exact curl command in
its own documentation, and including with a session cookie. catbox.moe, its
sibling service, accepts the identical request shape, so this is Litterbox
refusing rather than anything wrong here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor

TIMEOUT = (10, 1800)  # (connect, read) -- a multi-gigabyte body needs room

MB = 1024 ** 2
GB = 1024 ** 3


class UploadError(Exception):
    """The host would not take the file."""


def _post(url, fields, on_progress):
    """POST a streamed multipart body, reporting progress as it goes out."""
    # MultipartEncoder streams the body instead of building it in memory --
    # requests' own files= would read an entire 4 GB file in before sending.
    encoder = MultipartEncoder(fields=fields)
    monitor = MultipartEncoderMonitor(
        encoder,
        (lambda mon: on_progress(mon.bytes_read, mon.len)) if on_progress else None,
    )
    try:
        return requests.post(
            url,
            data=monitor,
            headers={"Content-Type": monitor.content_type},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise UploadError(f"Could not reach the host: {exc}") from exc


def _upload_uguu(path: Path, on_progress) -> str:
    """uguu.se -- returns a direct link that serves the raw file, no landing page."""
    with path.open("rb") as handle:
        response = _post(
            "https://uguu.se/upload",
            {"files[]": (path.name, handle, "application/octet-stream")},
            on_progress,
        )
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        raise UploadError(f"uguu.se sent an unreadable reply (HTTP {response.status_code}).")

    files = payload.get("files") or []
    if payload.get("success") and files and files[0].get("url"):
        return files[0]["url"]
    raise UploadError(str(payload.get("description") or payload.get("error") or payload)[:200])


def _upload_tempsh(path: Path, on_progress) -> str:
    """temp.sh -- the link opens a page with a download button. 4 GB, three days."""
    with path.open("rb") as handle:
        response = _post(
            "https://temp.sh/upload",
            {"file": (path.name, handle, "application/octet-stream")},
            on_progress,
        )
    body = response.text.strip()
    # temp.sh answers in plain text and reports failures the same way, so the
    # status code proves nothing -- the body has to look like a URL.
    if not body.startswith("https://"):
        detail = body[:200] if body else f"empty response (HTTP {response.status_code})"
        raise UploadError(f"temp.sh refused the upload: {detail}")
    return body


@dataclass(frozen=True)
class Host:
    id: str
    label: str          # what the fuse shows
    hours: int          # how long the link lives
    max_bytes: int
    origin: str         # who is actually storing it, shown in the UI
    direct: bool        # True when the link serves the file itself
    send: object

    @property
    def max_label(self) -> str:
        return f"{self.max_bytes // MB} MB" if self.max_bytes < GB else f"{self.max_bytes // GB} GB"


HOSTS = {
    "3h": Host(
        id="3h",
        label="3 hours",
        hours=3,
        max_bytes=128 * MB,
        origin="uguu.se",
        direct=True,
        send=_upload_uguu,
    ),
    "3d": Host(
        id="3d",
        label="3 days",
        hours=72,
        max_bytes=4 * GB,
        origin="temp.sh",
        direct=False,
        send=_upload_tempsh,
    ),
}

ORDER = ["3h", "3d"]
DEFAULT = "3d"
MAX_BYTES = max(host.max_bytes for host in HOSTS.values())


def get(host_id: str) -> Host:
    try:
        return HOSTS[host_id]
    except KeyError:
        raise UploadError(f"Unknown lifetime {host_id!r}.")


def send(path, host_id, on_progress=None) -> str:
    """Upload a file to the host backing host_id. Returns the shareable URL."""
    host = get(host_id)
    path = Path(path)
    size = path.stat().st_size
    if size == 0:
        raise UploadError("That file is empty.")
    if size > host.max_bytes:
        raise UploadError(
            f"That file is too big for a {host.label} link "
            f"({host.origin} accepts {host.max_label})."
        )
    return host.send(path, on_progress)
