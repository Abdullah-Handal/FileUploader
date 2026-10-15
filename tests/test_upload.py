import dataclasses
import time

from app import hosts
from app.uploader import registry


def wait_done(timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = registry.snapshot()
        if job["state"] in ("done", "error"):
            return job
        time.sleep(0.02)
    raise AssertionError("the share never finished")


def test_raw_body_round_trips_and_temp_folder_is_removed(client, offline, tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    body = bytes(range(256)) * 4096  # 1 MiB, every byte value
    response = client.post(
        "/api/share-upload", params={"name": "../../evil<>.bin", "lifetime": "3h"}, content=body
    )
    assert response.status_code == 200, response.text
    job = wait_done()
    assert job["state"] == "done" and job["direct"] == "https://host.example/evil.bin"
    assert offline == [("evil.bin", body, "3h")]
    assert not list(tmp_path.glob("fileuploader-*")), "the temporary copy was left behind"


def test_oversized_body_is_refused_and_cleaned_up(client, offline, tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    monkeypatch.setitem(hosts.HOSTS, "3h", dataclasses.replace(hosts.HOSTS["3h"], max_bytes=1000))

    declared = client.post("/api/share-upload", params={"name": "a", "lifetime": "3h"}, content=b"x" * 1001)
    assert declared.status_code == 413

    # A sender that does not declare a length is cut off once it passes the limit.
    streamed = client.post(
        "/api/share-upload",
        params={"name": "a", "lifetime": "3h"},
        content=(b"x" * 100 for _ in range(20)),
    )
    assert streamed.status_code == 413
    assert offline == []
    assert not list(tmp_path.glob("fileuploader-*"))


def test_second_upload_waits_for_the_first(client, monkeypatch):
    monkeypatch.setattr(registry, "busy", lambda: True)
    response = client.post("/api/share-upload", params={"name": "a"}, content=b"data")
    assert response.status_code == 409


def test_bad_lifetime_is_rejected_before_reading(client):
    response = client.post("/api/share-upload", params={"lifetime": "9y"}, content=b"data")
    assert response.status_code == 400
