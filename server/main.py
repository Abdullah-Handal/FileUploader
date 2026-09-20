"""HTTP API for the window.

The window is a webview pointed at this server on loopback, so these routes are
the only thing standing between the page and the upload machinery in ``app``.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import hosts, paths, shell, shortener, uploader
from app.uploader import registry

app = FastAPI(title="FileUploader", docs_url=None, redoc_url=None)


class ShareRequest(BaseModel):
    path: str = Field(min_length=1)
    alias: str = ""
    lifetime: str = hosts.DEFAULT


class TextRequest(BaseModel):
    text: str = Field(min_length=1)
    filename: str = ""
    alias: str = ""
    lifetime: str = hosts.DEFAULT


class AliasRequest(BaseModel):
    alias: str = ""


class OpenRequest(BaseModel):
    url: str = Field(min_length=1)


def safe_filename(raw: str) -> str:
    """Reduce user input to a bare filename that cannot escape its directory."""
    name = Path((raw or "").strip().replace("\\", "/")).name
    name = re.sub(r'[\x00-\x1f<>:"|?*]', "", name).strip(". ")
    return name[:120]


def _check(alias: str, lifetime: str) -> None:
    if lifetime not in hosts.HOSTS:
        raise HTTPException(400, f"Lifetime must be one of {', '.join(hosts.ORDER)}.")
    complaint = shortener.check_alias(alias.strip())
    if complaint:
        raise HTTPException(400, complaint)


@app.post("/api/share")
async def share(request: ShareRequest) -> dict:
    """Share a file already on this machine, by path, without copying it."""
    _check(request.alias, request.lifetime)
    try:
        registry.start(request.path, request.alias.strip(), request.lifetime)
    except hosts.UploadError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


@app.post("/api/share-text")
async def share_text(request: TextRequest) -> dict:
    """Turn pasted text into a .txt file, keep it, and share it."""
    _check(request.alias, request.lifetime)

    name = safe_filename(request.filename) or "note"
    if not name.lower().endswith(".txt"):
        name += ".txt"

    folder = paths.texts_dir()
    folder.mkdir(parents=True, exist_ok=True)

    # Don't overwrite an earlier snippet that happens to share a name.
    stem = name[: -len(".txt")]
    destination = folder / name
    counter = 1
    while destination.exists():
        destination = folder / f"{stem}({counter}).txt"
        counter += 1

    destination.write_text(request.text, encoding="utf-8")

    try:
        registry.start(destination, request.alias.strip(), request.lifetime)
    except hosts.UploadError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "saved_to": str(destination)}


@app.post("/api/share-upload")
async def share_upload(
    file: UploadFile = File(...),
    alias: str = Form(""),
    lifetime: str = Form(hosts.DEFAULT),
) -> dict:
    """Share a file sent through the browser.

    Used when a file was dropped onto the window, or when there is no native
    picker to get a path from. Picking natively takes /api/share and copies
    nothing.
    """
    _check(alias, lifetime)

    name = safe_filename(file.filename or "") or "upload.bin"
    temp_dir = Path(tempfile.mkdtemp(prefix="fileuploader-"))
    destination = temp_dir / name
    with destination.open("wb") as out:
        shutil.copyfileobj(file.file, out, length=1024 * 1024)

    try:
        registry.start(destination, alias.strip(), lifetime, cleanup=True)
    except hosts.UploadError as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


@app.post("/api/retry-alias")
async def retry_alias(request: AliasRequest) -> dict:
    """Re-shorten the file that is already uploaded, at a different alias."""
    complaint = shortener.check_alias(request.alias.strip())
    if complaint:
        raise HTTPException(400, complaint)
    try:
        registry.retry_alias(request.alias.strip())
    except hosts.UploadError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


@app.get("/api/status")
async def status() -> dict:
    return registry.snapshot()


@app.post("/api/reset")
async def reset() -> dict:
    registry.reset()
    return {"ok": True}


@app.get("/api/history")
async def get_history() -> dict:
    return {"entries": uploader.history()}


@app.post("/api/open")
async def open_external(request: OpenRequest) -> dict:
    """Open a finished link outside the app window.

    The Pake window has no JavaScript bridge to the host, so the page routes
    external links back through here rather than through ``window.open``.
    """
    try:
        shell.open_url(request.url)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(500, f"Could not open the link: {exc}") from exc
    return {"ok": True}


@app.post("/api/reveal")
async def reveal_texts() -> dict:
    """Show the saved-text folder in the system file manager."""
    try:
        shell.reveal(paths.texts_dir())
    except OSError as exc:
        raise HTTPException(500, f"Could not open the folder: {exc}") from exc
    return {"ok": True}


@app.get("/api/config")
async def config() -> dict:
    return {
        "lifetimes": [
            {
                "id": host_id,
                "label": hosts.HOSTS[host_id].label,
                "max_bytes": hosts.HOSTS[host_id].max_bytes,
                "max_label": hosts.HOSTS[host_id].max_label,
                "origin": hosts.HOSTS[host_id].origin,
                "direct": hosts.HOSTS[host_id].direct,
            }
            for host_id in hosts.ORDER
        ],
        "default": hosts.DEFAULT,
        "alias_rule": shortener.ALIAS_RULE,
        "texts_dir": str(paths.texts_dir()),
    }


# Mounted last so the API routes above win.
if paths.web_dir().is_dir():
    app.mount("/", StaticFiles(directory=paths.web_dir(), html=True), name="web")
