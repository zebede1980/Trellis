import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator

from trellis import boards, catalogue, works
from trellis.api.deps import current_user, get_conn
from trellis.db import now_utc

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

ENTRY_SQL = """
SELECT e.*, w.title, w.creators, w.year, w.cover_url, w.summary, w.url, w.source, w.source_id, w.verified, w.kind,
       w.tagged_at, b.name AS board_name, b.colour AS board_colour
FROM entry e JOIN work w ON w.work_id = e.work_id JOIN board b ON b.board_id = e.board_id
WHERE e.user_id = ?
"""


def entry_out(r, traits: list[dict] | None = None) -> dict:
    d = {k: r[k] for k in ("entry_id", "board_id", "work_id", "state", "rating", "note", "consumed_on", "created_at",
                           "updated_at", "title", "year", "cover_url", "url", "source", "kind", "board_name",
                           "board_colour")}
    d["creators"] = json.loads(r["creators"] or "[]")
    d["verified"] = bool(r["verified"])
    d["tagged"] = r["tagged_at"] is not None
    if "summary" in r.keys():
        d["summary"] = r["summary"]
    if traits is not None:
        d["traits"] = traits
    return d


def entry_traits(conn, work_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT t.trait_id, t.slug, t.name, t.facet, wt.weight FROM work_trait wt JOIN trait t ON t.trait_id = wt.trait_id
           WHERE wt.work_id = ? ORDER BY wt.weight DESC, t.name""", (work_id,)).fetchall()
    return [dict(r) for r in rows]


def get_entry(conn, user_id: int, entry_id: int):
    return conn.execute(ENTRY_SQL + " AND e.entry_id = ?", (user_id, entry_id)).fetchone()


class Manual(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    creators: list[str] = Field(default_factory=list, max_length=5)
    year: int | None = Field(default=None, ge=0, le=2100)
    url: str | None = Field(default=None, max_length=500)


class EntryIn(BaseModel):
    board_id: int
    source: str | None = None
    source_id: str | None = None
    manual: Manual | None = None
    state: Literal["done", "want"] = "done"
    rating: int | None = Field(default=None, ge=1, le=5)
    note: str | None = Field(default=None, max_length=4000)
    consumed_on: str | None = Field(default=None, pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$")

    @model_validator(mode="after")
    def _one_source(self):
        if bool(self.source and self.source_id) == bool(self.manual):
            raise ValueError("give either source + source_id, or manual")
        if self.state == "want":
            self.rating = None
        return self


class EntryPatch(BaseModel):
    state: Literal["done", "want"] | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    note: str | None = Field(default=None, max_length=4000)
    consumed_on: str | None = Field(default=None, pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$")
    board_id: int | None = None


@router.get("/lookup")
def lookup(request: Request, board_id: int, q: str = Query(min_length=1, max_length=200),
           user=Depends(current_user), conn=Depends(get_conn)):
    b = boards.get(conn, user["user_id"], board_id)
    if b is None:
        raise HTTPException(404)
    s = request.app.state.settings
    try:
        cands = catalogue.search(b["kind"], q.strip(), s, hint=b["custom_hint"])
    except catalogue.ProviderError as e:
        raise HTTPException(502, str(e))
    have = {(r["source"], r["source_id"]): (r["entry_id"], r["state"]) for r in conn.execute(
        "SELECT w.source, w.source_id, e.entry_id, e.state FROM entry e JOIN work w ON w.work_id = e.work_id "
        "WHERE e.user_id = ?", (user["user_id"],))}
    out = []
    for c in cands:
        d = c.to_dict()
        hit = have.get((c.source, c.source_id))
        d["have"] = {"entry_id": hit[0], "state": hit[1]} if hit else None
        out.append(d)
    return out


@router.post("/entries", status_code=201)
def create_entry(body: EntryIn, request: Request, user=Depends(current_user), conn=Depends(get_conn)):
    from trellis import jobs

    uid = user["user_id"]
    b = boards.get(conn, uid, body.board_id)
    if b is None:
        raise HTTPException(404, "no such board")
    s = request.app.state.settings
    try:
        if body.manual:
            m = body.manual
            work_id = works.add_manual(conn, b["kind"], m.title, [c.strip() for c in m.creators if c.strip()], m.year,
                                       url=m.url if (m.url or "").startswith(("http://", "https://")) else None)
        else:
            work_id = works.get_or_fetch(conn, s, b["kind"], body.source, body.source_id)
    except catalogue.ProviderError as e:
        raise HTTPException(502, str(e))
    dup = conn.execute("SELECT entry_id FROM entry WHERE user_id = ? AND work_id = ?", (uid, work_id)).fetchone()
    if dup:
        raise HTTPException(409, {"message": "Already on your boards", "entry_id": dup[0]})
    now = now_utc()
    cur = conn.execute(
        """INSERT INTO entry(user_id, board_id, work_id, state, rating, note, consumed_on, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (uid, b["board_id"], work_id, body.state, body.rating, (body.note or "").strip() or None, body.consumed_on,
         now, now))
    jobs.ensure_tagged(conn, work_id, uid)
    # Adding a suggested thing yourself closes the suggestion.
    conn.execute("UPDATE suggestion SET status = ?, acted_at = ? WHERE user_id = ? AND work_id = ? AND status = 'new'",
                 (body.state, now, uid, work_id))
    return entry_out(get_entry(conn, uid, cur.lastrowid), entry_traits(conn, work_id))


@router.get("/entries/{entry_id}")
def read_entry(entry_id: int, user=Depends(current_user), conn=Depends(get_conn)):
    r = get_entry(conn, user["user_id"], entry_id)
    if r is None:
        raise HTTPException(404)
    return entry_out(r, entry_traits(conn, r["work_id"]))


@router.patch("/entries/{entry_id}")
def patch_entry(entry_id: int, body: EntryPatch, user=Depends(current_user), conn=Depends(get_conn)):
    uid = user["user_id"]
    r = get_entry(conn, uid, entry_id)
    if r is None:
        raise HTTPException(404)
    ch = body.model_dump(exclude_unset=True)
    if "board_id" in ch:
        nb = boards.get(conn, uid, ch["board_id"])
        if nb is None:
            raise HTTPException(404, "no such board")
        if nb["kind"] != r["kind"] and not (nb["kind"] == "custom" and r["kind"] == "custom"):
            raise HTTPException(400, "Can only move to a board of the same kind")
    if ch.get("state") == "want":
        ch["rating"] = None
    if "note" in ch:
        ch["note"] = (ch["note"] or "").strip() or None
    for col, val in ch.items():
        conn.execute(f"UPDATE entry SET {col} = ? WHERE entry_id = ? AND user_id = ?", (val, entry_id, uid))
    conn.execute("UPDATE entry SET updated_at = ? WHERE entry_id = ? AND user_id = ?", (now_utc(), entry_id, uid))
    r = get_entry(conn, uid, entry_id)
    return entry_out(r, entry_traits(conn, r["work_id"]))


@router.delete("/entries/{entry_id}")
def delete_entry(entry_id: int, user=Depends(current_user), conn=Depends(get_conn)):
    cur = conn.execute("DELETE FROM entry WHERE entry_id = ? AND user_id = ?", (entry_id, user["user_id"]))
    if cur.rowcount == 0:
        raise HTTPException(404)
    return {"ok": True}


SORTS = {"recent": "e.updated_at DESC", "rating": "e.rating DESC NULLS LAST, e.updated_at DESC",
         "title": "w.title COLLATE NOCASE", "year": "w.year DESC NULLS LAST, w.title COLLATE NOCASE"}


@router.get("/boards/{board_id}/entries")
def board_entries(board_id: int, state: Literal["done", "want"] | None = None,
                  sort: Literal["recent", "rating", "title", "year"] = "recent",
                  user=Depends(current_user), conn=Depends(get_conn)):
    uid = user["user_id"]
    if boards.get(conn, uid, board_id) is None:
        raise HTTPException(404)
    sql = ENTRY_SQL + " AND e.board_id = ?"
    args: list = [uid, board_id]
    if state:
        sql += " AND e.state = ?"
        args.append(state)
    rows = conn.execute(sql + f" ORDER BY {SORTS[sort]}", args).fetchall()
    return [entry_out(r) for r in rows]
