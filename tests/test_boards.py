def test_default_boards(alice):
    names = [b["name"] for b in alice.get("/api/boards").json()]
    assert names == ["Books", "Films", "TV", "Games", "Music"]


def test_crud_and_reorder(alice):
    r = alice.post("/api/boards", json={"name": "Board games", "kind": "custom", "custom_hint": "tabletop board games"})
    assert r.status_code == 201
    bid = r.json()["board_id"]
    assert alice.post("/api/boards", json={"name": "X", "kind": "custom"}).status_code == 400
    assert alice.patch(f"/api/boards/{bid}", json={"name": "Tabletop"}).json()["name"] == "Tabletop"
    ids = [b["board_id"] for b in alice.get("/api/boards").json()]
    assert alice.post("/api/boards/reorder", json={"board_ids": ids[::-1]}).status_code == 200
    assert [b["board_id"] for b in alice.get("/api/boards").json()] == ids[::-1]
    assert alice.post("/api/boards/reorder", json={"board_ids": ids[:2]}).status_code == 400
    assert alice.delete(f"/api/boards/{bid}").status_code == 200
    assert alice.get(f"/api/boards/{bid}").status_code == 404


def test_cross_user_boards_404(two_clients):
    a, b = two_clients
    a_ids = [x["board_id"] for x in a.get("/api/boards").json()]
    b_ids = [x["board_id"] for x in b.get("/api/boards").json()]
    assert not set(a_ids) & set(b_ids)
    bid = a_ids[0]
    assert b.get(f"/api/boards/{bid}").status_code == 404
    assert b.patch(f"/api/boards/{bid}", json={"name": "pwned"}).status_code == 404
    assert b.delete(f"/api/boards/{bid}").status_code == 404
    assert b.post("/api/boards/reorder", json={"board_ids": a_ids}).status_code == 400
    assert a.get(f"/api/boards/{bid}").json()["name"] == "Books"
