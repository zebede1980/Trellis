import json


def board_id(c, kind):
    return next(b["board_id"] for b in c.get("/api/boards").json() if b["kind"] == kind)


def add_dune(c, **kw):
    body = {"board_id": board_id(c, "book"), "source": "openlibrary", "source_id": "OL893414W", "state": "done",
            "rating": 5, "note": "Spice!", **kw}
    return c.post("/api/entries", json=body)


def test_lookup_and_add(alice):
    bid = board_id(alice, "book")
    cands = alice.get("/api/lookup", params={"board_id": bid, "q": "dune"}).json()
    assert cands[0]["title"] == "Dune" and cands[0]["have"] is None
    r = add_dune(alice)
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["title"] == "Dune" and e["creators"] == ["Frank Herbert"] and e["rating"] == 5
    assert alice.get("/api/lookup", params={"board_id": bid, "q": "dune"}).json()[0]["have"]["entry_id"] == e["entry_id"]
    assert add_dune(alice).status_code == 409
    listed = alice.get(f"/api/boards/{bid}/entries").json()
    assert [x["entry_id"] for x in listed] == [e["entry_id"]]
    assert alice.get("/api/boards").json()[0]["n_done"] == 1


def test_want_clears_rating_and_patch(alice):
    e = add_dune(alice, state="want").json()
    assert e["rating"] is None
    p = alice.patch(f"/api/entries/{e['entry_id']}", json={"state": "done", "rating": 4, "note": "  good  "}).json()
    assert (p["state"], p["rating"], p["note"]) == ("done", 4, "good")
    assert alice.patch(f"/api/entries/{e['entry_id']}", json={"rating": 9}).status_code == 422
    film_board = board_id(alice, "film")
    assert alice.patch(f"/api/entries/{e['entry_id']}", json={"board_id": film_board}).status_code == 400


def test_wrong_source_for_board(alice):
    r = alice.post("/api/entries", json={"board_id": board_id(alice, "film"), "source": "openlibrary",
                                         "source_id": "OL893414W"})
    assert r.status_code == 502


def test_manual_on_custom_board(alice):
    bid = alice.post("/api/boards", json={"name": "Board games", "kind": "custom", "custom_hint": "board games"}).json()["board_id"]
    r = alice.post("/api/entries", json={"board_id": bid, "manual": {"title": "Wingspan", "creators": ["Elizabeth Hargrave"],
                                                                     "year": 2019, "url": "javascript:alert(1)"}})
    assert r.status_code == 201
    e = r.json()
    assert e["source"] == "manual" and e["verified"] is False and e["url"] is None


def test_saving_queues_tagging(alice, conn):
    add_dune(alice)
    jobs = conn.execute("SELECT kind, status FROM job").fetchall()
    assert [tuple(j) for j in jobs] == [("tag", "queued")]
    alice.post("/api/entries", json={"board_id": board_id(alice, "film"), "source": "tmdb", "source_id": "movie:438631"})
    assert conn.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 1, "one queued tag job covers both works"


def test_cross_user_entries_404(two_clients, settings):
    a, b = two_clients
    import dataclasses
    e = add_dune(a).json()
    eid = e["entry_id"]
    assert b.get(f"/api/entries/{eid}").status_code == 404
    assert b.patch(f"/api/entries/{eid}", json={"rating": 1}).status_code == 404
    assert b.delete(f"/api/entries/{eid}").status_code == 404
    assert b.get(f"/api/boards/{e['board_id']}/entries").status_code == 404
    assert b.get("/api/lookup", params={"board_id": e["board_id"], "q": "dune"}).status_code == 404
    assert b.post("/api/entries", json={"board_id": e["board_id"], "source": "openlibrary",
                                        "source_id": "OL893414W"}).status_code == 404
    # b moving their own entry onto a's board
    eb = add_dune(b).json()
    assert b.patch(f"/api/entries/{eb['entry_id']}", json={"board_id": e["board_id"]}).status_code == 404
    assert a.get(f"/api/entries/{eid}").json()["rating"] == 5
