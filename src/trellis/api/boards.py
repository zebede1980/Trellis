from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from trellis import boards
from trellis.api.deps import current_user, get_conn
from trellis.db import now_utc

router = APIRouter(prefix="/api/boards")

Kind = Literal["book", "film", "tv", "game", "music", "custom"]


class BoardIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    kind: Kind
    custom_hint: str | None = Field(default=None, max_length=200)
    colour: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class BoardPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    custom_hint: str | None = Field(default=None, max_length=200)
    colour: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class Reorder(BaseModel):
    board_ids: list[int]


BOARD_SQL = """
SELECT b.*,
       (SELECT COUNT(*) FROM entry e WHERE e.board_id = b.board_id AND e.state = 'done') AS n_done,
       (SELECT COUNT(*) FROM entry e WHERE e.board_id = b.board_id AND e.state = 'want') AS n_want,
       (SELECT w.cover_url FROM entry e JOIN work w ON w.work_id = e.work_id
         WHERE e.board_id = b.board_id AND w.cover_url IS NOT NULL ORDER BY e.updated_at DESC LIMIT 1) AS cover_url
FROM board b WHERE b.user_id = ?
"""


def board_out(r) -> dict:
    d = {k: r[k] for k in ("board_id", "name", "kind", "custom_hint", "colour", "sort_order")}
    keys = r.keys()
    for k in ("n_done", "n_want", "cover_url"):
        if k in keys:
            d[k] = r[k]
    return d


@router.get("")
def list_boards(user=Depends(current_user), conn=Depends(get_conn)):
    rows = conn.execute(BOARD_SQL + " ORDER BY b.sort_order, b.board_id", (user["user_id"],)).fetchall()
    return [board_out(r) for r in rows]


@router.post("", status_code=201)
def create_board(body: BoardIn, user=Depends(current_user), conn=Depends(get_conn)):
    uid = user["user_id"]
    if body.kind == "custom" and not (body.custom_hint or "").strip():
        raise HTTPException(400, "Custom boards need a short description, e.g. 'board games'.")
    nxt = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM board WHERE user_id = ?", (uid,)).fetchone()[0]
    cur = conn.execute(
        "INSERT INTO board(user_id, name, kind, custom_hint, colour, sort_order, created_at) VALUES (?,?,?,?,?,?,?)",
        (uid, body.name.strip(), body.kind, (body.custom_hint or "").strip() or None,
         body.colour or boards.pick_colour(conn, uid, body.kind), nxt, now_utc()))
    return board_out(boards.get(conn, uid, cur.lastrowid))


@router.get("/{board_id}")
def get_board(board_id: int, user=Depends(current_user), conn=Depends(get_conn)):
    r = conn.execute(BOARD_SQL + " AND b.board_id = ?", (user["user_id"], board_id)).fetchone()
    if r is None:
        raise HTTPException(404)
    return board_out(r)


@router.patch("/{board_id}")
def patch_board(board_id: int, body: BoardPatch, user=Depends(current_user), conn=Depends(get_conn)):
    if boards.get(conn, user["user_id"], board_id) is None:
        raise HTTPException(404)
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes:
        changes["name"] = changes["name"].strip()
    for col, val in changes.items():
        conn.execute(f"UPDATE board SET {col} = ? WHERE board_id = ? AND user_id = ?",
                     (val, board_id, user["user_id"]))
    return board_out(boards.get(conn, user["user_id"], board_id))


@router.delete("/{board_id}")
def delete_board(board_id: int, user=Depends(current_user), conn=Depends(get_conn)):
    cur = conn.execute("DELETE FROM board WHERE board_id = ? AND user_id = ?", (board_id, user["user_id"]))
    if cur.rowcount == 0:
        raise HTTPException(404)
    return {"ok": True}


@router.post("/reorder")
def reorder(body: Reorder, user=Depends(current_user), conn=Depends(get_conn)):
    uid = user["user_id"]
    mine = {r[0] for r in conn.execute("SELECT board_id FROM board WHERE user_id = ?", (uid,))}
    if set(body.board_ids) != mine or len(body.board_ids) != len(mine):
        raise HTTPException(400, "board_ids must list each of your boards exactly once")
    conn.execute("BEGIN")
    for i, bid in enumerate(body.board_ids):
        conn.execute("UPDATE board SET sort_order = ? WHERE board_id = ? AND user_id = ?", (i, bid, uid))
    conn.execute("COMMIT")
    return {"ok": True}
