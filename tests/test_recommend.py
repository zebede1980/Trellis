import json

from trellis import jobs, recommend
from trellis.db import now_utc

from test_tree import seed_tagged


def setup_user(alice, conn):
    uid = conn.execute("SELECT user_id FROM app_user WHERE username='alice'").fetchone()[0]
    ids = seed_tagged(conn, uid, [("Wolf Hall", 5, ["political-intrigue", "historical-setting"]),
                                  ("Shogun", 5, ["political-intrigue", "epic"]),
                                  ("Twilight", 1, ["love-and-romance"])])
    return uid, ids


def boards(alice):
    return {b["kind"]: b["board_id"] for b in alice.get("/api/boards").json()}


def rec_response(b, ids):
    return json.dumps({"suggestions": [
        {"title": "Dune", "creator": "Frank Herbert", "year": 1965, "board_id": b["book"],
         "because_traits": ["political-intrigue"], "because_entries": [ids[0], 99999],
         "reason": "Like Wolf Hall, it is all scheming houses.", "new_branch": None},
        {"title": "Dune", "creator": "Denis Villeneuve", "year": 2021, "board_id": b["film"],
         "because_traits": ["political-intrigue"], "because_entries": [ids[1]],
         "reason": "The Shogun of space operas.", "new_branch": None},
        {"title": "A Book That Does Not Exist", "creator": "Nobody", "year": 2019, "board_id": b["book"],
         "because_traits": [], "because_entries": [], "reason": "Made up, from Shogun.", "new_branch": None},
    ]})


def tag_all(model, messages):
    ws = json.loads(messages[1]["content"])["works"]
    traits = [{"slug": s, "weight": 0.8} for s in ("political-intrigue", "epic", "deep-space", "rich-worldbuilding",
                                                     "science-fiction")]
    return json.dumps({"works": [{"id": w["id"], "traits": traits} for w in ws]})


def test_needs_three_ratings(alice):
    assert alice.post("/api/recommend", json={"mode": "all"}).status_code == 400


def test_pipeline(alice, conn, settings, fake_llm):
    uid, ids = setup_user(alice, conn)
    b = boards(alice)
    r = alice.post("/api/recommend", json={"mode": "all"})
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    fake_llm.queue += [rec_response(b, ids), tag_all]
    jobs.run_pending(conn, settings)
    job = alice.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "done", job
    stats = job["result"]
    assert stats["returned"] == 3 and stats["matched"] == 2 and stats["kept"] == 2
    assert stats["unmatched"] == ["A Book That Does Not Exist (2019): unmatched"]
    sugg = alice.get("/api/suggestions").json()
    titles = {(s["title"], s["board_name"]) for s in sugg}
    assert titles == {("Dune", "Books"), ("Dune", "Films")}
    book = next(s for s in sugg if s["board_name"] == "Books")
    assert book["sources"] == [{"entry_id": ids[0], "title": "Wolf Hall"}], "unknown entry ids are dropped"
    assert "political intrigue" in {t["name"] for t in book["traits"]}
    assert book["score"] > 0
    # the suggestion shows up on the tree, dashed under its theme
    tree = alice.get("/api/tree").json()
    pi = next(x for x in tree["branches"] if x["name"] == "political intrigue")
    assert len(pi["suggestions"]) == 2

    # second run must exclude what was already suggested
    alice.post("/api/recommend", json={"mode": "all"})
    fake_llm.queue += [rec_response(b, ids)]
    jobs.run_pending(conn, settings)
    msg = json.loads(fake_llm.calls[-1][1][1]["content"])
    assert any(t.startswith("Dune") for t in msg["exclude"])
    last = alice.get("/api/recommend/status").json()["last"]["result"]
    assert last["kept"] == 0 and last["already_have"] == 2


def test_act(alice, conn, settings, fake_llm):
    uid, ids = setup_user(alice, conn)
    b = boards(alice)
    alice.post("/api/recommend", json={"mode": "all"})
    fake_llm.queue += [rec_response(b, ids), tag_all]
    jobs.run_pending(conn, settings)
    s1, s2 = alice.get("/api/suggestions").json()
    r = alice.post(f"/api/suggestions/{s1['suggestion_id']}/act", json={"action": "want"})
    e = alice.get(f"/api/entries/{r.json()['entry_id']}").json()
    assert e["state"] == "want" and e["board_id"] == s1["board_id"]
    assert alice.post(f"/api/suggestions/{s2['suggestion_id']}/act", json={"action": "done"}).status_code == 400
    alice.post(f"/api/suggestions/{s2['suggestion_id']}/act", json={"action": "dismiss", "reason": "not for me"})
    assert alice.get("/api/suggestions").json() == []
    assert len(alice.get("/api/suggestions", params={"status": "dismissed"}).json()) == 1


def test_bad_output_fails_without_retry(alice, conn, settings, fake_llm):
    setup_user(alice, conn)
    alice.post("/api/recommend", json={"mode": "all"})
    fake_llm.queue += ["no json here", '{"suggestions": []}']
    jobs.run_pending(conn, settings)
    j = conn.execute("SELECT status, attempts FROM job WHERE kind='recommend'").fetchone()
    assert tuple(j) == ("failed", 1)
    assert len(fake_llm.calls) == 2
    assert conn.execute("SELECT status FROM rec_run").fetchone()[0] == "failed"


def test_daily_cap(alice, conn, settings):
    uid, _ = setup_user(alice, conn)
    for _ in range(settings.rec_runs_per_day):
        conn.execute("INSERT INTO rec_run(user_id, scope, status, started_at) VALUES (?, '{}', 'done', ?)", (uid, now_utc()))
    assert alice.post("/api/recommend", json={"mode": "all"}).status_code == 429


def test_cross_user_suggestions(two_clients, conn, settings, fake_llm):
    a, b = two_clients
    uid, ids = setup_user(a, conn)
    a.post("/api/recommend", json={"mode": "all"})
    fake_llm.queue += [rec_response(boards(a), ids), tag_all]
    jobs.run_pending(conn, settings)
    sid = a.get("/api/suggestions").json()[0]["suggestion_id"]
    job_id = conn.execute("SELECT job_id FROM job WHERE kind='recommend'").fetchone()[0]
    assert b.get("/api/suggestions").json() == []
    assert b.post(f"/api/suggestions/{sid}/act", json={"action": "want"}).status_code == 404
    assert b.get(f"/api/jobs/{job_id}").status_code == 404
    assert b.post("/api/recommend", json={"mode": "board", "board_id": boards(a)["book"]}).status_code == 404
