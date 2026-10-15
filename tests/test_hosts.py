import dataclasses

import pytest

from app import hosts, shortener

real_send = hosts.send  # captured at import, before the offline fixture swaps it


class Reply:
    def __init__(self, payload):
        self.payload = payload
        self.status_code = 200
        self.text = str(payload)

    def json(self):
        return self.payload


def test_a_host_answering_with_a_script_url_is_refused(tmp_path, monkeypatch):
    sample = tmp_path / "a.txt"
    sample.write_text("hi")
    reply = Reply({"success": True, "files": [{"url": "javascript:alert(1)"}]})
    monkeypatch.setattr(hosts, "_post", lambda *a: reply)
    monkeypatch.setitem(hosts.HOSTS, "3h", dataclasses.replace(hosts.HOSTS["3h"], send=hosts._upload_uguu))
    with pytest.raises(hosts.UploadError):
        real_send(sample, "3h")

    reply.payload["files"][0]["url"] = "https://o.uguu.se/a.txt"
    assert real_send(sample, "3h") == "https://o.uguu.se/a.txt"


def test_is_gd_answer_must_be_a_link(monkeypatch):
    monkeypatch.setattr(shortener.requests, "get", lambda *a, **k: Reply({"shorturl": "javascript:x"}))
    with pytest.raises(shortener.ShortenError):
        shortener._is_gd("https://host.example/f", "")


def test_empty_file_is_refused(tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.write_bytes(b"")
    with pytest.raises(hosts.UploadError, match="empty"):
        real_send(empty, "3h")


class Page:
    status_code = 403
    text = "<!DOCTYPE html><html><head><title>Just a moment...</title>"

    def json(self):
        raise ValueError


def test_a_bot_check_page_is_reported_briefly(monkeypatch):
    monkeypatch.setattr(shortener.requests, "get", lambda *a, **k: Page())
    for provider in (shortener._ulvis, shortener._is_gd):
        with pytest.raises(shortener.ShortenError, match=r"^no usable answer \(HTTP 403\)$"):
            provider("https://host.example/f", "")
