"""The suggestion pipeline.

taste context (SQL) -> ask the model for about twice what we need -> match each idea to a real catalogue record
(normalised title ratio >= 0.9 AND year within 1 or a creator overlap) -> drop non-matches on built-in boards ->
drop anything the user already has or was already shown -> tag the survivors -> score by affinity overlap -> store.

The model only does taste (which ideas, and why). Titles, creators, years and covers come from the catalogues.
"""

import hashlib
import json
import logging
import re
import sqlite3
from typing import Any

from trellis import catalogue, jobs, llm, match, taste, traits, works
from trellis.catalogue.ai_lookup import brave_search
from trellis.config import Settings
from trellis.db import now_utc

log = logging.getLogger(__name__)
MODES = ("all", "trait", "board", "explore")
KEEP = 8            # suggestions stored per run
ASK = 14            # ideas requested per run
MAX_REASON_WORDS = 45


class CapReached(Exception):
    pass


def runs_today(conn: sqlite3.Connection, user_id: int) -> int:
    return conn.execute("SELECT COUNT(*) FROM rec_run WHERE user_id = ? AND started_at >= date('now')",
                        (user_id,)).fetchone()[0]


def start(conn: sqlite3.Connection, s: Settings, user_id: int, scope: dict) -> int:
    """Validate the request, enforce the daily cap, and queue the job. Returns the job id."""
    if runs_today(conn, user_id) + _queued(conn, user_id) >= s.rec_runs_per_day:
        raise CapReached(f"You've used today's {s.rec_runs_per_day} suggestion runs. More tomorrow.")
    return jobs.enqueue(conn, "recommend", scope, user_id)


def _queued(conn, user_id) -> int:
    return conn.execute("SELECT COUNT(*) FROM job WHERE user_id = ? AND kind = 'recommend' AND status IN "
                        "('queued', 'running')", (user_id,)).fetchone()[0]


# --------------------------------------------------------------------------- taste context

def _clip(s: str | None, n: int) -> str | None:
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def build_context(conn: sqlite3.Connection, user_id: int, scope: dict) -> dict:
    mode = scope.get("mode", "all")
    aff = taste.affinity(conn, user_id)
    rows = conn.execute(taste.ENTRIES_SQL + " ORDER BY e.rating DESC NULLS LAST, e.updated_at DESC", (user_id,)).fetchall()
    entries = [taste.entry_card(r) for r in rows]
    trait_names = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT trait_id, slug, name FROM trait")}
    work_traits: dict[int, list[int]] = {}
    for wid, tid in conn.execute(
            "SELECT wt.work_id, wt.trait_id FROM work_trait wt JOIN entry e ON e.work_id = wt.work_id "
            "WHERE e.user_id = ? AND wt.weight >= 0.5", (user_id,)):
        work_traits.setdefault(wid, []).append(tid)

    def ent(e: dict) -> dict:
        d = {"id": e["entry_id"], "title": e["title"], "by": ", ".join(e["creators"][:2]) or None, "year": e["year"],
             "kind": e["kind"], "rating": e["rating"]}
        if e["note"]:
            d["note"] = _clip(e["note"], 220)
        return d

    liked = sorted((a for a in aff.values() if (a["affinity"] or 0) > 0), key=lambda a: -a["affinity"])[:10]
    disliked = sorted((a for a in aff.values() if (a["affinity"] or 0) < 0), key=lambda a: a["affinity"])[:6]
    by_trait: dict[int, list[dict]] = {}
    for e in entries:
        for tid in work_traits.get(e["work_id"], []):
            by_trait.setdefault(tid, []).append(e)

    ctx: dict[str, Any] = {
        "liked_themes": [{"slug": a["slug"], "name": a["name"], "affinity": a["affinity"],
                          "examples": [x["title"] for x in by_trait.get(a["trait_id"], []) if (x["rating"] or 0) >= 4][:3]}
                         for a in liked],
        "disliked_themes": [{"slug": a["slug"], "name": a["name"]} for a in disliked],
        "loved": [ent(e) for e in entries if (e["rating"] or 0) >= 4][:30],
        "disliked": [ent(e) for e in entries if e["rating"] is not None and e["rating"] <= 2][:12],
        "want_to_try": [e["title"] for e in entries if e["state"] == "want"][:20],
    }
    dismissed = conn.execute(
        """SELECT w.title, g.dismiss_reason FROM suggestion g JOIN work w ON w.work_id = g.work_id
           WHERE g.user_id = ? AND g.status = 'dismissed' ORDER BY g.acted_at DESC LIMIT 20""", (user_id,)).fetchall()
    if dismissed:
        ctx["recently_rejected_suggestions"] = [f"{r[0]} ({r[1] or 'no reason'})" for r in dismissed]
    if mode == "trait" and scope.get("trait_id"):
        tid = traits.canonical(conn, int(scope["trait_id"]))
        slug, name = trait_names.get(tid, ("", ""))
        ctx["focus_theme"] = {"slug": slug, "name": name,
                              "your_entries_with_it": [ent(e) for e in by_trait.get(tid, [])][:12]}
    return ctx


def exclude_titles(conn: sqlite3.Connection, user_id: int) -> list[str]:
    rows = conn.execute(
        """SELECT w.title, w.year FROM entry e JOIN work w ON w.work_id = e.work_id WHERE e.user_id = ?
           UNION SELECT w.title, w.year FROM suggestion g JOIN work w ON w.work_id = g.work_id WHERE g.user_id = ?""",
        (user_id, user_id)).fetchall()
    return [f"{r[0]} ({r[1]})" if r[1] else r[0] for r in rows][:400]


def target_boards(conn: sqlite3.Connection, user_id: int, scope: dict) -> list[dict]:
    rows = conn.execute("SELECT board_id, name, kind, custom_hint FROM board WHERE user_id = ? ORDER BY sort_order",
                        (user_id,)).fetchall()
    if scope.get("mode") == "board" and scope.get("board_id"):
        rows = [r for r in rows if r["board_id"] == int(scope["board_id"])]
    out = []
    for r in rows:
        d = {"board_id": r["board_id"], "name": r["name"], "kind": r["kind"]}
        if r["kind"] == "custom":
            d["holds"] = r["custom_hint"]
        out.append(d)
    return out


# --------------------------------------------------------------------------- prompt

SYSTEM = """You are a thoughtful cross-media recommender. You know the user's taste from what they have rated and written. Your job: suggest specific, REAL, existing works they have not tried, and explain each in terms of their own entries.

Hard rules:
- Only real, released works that you are confident exist. Use the exact official title (as the catalogue would list it), the main creator (author / director / showrunner / developer / artist), and the original release year. If unsure a work exists, leave it out.
- Never suggest anything in "exclude" (already on their boards or already suggested), and nothing from "recently_rejected_suggestions".
- Each suggestion goes on one of the given boards (board_id) and must be the kind of thing that board holds. For a custom board, follow what the board "holds".
- reason: max 40 words, second person, concrete, and it must name at least one of the user's own entries. No hype words.
- because_entries: ids from the user's entries that this follows from. because_traits: slugs from liked_themes or focus_theme.
- Favour cross-media links (a book for someone who loves a game's themes). Mix well-known and lesser-known; avoid the obvious top-10 list unless it is a genuinely strong fit.
- Respect disliked themes and low ratings: steer away from them.
- new_branch: null, except as the mode says below.

{mode_rules}

Return ONLY JSON:
{{"suggestions": [{{"title": "", "creator": "", "year": 2021, "board_id": 1, "because_traits": ["political-intrigue"], "because_entries": [12], "reason": "", "new_branch": null}}]}}"""

MODE_RULES = {
    "all": "Mode: balanced. Spread suggestions across the target boards, weighted towards the strongest liked themes.",
    "board": "Mode: board. Every suggestion goes on the single target board.",
    "trait": "Mode: more of one theme. Every suggestion must strongly feature focus_theme, ideally across several boards.",
    "explore": ("Mode: explore. Propose themes the user has NOT explored yet but would plausibly enjoy given what "
                "they love. For every suggestion set new_branch to {\"name\": \"theme name\", \"facet\": "
                "\"theme|tone|setting|style\", \"description\": \"one line\"}, at the grain of 'political intrigue' "
                "or 'found family'. Use 3-5 different new branches, 2-4 works each. The new branch must not be one of "
                "liked_themes."),
}


def make_validator(boards: list[dict], entry_ids: set[int], mode: str):
    board_ids = {b["board_id"] for b in boards}

    def validate(obj: dict) -> list[str]:
        sugg = obj.get("suggestions")
        if not isinstance(sugg, list) or not sugg:
            return ["'suggestions' must be a non-empty list"]
        errs = []
        for i, x in enumerate(sugg):
            if not isinstance(x, dict) or not str(x.get("title", "")).strip():
                errs.append(f"suggestion {i}: needs a title")
                continue
            if x.get("board_id") not in board_ids:
                errs.append(f"suggestion {i} ({x.get('title')}): board_id must be one of {sorted(board_ids)}")
            if len(str(x.get("reason", "")).split()) > MAX_REASON_WORDS:
                errs.append(f"suggestion {i}: reason is over 40 words")
            if not str(x.get("reason", "")).strip():
                errs.append(f"suggestion {i}: needs a reason")
            x["because_entries"] = [e for e in (x.get("because_entries") or []) if isinstance(e, int) and e in entry_ids]
            x["because_traits"] = [str(t) for t in (x.get("because_traits") or []) if isinstance(t, str)]
            nb = x.get("new_branch")
            if mode == "explore":
                if not isinstance(nb, dict) or not nb.get("name") or nb.get("facet") not in traits.FACETS:
                    errs.append(f"suggestion {i}: explore mode needs new_branch with name and facet")
            elif nb is not None and not isinstance(nb, dict):
                x["new_branch"] = None
        return errs

    return validate


# --------------------------------------------------------------------------- matching

def _brave_url(s: Settings, title: str, creator: str | None) -> str | None:
    try:
        results = brave_search(s, f"{title} {creator or ''}".strip(), count=5)
    except catalogue.ProviderError:
        return None
    for r in results:
        if match.title_ratio(title, (r.get("title") or "").split(" - ")[0].split(" | ")[0]) >= 0.8 or \
                match.norm_title(title) in match.norm_title(r.get("title") or ""):
            return r.get("url")
    return None


def resolve(conn: sqlite3.Connection, s: Settings, board: dict, idea: dict) -> tuple[int | None, str]:
    """Find the catalogue record for an idea. Returns (work_id, outcome)."""
    title, year, creator = str(idea["title"]).strip(), idea.get("year"), idea.get("creator") or None
    year = year if isinstance(year, int) else None
    if board["kind"] == "custom":
        url = _brave_url(s, title, creator) if s.brave_api_key else None
        hint = board.get("holds") or ""
        sid = hashlib.sha1(f"{hint}|{title.lower()}|{year}".encode()).hexdigest()[:16]
        wid = works.add_manual(conn, "custom", title, [creator] if creator else [], year, url=url, source="ai",
                               source_id=sid, verified=url is not None)
        return wid, "custom"
    try:
        cands = catalogue.search(board["kind"], title, s)
    except catalogue.ProviderError as e:
        log.info("catalogue search failed for %r: %s", title, e)
        return None, "search_failed"
    hit = match.best_match(title, year, creator, cands)
    if hit is None:
        return None, "unmatched"
    try:
        return works.get_or_fetch(conn, s, board["kind"], hit.source, hit.source_id), "matched"
    except catalogue.ProviderError:
        return None, "fetch_failed"


# --------------------------------------------------------------------------- the job

def run(conn: sqlite3.Connection, s: Settings, user_id: int, scope: dict, *, dry_run: bool = False,
        log_fn=None) -> dict:
    mode = scope.get("mode", "all")
    if mode not in MODES:
        raise jobs.PermanentError(f"bad mode {mode!r}")
    model = s.rec_model
    run_id = conn.execute("INSERT INTO rec_run(user_id, scope, model, status, started_at) VALUES (?,?,?,?,?)",
                          (user_id, json.dumps(scope), model, "running", now_utc())).lastrowid
    stats: dict[str, Any] = {"asked": ASK, "returned": 0, "matched": 0, "unmatched": [], "already_have": 0,
                             "kept": 0, "custom": 0}
    try:
        boards = target_boards(conn, user_id, scope)
        if not boards:
            raise jobs.PermanentError("no target boards")
        ctx = build_context(conn, user_id, scope)
        entry_ids = {r[0] for r in conn.execute("SELECT entry_id FROM entry WHERE user_id = ?", (user_id,))}
        user_msg = {"mode": mode, "how_many": ASK, "boards": boards, **ctx, "exclude": exclude_titles(conn, user_id)}
        if s.rec_web_search and s.brave_api_key and ctx.get("focus_theme"):
            try:
                user_msg["web_results"] = brave_search(
                    s, f"best {ctx['focus_theme']['name']} books films games recommendations", count=6)
            except catalogue.ProviderError:
                pass
        obj = llm.call_json(conn, s, purpose=f"recommend:{mode}", model=model, user_id=user_id, max_tokens=4000,
                            temperature=0.7,
                            messages=[{"role": "system", "content": SYSTEM.format(mode_rules=MODE_RULES[mode])},
                                      {"role": "user", "content": json.dumps(user_msg, ensure_ascii=False)}],
                            validate=make_validator(boards, entry_ids, mode))
        ideas = obj["suggestions"]
        stats["returned"] = len(ideas)
        by_board = {b["board_id"]: b for b in boards}
        have = {r[0] for r in conn.execute("SELECT work_id FROM entry WHERE user_id = ? UNION "
                                           "SELECT work_id FROM suggestion WHERE user_id = ?", (user_id, user_id))}
        kept: list[tuple[dict, int, dict]] = []
        for idea in ideas:
            if len(kept) >= KEEP and mode != "explore":
                break
            board = by_board[idea["board_id"]]
            wid, outcome = resolve(conn, s, board, idea)
            if log_fn:
                log_fn(f"  {outcome:<13} {idea['title']} ({idea.get('year')}) -> board {board['name']}")
            if wid is None:
                stats["unmatched"].append(f"{idea['title']} ({idea.get('year')}): {outcome}")
                continue
            stats["matched" if outcome == "matched" else "custom"] += 1
            if wid in have:
                stats["already_have"] += 1
                continue
            have.add(wid)
            kept.append((idea, wid, board))
        if mode == "explore":
            kept = kept[:12]

        # tag survivors so they slot into the tree, in batches
        untagged = [w for w in conn.execute(
            f"SELECT * FROM work WHERE tagged_at IS NULL AND work_id IN ({','.join('?' * len(kept))})",
            [k[1] for k in kept]).fetchall()] if kept else []
        for i in range(0, len(untagged), 5):
            try:
                traits.tag_works(conn, s, untagged[i:i + 5], user_id=user_id)
            except llm.LLMError as e:
                log.warning("tagging suggestions failed: %s", e)

        aff = taste.affinity(conn, user_id)
        vocab = [dict(t) for t in traits.vocabulary(conn)]
        now = now_utc()
        for idea, wid, board in kept:
            wts = conn.execute("SELECT trait_id, weight FROM work_trait WHERE work_id = ?", (wid,)).fetchall()
            score = sum((aff.get(t, {}).get("affinity") or 0) * w for t, w in wts)
            because = []
            for slug in idea["because_traits"]:
                hit = next((v for v in vocab if v["slug"] == slug), None) or traits.find_similar(vocab, slug.replace("-", " "))
                if hit:
                    because.append(traits.canonical(conn, hit["trait_id"]))
            # also link the strongest overlaps with the user's liked themes, so the tree can place it
            overlap = sorted(((aff[t]["affinity"] or 0) * w, t) for t, w in wts if t in aff and (aff[t]["affinity"] or 0) > 0)
            because += [t for _, t in reversed(overlap[-3:])]
            nb_tid = None
            if idea.get("new_branch"):
                nb = idea["new_branch"]
                hit = traits.find_similar(vocab, nb["name"])
                nb_tid = traits.canonical(conn, hit["trait_id"]) if hit else traits.create(
                    conn, nb["name"], nb["facet"], nb.get("description"))
                if not hit:
                    vocab.append({"trait_id": nb_tid, "slug": traits.slugify(nb["name"]), "name": nb["name"],
                                  "facet": nb["facet"]})
                conn.execute("INSERT OR IGNORE INTO work_trait(work_id, trait_id, weight) VALUES (?,?,0.8)", (wid, nb_tid))
            if dry_run:
                continue
            sid = conn.execute(
                """INSERT INTO suggestion(user_id, work_id, board_id, run_id, reason, score, is_new_branch,
                                          new_branch_trait_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(user_id, work_id) DO NOTHING RETURNING suggestion_id""",
                (user_id, wid, board["board_id"], run_id, str(idea["reason"]).strip()[:400], round(score, 3),
                 int(nb_tid is not None), nb_tid, now)).fetchone()
            if sid is None:
                continue
            for t in dict.fromkeys(because):
                conn.execute("INSERT OR IGNORE INTO suggestion_trait VALUES (?,?)", (sid[0], t))
            for e in idea["because_entries"][:4]:
                conn.execute("INSERT OR IGNORE INTO suggestion_source VALUES (?,?)", (sid[0], e))
            stats["kept"] += 1
        stats["drop_rate"] = round(len(stats["unmatched"]) / max(1, stats["returned"]), 2)
        conn.execute("UPDATE rec_run SET status = 'done', stats = ?, finished_at = ? WHERE run_id = ?",
                     (json.dumps(stats), now_utc(), run_id))
        stats["run_id"] = run_id
        return stats
    except Exception as e:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        stats["error"] = f"{type(e).__name__}: {e}"
        conn.execute("UPDATE rec_run SET status = 'failed', stats = ?, finished_at = ? WHERE run_id = ?",
                     (json.dumps(stats), now_utc(), run_id))
        if isinstance(e, llm.LLMError):
            raise jobs.PermanentError(str(e)) from e   # don't spend two more expensive calls on a retry
        raise


@jobs.handler("recommend")
def job_recommend(conn: sqlite3.Connection, s: Settings, payload: dict, user_id: int | None) -> dict:
    if user_id is None:
        raise jobs.PermanentError("recommend job without a user")
    try:
        return run(conn, s, user_id, payload)
    except jobs.PermanentError:
        raise
    except Exception as e:
        # A retry would pay for another recommendation call; fail once and let the user re-run.
        raise jobs.PermanentError(f"{type(e).__name__}: {e}") from e
