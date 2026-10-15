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


def test_safe_filename():
    from server.main import safe_filename

    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("..\\..\\Windows\\win.ini") == "win.ini"
    assert safe_filename('a<b>:c"d|e?f*.txt') == "abcdef.txt"
    assert safe_filename("...") == ""
    assert safe_filename("con.txt") == "_con.txt"
    assert safe_filename("NUL") == "_NUL"
    assert safe_filename("console.txt") == "console.txt"
    # Cut to length first, so the cut cannot leave a trailing dot Windows drops.
    assert not safe_filename("a" * 119 + ".txt").endswith(".")
