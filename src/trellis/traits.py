"""Themes ("traits"): a controlled vocabulary the AI must reuse before it invents.

Tagging rules are enforced in code, not just in the prompt:
- 5 to 8 traits per work
- at least 3 from the media-agnostic facets (theme, tone, setting, style), which is what links a book to a game
- at most 2 new traits per work
- a new trait whose slug, or name similarity (difflib ratio >= 0.88), matches an existing trait is mapped to it
"""

import json
import os
import re
import sqlite3
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from trellis import jobs, llm
from trellis.config import Settings
from trellis.db import now_utc

FACETS = ("theme", "tone", "setting", "style", "genre", "medium")
AGNOSTIC = ("theme", "tone", "setting", "style")
SEED = Path(__file__).parent / "seed_traits.json"
NEAR_DUP = 0.88
MIN_T, MAX_T, MIN_AGNOSTIC, MAX_NEW = 5, 8, 3, 2


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _singular(slug: str) -> str:
    def one(w: str) -> str:
        if len(w) > 4 and w.endswith("ies"):
            return w[:-3] + "y"
        if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
            return w[:-1]
        return w
    return "-".join(one(w) for w in slug.split("-"))


def load_seed(conn: sqlite3.Connection) -> int:
    if conn.execute("SELECT COUNT(*) FROM trait").fetchone()[0]:
        return 0
    rows = json.loads(SEED.read_text(encoding="utf-8"))
    now = now_utc()
    conn.executemany("INSERT INTO trait(slug, name, facet, description, created_at) VALUES (?,?,?,?,?)",
                     [(slugify(r["name"]), r["name"], r["facet"], r.get("description"), now) for r in rows])
    return len(rows)


def vocabulary(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT trait_id, slug, name, facet, description FROM trait WHERE merged_into_id IS NULL "
                        "ORDER BY facet, name").fetchall()


def canonical(conn: sqlite3.Connection, trait_id: int) -> int:
    for _ in range(10):
        r = conn.execute("SELECT merged_into_id FROM trait WHERE trait_id = ?", (trait_id,)).fetchone()
        if r is None or r[0] is None:
            return trait_id
        trait_id = r[0]
    return trait_id


def find_similar(vocab: list, name: str) -> sqlite3.Row | dict | None:
    slug = slugify(name)
    if not slug:
        return None
    for t in vocab:
        if t["slug"] == slug or _singular(t["slug"]) == _singular(slug):
            return t
    best, best_r = None, 0.0
    for t in vocab:
        r = max(SequenceMatcher(None, slug, t["slug"]).ratio(),
                SequenceMatcher(None, name.lower().strip(), t["name"].lower()).ratio())
        if r > best_r:
            best, best_r = t, r
    return best if best_r >= NEAR_DUP else None


def create(conn: sqlite3.Connection, name: str, facet: str, description: str | None) -> int:
    name = re.sub(r"\s+", " ", name).strip().lower()
    cur = conn.execute("INSERT INTO trait(slug, name, facet, description, created_at) VALUES (?,?,?,?,?) "
                       "ON CONFLICT(slug) DO UPDATE SET slug = excluded.slug RETURNING trait_id",
                       (slugify(name), name, facet, (description or "").strip()[:300] or None, now_utc()))
    return cur.fetchone()[0]


def merge(conn: sqlite3.Connection, from_id: int, into_id: int) -> None:
    """Fold one trait into another: repoint every link, keep the higher weight, and remember the merge."""
    into_id = canonical(conn, into_id)
    if from_id == into_id:
        raise ValueError("cannot merge a trait into itself")
    conn.execute("BEGIN")
    try:
        conn.execute("""INSERT INTO work_trait(work_id, trait_id, weight)
                        SELECT work_id, ?, weight FROM work_trait WHERE trait_id = ?
                        ON CONFLICT(work_id, trait_id) DO UPDATE SET weight = MAX(work_trait.weight, excluded.weight)""",
                     (into_id, from_id))
        conn.execute("DELETE FROM work_trait WHERE trait_id = ?", (from_id,))
        conn.execute("""INSERT OR IGNORE INTO suggestion_trait(suggestion_id, trait_id)
                        SELECT suggestion_id, ? FROM suggestion_trait WHERE trait_id = ?""", (into_id, from_id))
        conn.execute("DELETE FROM suggestion_trait WHERE trait_id = ?", (from_id,))
        conn.execute("UPDATE suggestion SET new_branch_trait_id = ? WHERE new_branch_trait_id = ?", (into_id, from_id))
        conn.execute("UPDATE trait SET merged_into_id = ? WHERE trait_id = ?", (into_id, from_id))
        conn.execute("UPDATE trait SET merged_into_id = ? WHERE merged_into_id = ?", (into_id, from_id))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


# --------------------------------------------------------------------------- tagging

SYSTEM = """You tag creative works (books, films, TV, games, music, and anything else) with themes from a shared vocabulary, so that a user's taste can be linked ACROSS media: a political-intrigue novel should share tags with a political-intrigue game.

Rules:
- Give each work 6 to 8 traits (never fewer than 5, never more than 8).
- At least 3 must come from the media-agnostic facets: theme, tone, setting, style. These are what connect different media, so favour them.
- Strongly prefer existing vocabulary slugs. Only invent a trait ("new") when nothing in the vocabulary fits; at most 2 new per work.
- A new trait must be at the same grain as the vocabulary: "political intrigue", not "politics" and not "Byzantine succession crises". Reusable across many works and media. Lower case.
- weight is 0.1 to 1.0: how central the trait is to the work (1.0 = defining).
- Format/medium labels (open world, miniseries, concept album...) only when literally true of the work.
- Use what you know about the work plus the catalogue tags given. If you do not know the work, tag conservatively from the summary and tags.

Return ONLY JSON:
{"works": [{"id": <id>, "traits": [{"slug": "found-family", "weight": 0.9}, {"new": {"name": "generation ship", "facet": "setting", "description": "one line"}, "weight": 0.6}]}]}"""


def _work_payload(w: sqlite3.Row) -> dict:
    return {"id": w["work_id"], "kind": w["kind"], "title": w["title"],
            "creators": json.loads(w["creators"] or "[]"), "year": w["year"],
            "summary": (w["summary"] or "")[:700] or None, "catalogue_tags": json.loads(w["raw_tags"] or "[]")[:20]}


def build_messages(vocab: list, ws: list[sqlite3.Row], board_hints: dict[int, str] | None = None) -> list[dict]:
    by_facet: dict[str, list[str]] = {}
    for t in vocab:
        by_facet.setdefault(t["facet"], []).append(f"{t['slug']} ({t['name']})" if slugify(t["name"]) != t["slug"]
                                                   else t["slug"])
    items = []
    for w in ws:
        p = _work_payload(w)
        if board_hints and board_hints.get(w["work_id"]):
            p["what_it_is"] = board_hints[w["work_id"]]
        items.append(p)
    user = {"vocabulary": by_facet, "works": items}
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(user, ensure_ascii=False)}]


def make_validator(vocab: list, work_ids: list[int]):
    by_slug = {t["slug"]: t for t in vocab}

    def validate(obj: dict) -> list[str]:
        errors: list[str] = []
        got = {w.get("id"): w for w in obj.get("works", []) if isinstance(w, dict)}
        for wid in work_ids:
            w = got.get(wid)
            if w is None:
                errors.append(f"work {wid} missing")
                continue
            resolved, n_new = [], 0
            for t in w.get("traits", []):
                if not isinstance(t, dict):
                    errors.append(f"work {wid}: trait entries must be objects")
                    continue
                weight = t.get("weight")
                if not isinstance(weight, (int, float)) or not 0 < weight <= 1:
                    errors.append(f"work {wid}: weight must be between 0.1 and 1.0")
                    continue
                if "slug" in t:
                    slug = str(t["slug"]).strip()
                    hit = by_slug.get(slug) or find_similar(vocab, slug.replace("-", " "))
                    if hit is None:
                        errors.append(f"work {wid}: unknown slug {slug!r}; use a vocabulary slug or a 'new' trait")
                        continue
                    resolved.append({"slug": hit["slug"], "facet": hit["facet"], "weight": float(weight)})
                elif isinstance(t.get("new"), dict):
                    nw = t["new"]
                    name, facet = str(nw.get("name", "")).strip(), nw.get("facet")
                    if not name or facet not in FACETS:
                        errors.append(f"work {wid}: new trait needs a name and a facet in {FACETS}")
                        continue
                    hit = find_similar(vocab, name)
                    if hit is not None:   # silently map near-duplicates onto the existing trait
                        resolved.append({"slug": hit["slug"], "facet": hit["facet"], "weight": float(weight)})
                    else:
                        n_new += 1
                        resolved.append({"new": {"name": name, "facet": facet,
                                                 "description": str(nw.get("description", ""))[:300]},
                                         "facet": facet, "weight": float(weight)})
                else:
                    errors.append(f"work {wid}: each trait needs 'slug' or 'new'")
            # de-duplicate after mapping, keeping the highest weight
            uniq: dict[str, dict] = {}
            for r in resolved:
                key = r.get("slug") or slugify(r["new"]["name"])
                if key not in uniq or r["weight"] > uniq[key]["weight"]:
                    uniq[key] = r
            resolved = list(uniq.values())
            if not MIN_T <= len(resolved) <= MAX_T:
                errors.append(f"work {wid}: needs {MIN_T}-{MAX_T} distinct traits, got {len(resolved)}")
            if sum(r["facet"] in AGNOSTIC for r in resolved) < MIN_AGNOSTIC:
                errors.append(f"work {wid}: needs at least {MIN_AGNOSTIC} traits from theme/tone/setting/style")
            if n_new > MAX_NEW:
                errors.append(f"work {wid}: at most {MAX_NEW} new traits, got {n_new}")
            w["_resolved"] = resolved
        return errors

    return validate


def tag_works(conn: sqlite3.Connection, s: Settings, ws: list[sqlite3.Row], *, model: str | None = None,
              user_id: int | None = None, write: bool = True, board_hints: dict[int, str] | None = None) -> dict:
    """Tag a batch of works in one LLM call. Returns {work_id: [(slug, weight), ...]}."""
    load_seed(conn)
    vocab = [dict(t) for t in vocabulary(conn)]
    ids = [w["work_id"] for w in ws]
    obj = llm.call_json(conn, s, purpose="tag", model=model or s.tag_model, messages=build_messages(vocab, ws, board_hints),
                        validate=make_validator(vocab, ids), user_id=user_id, max_tokens=400 + 400 * len(ws),
                        temperature=0.0)
    out: dict[int, list[tuple[str, float]]] = {}
    by_id = {w["id"]: w for w in obj["works"] if isinstance(w, dict)}
    for wid in ids:
        out[wid] = []
        for r in by_id[wid]["_resolved"]:
            if "new" in r:
                if write:
                    tid = create(conn, r["new"]["name"], r["new"]["facet"], r["new"]["description"])
                    slug = conn.execute("SELECT slug FROM trait WHERE trait_id = ?", (tid,)).fetchone()[0]
                else:
                    slug = "+" + slugify(r["new"]["name"])   # marks an invented trait in eval output
            else:
                slug = r["slug"]
            out[wid].append((slug, r["weight"]))
    if write:
        now = now_utc()
        for wid, pairs in out.items():
            conn.execute("DELETE FROM work_trait WHERE work_id = ?", (wid,))
            for slug, weight in pairs:
                tid = conn.execute("SELECT trait_id FROM trait WHERE slug = ?", (slug,)).fetchone()[0]
                conn.execute("INSERT OR REPLACE INTO work_trait(work_id, trait_id, weight) VALUES (?,?,?)",
                             (wid, canonical(conn, tid), weight))
            conn.execute("UPDATE work SET tagged_at = ? WHERE work_id = ?", (now, wid))
    return out


def _batch_size() -> int:
    return max(1, int(os.environ.get("TAG_BATCH", "5")))


@jobs.handler("tag")
def job_tag(conn: sqlite3.Connection, s: Settings, payload: dict, user_id: int | None) -> dict:
    """Tag untagged works that someone has on a board or as a suggestion, a batch per LLM call."""
    ws = conn.execute(
        """SELECT * FROM work w WHERE w.tagged_at IS NULL
             AND (EXISTS (SELECT 1 FROM entry e WHERE e.work_id = w.work_id)
                  OR EXISTS (SELECT 1 FROM suggestion g WHERE g.work_id = w.work_id))
           ORDER BY w.work_id LIMIT ?""", (_batch_size(),)).fetchall()
    if not ws:
        return {"tagged": 0}
    hints = {r[0]: r[1] for r in conn.execute(
        """SELECT e.work_id, b.custom_hint FROM entry e JOIN board b ON b.board_id = e.board_id
           WHERE b.kind = 'custom' AND e.work_id IN (%s)""" % ",".join("?" * len(ws)), [w["work_id"] for w in ws])}
    tag_works(conn, s, ws, user_id=user_id, board_hints=hints)
    remaining = conn.execute(
        """SELECT 1 FROM work w WHERE w.tagged_at IS NULL AND EXISTS (SELECT 1 FROM entry e WHERE e.work_id = w.work_id)
           LIMIT 1""").fetchone()
    if remaining:
        jobs.enqueue(conn, "tag", {}, user_id)
    return {"tagged": len(ws), "titles": [w["title"] for w in ws]}
