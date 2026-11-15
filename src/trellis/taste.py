"""Taste is plain SQL, not AI: affinity per theme, centred on a 3-star "meh".

affinity(trait) = SUM((rating - 3) * weight) over the user's rated entries
                  - 0.25 * weight for each suggestion they dismissed as "not for me"
This keeps "why was this recommended" fully explainable.
"""

import json
import sqlite3

DISMISS_PENALTY = 0.25
MIN_WEIGHT = 0.35          # weaker links are left off the tree to keep it readable
TREE_FACETS = ("theme", "tone", "setting", "style", "genre")

AFFINITY_SQL = """
WITH scored AS (
  SELECT wt.trait_id, (e.rating - 3) * wt.weight AS a, 1 AS rated
  FROM entry e JOIN work_trait wt ON wt.work_id = e.work_id
  WHERE e.user_id = :uid AND e.state = 'done' AND e.rating IS NOT NULL
  UNION ALL
  SELECT wt.trait_id, -:pen * wt.weight, 0
  FROM suggestion g JOIN work_trait wt ON wt.work_id = g.work_id
  WHERE g.user_id = :uid AND g.status = 'dismissed' AND COALESCE(g.dismiss_reason, '') = 'not for me'
)
SELECT t.trait_id, t.slug, t.name, t.facet, t.description,
       ROUND(SUM(s.a), 3) AS affinity, SUM(s.rated) AS n
FROM scored s JOIN trait t ON t.trait_id = s.trait_id
GROUP BY t.trait_id
"""


def affinity(conn: sqlite3.Connection, user_id: int) -> dict[int, dict]:
    return {r["trait_id"]: dict(r) for r in conn.execute(AFFINITY_SQL, {"uid": user_id, "pen": DISMISS_PENALTY})}


def entry_card(r) -> dict:
    return {"entry_id": r["entry_id"], "work_id": r["work_id"], "title": r["title"], "year": r["year"],
            "creators": json.loads(r["creators"] or "[]"), "cover_url": r["cover_url"], "state": r["state"],
            "rating": r["rating"], "note": r["note"], "board_id": r["board_id"], "board_name": r["board_name"],
            "board_colour": r["board_colour"], "kind": r["kind"]}


ENTRIES_SQL = """
SELECT e.entry_id, e.work_id, e.state, e.rating, e.note, e.board_id, w.title, w.year, w.creators, w.cover_url, w.kind,
       b.name AS board_name, b.colour AS board_colour
FROM entry e JOIN work w ON w.work_id = e.work_id JOIN board b ON b.board_id = e.board_id
WHERE e.user_id = ?
"""

SUGGESTIONS_SQL = """
SELECT g.suggestion_id, g.work_id, g.board_id, g.reason, g.score, g.is_new_branch, g.new_branch_trait_id, g.status,
       w.title, w.year, w.creators, w.cover_url, w.kind, w.url, w.verified, b.name AS board_name, b.colour AS board_colour
FROM suggestion g JOIN work w ON w.work_id = g.work_id JOIN board b ON b.board_id = g.board_id
WHERE g.user_id = ? AND g.status = 'new'
"""


def suggestion_card(r) -> dict:
    return {"suggestion_id": r["suggestion_id"], "work_id": r["work_id"], "title": r["title"], "year": r["year"],
            "creators": json.loads(r["creators"] or "[]"), "cover_url": r["cover_url"], "reason": r["reason"],
            "score": r["score"], "board_id": r["board_id"], "board_name": r["board_name"],
            "board_colour": r["board_colour"], "kind": r["kind"], "url": r["url"], "verified": bool(r["verified"]),
            "is_new_branch": bool(r["is_new_branch"])}


def tree(conn: sqlite3.Connection, user_id: int, group: str = "theme") -> dict:
    entries = {r["entry_id"]: entry_card(r) for r in conn.execute(ENTRIES_SQL, (user_id,))}
    sugg = {r["suggestion_id"]: dict(suggestion_card(r), _nb=r["new_branch_trait_id"])
            for r in conn.execute(SUGGESTIONS_SQL, (user_id,))}
    boards = [dict(r) for r in conn.execute(
        "SELECT board_id, name, kind, colour FROM board WHERE user_id = ? ORDER BY sort_order, board_id", (user_id,))]

    if group == "board":
        branches = []
        for b in boards:
            ids = [e["entry_id"] for e in entries.values() if e["board_id"] == b["board_id"]]
            sids = [s["suggestion_id"] for s in sugg.values() if s["board_id"] == b["board_id"]]
            if ids or sids:
                branches.append({"id": f"b{b['board_id']}", "board_id": b["board_id"], "name": b["name"],
                                 "colour": b["colour"], "entries": ids, "suggestions": sids})
        return _out(group, branches, [], entries, sugg, boards)

    aff = affinity(conn, user_id)
    by_work: dict[int, list[int]] = {}
    for e in entries.values():
        by_work.setdefault(e["work_id"], []).append(e["entry_id"])
    links = conn.execute(
        f"""SELECT wt.work_id, wt.trait_id, wt.weight, t.name, t.facet, t.slug, t.description
            FROM work_trait wt JOIN trait t ON t.trait_id = wt.trait_id
            WHERE wt.weight >= ? AND t.facet IN ({",".join("?" * len(TREE_FACETS))})
              AND wt.work_id IN (SELECT work_id FROM entry WHERE user_id = ?
                                 UNION SELECT work_id FROM suggestion WHERE user_id = ? AND status = 'new')""",
        (MIN_WEIGHT, *TREE_FACETS, user_id, user_id)).fetchall()
    themes: dict[int, dict] = {}
    for l in links:
        t = themes.setdefault(l["trait_id"], {"trait_id": l["trait_id"], "name": l["name"], "facet": l["facet"],
                                              "slug": l["slug"], "description": l["description"],
                                              "entries": [], "suggestions": [], "new_branch": False})
        t["entries"] += by_work.get(l["work_id"], [])
    for sid, s in sugg.items():
        trait_ids = [r[0] for r in conn.execute("SELECT trait_id FROM suggestion_trait WHERE suggestion_id = ?", (sid,))]
        if s["_nb"]:
            trait_ids = [s["_nb"]]
        for tid in trait_ids:
            if tid not in themes:
                tr = conn.execute("SELECT trait_id, name, facet, slug, description FROM trait WHERE trait_id = ?",
                                  (tid,)).fetchone()
                if tr is None:
                    continue
                themes[tid] = {**dict(tr), "entries": [], "suggestions": [], "new_branch": bool(s["_nb"])}
            themes[tid]["suggestions"].append(sid)
    branches, placed = [], set()
    for t in themes.values():
        a = aff.get(t["trait_id"], {})
        t["affinity"] = a.get("affinity", 0.0) or 0.0
        t["n"] = len(set(t["entries"]))
        t["entries"] = sorted(set(t["entries"]), key=lambda i: -(entries[i]["rating"] or 0))
        t["id"] = f"t{t['trait_id']}"
        if t["n"] >= 2 or (t["new_branch"] and t["suggestions"]):
            branches.append(t)
            placed |= set(t["entries"])
        elif t["suggestions"] and t["n"] >= 1:
            branches.append(t)
            placed |= set(t["entries"])
    branches.sort(key=lambda t: (t["new_branch"], -t["affinity"], -t["n"], t["name"]))
    other = sorted(set(entries) - placed)
    return _out(group, branches, other, entries, sugg, boards)


def _out(group, branches, other, entries, sugg, boards) -> dict:
    for s in sugg.values():
        s.pop("_nb", None)
    return {"group": group, "branches": branches, "other": other,
            "entries": {str(k): v for k, v in entries.items()},
            "suggestions": {str(k): v for k, v in sugg.items()}, "boards": boards}
