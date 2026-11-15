def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_spa_fallback(client, settings):
    settings.web_dir.mkdir()
    (settings.web_dir / "index.html").write_text("<h1>hi</h1>")
    assert client.get("/board/3").text == "<h1>hi</h1>"
    assert client.get("/api/nope").status_code == 404
    assert client.get("/../../etc/passwd").text == "<h1>hi</h1>"

