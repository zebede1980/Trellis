import json

import pytest

from trellis import jobs, llm, traits
from trellis.catalogue.base import WorkData
from trellis.works import upsert


def mk_work(conn, title="Dune", kind="book"):
    return upsert(conn, kind, WorkData(source="manual", source_id=title, title=title, creators=["X"], year=1965,
                                       summary="Desert planet politics", raw_tags=["Science fiction"]))


def good(wid, extra=None):
    ts = [{"slug": "political-intrigue", "weight": 0.9}, {"slug": "epic", "weight": 0.7},
          {"slug": "secondary-fantasy-world", "weight": 0.3}, {"slug": "rich-worldbuilding", "weight": 0.8},
          {"slug": "science-fiction", "weight": 1.0}]
    return json.dumps({"works": [{"id": wid, "traits": ts + (extra or [])}]})


def test_seed_loaded(conn):
    n = conn.execute("SELECT COUNT(*) FROM trait").fetchone()[0]
    assert 60 <= n <= 120
    slugs = [r[0] for r in conn.execute("SELECT slug FROM trait")]
    assert len(slugs) == len(set(slugs))


def test_tag_happy_path_and_new_trait(conn, settings, fake_llm):
    wid = mk_work(conn)
    fake_llm.queue.append(good(wid, [{"new": {"name": "Generation Ship", "facet": "setting", "description": "d"},
                                      "weight": 0.5}]))
    out = traits.tag_works(conn, settings, [conn.execute("SELECT * FROM work WHERE work_id=?", (wid,)).fetchone()])
    assert ("generation-ship", 0.5) in out[wid]
    assert conn.execute("SELECT tagged_at FROM work WHERE work_id=?", (wid,)).fetchone()[0]
    assert conn.execute("SELECT COUNT(*) FROM work_trait WHERE work_id=?", (wid,)).fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM llm_call WHERE purpose='tag' AND ok=1").fetchone()[0] == 1


def test_near_duplicate_new_maps_to_existing(conn, settings, fake_llm):
    wid = mk_work(conn)
    fake_llm.queue.append(good(wid, [{"new": {"name": "found families", "facet": "theme"}, "weight": 0.6}]))
    out = traits.tag_works(conn, settings, [conn.execute("SELECT * FROM work WHERE work_id=?", (wid,)).fetchone()])
    assert ("found-family", 0.6) in out[wid]
    assert conn.execute("SELECT COUNT(*) FROM trait WHERE slug LIKE 'found-famil%'").fetchone()[0] == 1


def test_malformed_then_fixed(conn, settings, fake_llm):
    wid = mk_work(conn)
    fake_llm.queue += ["sorry, here you go: {not json", good(wid)]
    traits.tag_works(conn, settings, [conn.execute("SELECT * FROM work WHERE work_id=?", (wid,)).fetchone()])
    assert len(fake_llm.calls) == 2
    assert "failed validation" in fake_llm.calls[1][1][-1]["content"]


def test_rules_enforced(conn, settings, fake_llm):
    wid = mk_work(conn)
    w = conn.execute("SELECT * FROM work WHERE work_id=?", (wid,)).fetchone()
    too_few = json.dumps({"works": [{"id": wid, "traits": [{"slug": "science-fiction", "weight": 1}]}]})
    genre_heavy = json.dumps({"works": [{"id": wid, "traits": [
        {"slug": s, "weight": 0.5} for s in ("science-fiction", "fantasy", "horror", "mystery", "epic")]}]})
    many_new = good(wid, [{"new": {"name": f"zzq thing {i}", "facet": "theme"}, "weight": 0.2} for i in "abc"][:3])
    for bad in (too_few, genre_heavy):
        fake_llm.queue += [bad, bad]
        with pytest.raises(llm.LLMError):
            traits.tag_works(conn, settings, [w])
    fake_llm.queue += [many_new, many_new]
    with pytest.raises(llm.LLMError):  # 5 + 3 new = 8 traits is fine, but 3 new is too many
        traits.tag_works(conn, settings, [w])


def test_tag_job_batches(conn, settings, fake_llm, alice):
    bid = alice.get("/api/boards").json()[0]["board_id"]
    alice.post("/api/entries", json={"board_id": bid, "source": "openlibrary", "source_id": "OL893414W"})
    alice.post("/api/entries", json={"board_id": bid, "manual": {"title": "Hyperion"}})

    def respond(model, messages):
        ws = json.loads(messages[1]["content"])["works"]
        return json.dumps({"works": [json.loads(good(w["id"]))["works"][0] for w in ws]})

    fake_llm.queue.append(respond)
    assert jobs.run_pending(conn, settings) == 1
    assert conn.execute("SELECT COUNT(*) FROM work WHERE tagged_at IS NULL").fetchone()[0] == 0
    e = alice.get(f"/api/boards/{bid}/entries").json()[0]
    detail = alice.get(f"/api/entries/{e['entry_id']}").json()
    assert {t["slug"] for t in detail["traits"]} >= {"political-intrigue", "epic"}


def test_job_retries_then_fails(conn, settings, fake_llm):
    mk_work(conn)
    conn.execute("INSERT INTO app_user(username, pw_hash, created_at) VALUES ('z','x','now')")
    jid = jobs.enqueue(conn, "nope", {})
    for _ in range(3):
        jobs.run_one(conn, settings)
    r = conn.execute("SELECT status, attempts FROM job WHERE job_id=?", (jid,)).fetchone()
    assert tuple(r) == ("failed", 3)


def test_merge(conn, settings, fake_llm):
    wid = mk_work(conn)
    fake_llm.queue.append(good(wid))
    traits.tag_works(conn, settings, [conn.execute("SELECT * FROM work WHERE work_id=?", (wid,)).fetchone()])
    tid = lambda s: conn.execute("SELECT trait_id FROM trait WHERE slug=?", (s,)).fetchone()[0]
    traits.merge(conn, tid("epic"), tid("political-intrigue"))
    rows = dict(conn.execute("SELECT t.slug, wt.weight FROM work_trait wt JOIN trait t USING(trait_id) WHERE work_id=?",
                             (wid,)).fetchall())
    assert "epic" not in rows and rows["political-intrigue"] == 0.9
    assert traits.canonical(conn, tid("epic")) == tid("political-intrigue")


def test_tag_job_failure_is_not_retried(conn, settings, fake_llm, alice):
    bid = alice.get("/api/boards").json()[0]["board_id"]
    alice.post("/api/entries", json={"board_id": bid, "manual": {"title": "Hyperion"}})
    fake_llm.queue += ["{broken", "{still broken"]
    jobs.run_pending(conn, settings)
    assert len(fake_llm.calls) == 2
    assert conn.execute("SELECT status FROM job").fetchone()[0] == "failed"
