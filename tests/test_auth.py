from fastapi.testclient import TestClient

from conftest import login


def test_login_and_me(client, make_user):
    make_user("alice")
    assert client.get("/api/me").status_code == 401
    me = login(client, "Alice ")
    assert me["username"] == "alice"
    assert client.get("/api/me").json()["username"] == "alice"
    client.post("/api/logout")
    assert client.get("/api/me").status_code == 401


def test_wrong_password_and_throttle(client, make_user):
    make_user("alice")
    for _ in range(5):
        assert client.post("/api/login", json={"username": "alice", "password": "nope-nope"}).status_code == 401
    r = client.post("/api/login", json={"username": "alice", "password": "password123"})
    assert r.status_code == 429


def test_unknown_user(client):
    assert client.post("/api/login", json={"username": "ghost", "password": "password123"}).status_code == 401


def test_disabled_user_cannot_login(client, make_user, conn):
    uid = make_user("alice")
    conn.execute("UPDATE app_user SET disabled = 1 WHERE user_id = ?", (uid,))
    assert client.post("/api/login", json={"username": "alice", "password": "password123"}).status_code == 401


def test_post_needs_xhr_header(app, make_user):
    make_user("alice")
    with TestClient(app) as c:
        assert c.post("/api/login", json={"username": "alice", "password": "password123"}).status_code == 403


def test_change_password(alice):
    assert alice.post("/api/me/password", json={"current": "wrong", "new": "newpassword1"}).status_code == 400
    assert alice.post("/api/me/password", json={"current": "password123", "new": "short"}).status_code == 400
    assert alice.post("/api/me/password", json={"current": "password123", "new": "newpassword1"}).status_code == 200
    alice.post("/api/logout")
    assert alice.post("/api/login", json={"username": "alice", "password": "newpassword1"}).status_code == 200
