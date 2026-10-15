import json
import threading

from app import hosts, paths, uploader
from app.uploader import Registry
from tests.test_upload import wait_done


def test_reset_leaves_a_running_share_alone():
    registry = Registry()
    registry._set(state="uploading", name="big.iso")
    registry.reset()
    assert registry.snapshot()["state"] == "uploading"
    registry._set(state="done")
    registry.reset()
    assert registry.snapshot()["state"] == "idle"


def test_only_one_of_two_simultaneous_starts_wins(tmp_path, monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(hosts, "send", lambda *a, **k: release.wait(5) and "https://host.example/f")
    source = tmp_path / "f"
    source.write_bytes(b"data")
    registry = Registry()
    outcomes = []

    def go():
        try:
            registry.start(source, lifetime="3h")
            outcomes.append("started")
        except uploader.UploadError:
            outcomes.append("refused")

    threads = [threading.Thread(target=go) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    release.set()
    assert sorted(outcomes) == ["refused"] * 7 + ["started"]


def test_retry_alias_is_refused_while_a_link_is_being_made():
    registry = Registry()
    registry._set(state="shortening", direct="https://host.example/f")
    try:
        registry.retry_alias("another")
    except uploader.UploadError:
        pass
    else:
        raise AssertionError("a second shortening was started")


def test_history_survives_a_damaged_file():
    paths.data_dir().mkdir(parents=True)
    paths.history_file().write_text(
        json.dumps(["junk", {"link": "https://a.example", "created": "soon"}, {"name": "no link"}]),
        encoding="utf-8",
    )
    entries = uploader.history()
    assert [entry["link"] for entry in entries] == ["https://a.example"]


def test_finished_share_lands_in_history(tmp_path):
    source = tmp_path / "notes.txt"
    source.write_text("hello")
    uploader.registry.start(source, lifetime="3h")
    wait_done()
    [entry] = uploader.history()
    assert entry["name"] == "notes.txt" and entry["link"] == "https://short.example/x"
    assert source.exists(), "a file picked natively must never be deleted"
