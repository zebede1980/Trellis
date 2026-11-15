from trellis.db import now_utc


def seed_tagged(conn, uid, items):
    """items: list of (title, rating, [trait slugs]) on the user's first board; returns entry ids."""
    bid = conn.execute("SELECT board_id FROM board WHERE user_id = ? ORDER BY sort_order LIMIT 1", (uid,)).fetchone()[0]
    ids = []
    for title, rating, slugs in items:
        wid = conn.execute("INSERT INTO work(kind, source, source_id, title, fetched_at, tagged_at) VALUES "
                           "('book','manual',?,?,?,?) RETURNING work_id", (title, title, now_utc(), now_utc())).fetchone()[0]
        for s in slugs:
            tid = conn.execute("SELECT trait_id FROM trait WHERE slug = ?", (s,)).fetchone()[0]
            conn.execute("INSERT INTO work_trait VALUES (?,?,0.9)", (wid, tid))
        ids.append(conn.execute("INSERT INTO entry(user_id, board_id, work_id, state, rating, created_at, updated_at) "
                                "VALUES (?,?,?,'done',?,?,?) RETURNING entry_id",
                                (uid, bid, wid, rating, now_utc(), now_utc())).fetchone()[0])
    return ids


def test_affinity_and_tree(alice, conn):
    uid = conn.execute("SELECT user_id FROM app_user WHERE username='alice'").fetchone()[0]
    seed_tagged(conn, uid, [("A", 5, ["political-intrigue", "epic"]), ("B", 4, ["political-intrigue", "cozy"]),
                            ("C", 1, ["epic", "horror"]), ("D", 3, ["found-family"])])
    t = alice.get("/api/tree").json()
    names = [b["name"] for b in t["branches"]]
    assert names[0] == "political intrigue"   # (2 + 1) * 0.9 = 2.7
    assert "epic" in names                       # (2 - 2) * 0.9 = 0, but 2 entries
    assert "cozy" not in names                   # only one entry: goes to "other threads"
    other_titles = {t["entries"][str(i)]["title"] for i in t["other"]}
    assert other_titles == {"D"}
    pi = next(b for b in t["branches"] if b["name"] == "political intrigue")
    assert pi["affinity"] == 2.7 and pi["n"] == 2
    tb = alice.get("/api/tree", params={"group": "board"}).json()
    assert tb["branches"][0]["name"] == "Books" and len(tb["branches"][0]["entries"]) == 4
    th = alice.get(f"/api/themes/{pi['trait_id']}").json()
    assert [e["title"] for e in th["entries"]] == ["A", "B"]
    assert {r["name"] for r in th["related"]} >= {"epic", "cozy"}
    assert alice.get("/api/themes").json()[0]["name"] == "political intrigue"


def test_tree_is_private(two_clients, conn):
    a, b = two_clients
    uid = conn.execute("SELECT user_id FROM app_user WHERE username='alice'").fetchone()[0]
    seed_tagged(conn, uid, [("Secret", 5, ["political-intrigue"]), ("Secret2", 5, ["political-intrigue"])])
    assert b.get("/api/tree").json()["entries"] == {}
    tid = conn.execute("SELECT trait_id FROM trait WHERE slug='political-intrigue'").fetchone()[0]
    assert b.get(f"/api/themes/{tid}").json()["entries"] == []
