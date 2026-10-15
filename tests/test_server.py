def test_own_page_is_served(client):
    assert client.get("/api/config").status_code == 200
    assert client.get("/api/config", headers={"Origin": "http://127.0.0.1:8765"}).status_code == 200


def test_localhost_name_is_accepted(client):
    assert client.get("/api/config", headers={"Host": "localhost:8765"}).status_code == 200


def test_rebound_dns_name_is_refused(client):
    # A site rebinding evil.example to 127.0.0.1 still sends its own Host.
    response = client.post("/api/share", json={"path": "/no/such/file"}, headers={"Host": "evil.example:8765"})
    assert response.status_code == 403


def test_foreign_page_is_refused(client):
    for origin in ("https://evil.example", "http://127.0.0.1:9999", "null"):
        response = client.post("/api/reveal", headers={"Origin": origin})
        assert response.status_code == 403, origin
