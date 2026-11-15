import json

from trellis import jobs

from conftest import login


def test_non_admin_forbidden(alice):
    for path in ("/api/admin/users", "/api/admin/themes", "/api/admin/usage"):
        assert alice.get(path).status_code == 403
    assert alice.post("/api/admin/users", json={"username": "x", "password": "password123"}).status_code == 403
    assert alice.post("/api/admin/themes/merge", json={"from_id": 1, "into_id": 2}).status_code == 403


def test_admin_users(client, make_user):
    make_user("root", admin=True)
    login(client, "root")
    assert client.post("/api/admin/users", json={"username": "carol", "password": "short"}).status_code == 422
    r = client.post("/api/admin/users", json={"username": "carol", "password": "password123"})
    assert r.status_code == 201
    uid = r.json()["user_id"]
    assert client.post("/api/admin/users", json={"username": "Carol", "password": "password123"}).status_code == 409
    client.patch(f"/api/admin/users/{uid}", json={"disabled": True})
    me = client.get("/api/me").json()
    assert client.patch(f"/api/admin/users/{me['user_id']}", json={"disabled": True}).status_code == 400
    client.post("/api/logout")
    assert client.post("/api/login", json={"username": "carol", "password": "password123"}).status_code == 401


def test_disabled_user_session_dies(two_clients, conn):
    a, b = two_clients
    conn.execute("UPDATE app_user SET disabled = 1 WHERE username = 'bob'")
    assert b.get("/api/me").status_code == 401


def test_theme_rename_merge_and_suggest(client, make_user, conn, settings, fake_llm):
    make_user("root", admin=True)
    login(client, "root")
    ts = {t["slug"]: t for t in client.get("/api/admin/themes").json()}
    assert client.patch(f"/api/admin/themes/{ts['cozy']['trait_id']}", json={"name": "Epic"}).status_code == 409
    assert client.patch(f"/api/admin/themes/{ts['cozy']['trait_id']}", json={"name": "Comfy"}).status_code == 200
    fake_llm.queue.append(json.dumps({"pairs": [{"merge": "comfy", "into": "hopeful", "why": "close"},
                                                {"merge": "nope", "into": "hopeful"}]}))
    jid = client.post("/api/admin/themes/suggest-merges").json()["job_id"]
    jobs.run_pending(conn, settings)
    pairs = client.get(f"/api/admin/jobs/{jid}").json()["result"]["pairs"]
    assert [(p["from"], p["into"]) for p in pairs] == [("comfy", "hopeful")]
    assert client.post("/api/admin/themes/merge", json={"from_id": pairs[0]["from_id"],
                                                        "into_id": pairs[0]["into_id"]}).status_code == 200
    assert "comfy" not in {t["slug"] for t in client.get("/api/admin/themes").json()}
    assert client.get("/api/admin/usage").json()["calls_today"] == 1


def test_export_own_data_only(two_clients):
    a, b = two_clients
    bid = a.get("/api/boards").json()[0]["board_id"]
    a.post("/api/entries", json={"board_id": bid, "source": "openlibrary", "source_id": "OL893414W", "rating": 5})
    ea = a.get("/api/export").json()
    assert ea["username"] == "alice" and [e["title"] for e in ea["entries"]] == ["Dune"]
    assert b.get("/api/export").json()["entries"] == []
