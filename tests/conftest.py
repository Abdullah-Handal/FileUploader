import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """Keep history and saved text out of the real home directory."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    return tmp_path / "data" / "fileuploader"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No test may reach a real host. Uploads land in ``sent`` instead."""
    from app import hosts, shortener, uploader

    sent = []

    def fake_send(path, host_id, on_progress=None):
        sent.append((path.name, path.read_bytes(), host_id))
        return "https://host.example/" + path.name

    def no_network(*args, **kwargs):
        raise AssertionError("tests must not touch the network")

    monkeypatch.setattr(hosts, "send", fake_send)
    monkeypatch.setattr(shortener, "shorten", lambda url, alias="": "https://short.example/x")
    monkeypatch.setattr("requests.post", no_network)
    monkeypatch.setattr("requests.get", no_network)
    uploader.registry.reset()
    return sent


@pytest.fixture
def client():
    from server.main import app

    # The Host the page itself sends; TestClient's default "testserver" is refused.
    return TestClient(app, base_url="http://127.0.0.1:8765")
