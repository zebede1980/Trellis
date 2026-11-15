from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from trellis import jobs, recommend, taste
from trellis.api.deps import current_user, get_conn
from trellis.db import now_utc

router = APIRouter(prefix="/api")


class RecommendIn(BaseModel):
    mode: Literal["all", "trait", "board", "explore"] = "all"
    trait_id: int | None = None
    board_id: int | None = None

    @model_validator(mode="after")
    def _needs(self):
        if self.mode == "trait" and not self.trait_id:
            raise ValueError("trait mode needs trait_id")
        if self.mode == "board" and not self.board_id:
            raise ValueError("board mode needs board_id")
        return self


class ActIn(BaseModel):
    action: Literal["want", "dismiss", "done"]
    reason: Literal["not for me", "too similar", "already tried it"] | None = None
    rating: int | None = Field(default=None, ge=1, le=5)


@router.post("/recommend", status_code=202)
def start_recommend(body: RecommendIn, request: Request, user=Depends(current_user), conn=Depends(get_conn)):
    uid = user["user_id"]
    if body.board_id is not None and conn.execute("SELECT 1 FROM board WHERE board_id = ? AND user_id = ?",
                                                  (body.board_id, uid)).fetchone() is None:
        raise HTTPException(404, "no such board")
    if body.trait_id is not None and conn.execute("SELECT 1 FROM trait WHERE trait_id = ?",
                                                  (body.trait_id,)).fetchone() is None:
        raise HTTPException(404, "no such theme")
    if conn.execute("SELECT COUNT(*) FROM entry WHERE user_id = ? AND rating IS NOT NULL", (uid,)).fetchone()[0] < 3:
        raise HTTPException(400, "Rate at least 3 things first, so there's some taste to go on.")
    try:
        job_id = recommend.start(conn, request.app.state.settings, uid, body.model_dump(exclude_none=True))
    except recommend.CapReached as e:
        raise HTTPException(429, str(e))
    return {"job_id": job_id}


@router.get("/recommend/status")
def recommend_status(request: Request, user=Depends(current_user), conn=Depends(get_conn)):
    uid = user["user_id"]
    active = conn.execute("SELECT * FROM job WHERE user_id = ? AND kind = 'recommend' AND status IN ('queued','running') "
                          "ORDER BY job_id DESC LIMIT 1", (uid,)).fetchone()
    last = conn.execute("SELECT * FROM job WHERE user_id = ? AND kind = 'recommend' ORDER BY job_id DESC LIMIT 1",
                        (uid,)).fetchone()
    return {"runs_today": recommend.runs_today(conn, uid), "cap": request.app.state.settings.rec_runs_per_day,
            "active": jobs.job_out(active) if active else None, "last": jobs.job_out(last) if last else None}


@router.get("/jobs/{job_id}")
def get_job(job_id: int, user=Depends(current_user), conn=Depends(get_conn)):
    r = conn.execute("SELECT * FROM job WHERE job_id = ? AND user_id = ?", (job_id, user["user_id"])).fetchone()
    if r is None:
        raise HTTPException(404)
    return jobs.job_out(r)


def _decorate(conn, cards: list[dict]) -> list[dict]:
    if not cards:
        return cards
    ids = [c["suggestion_id"] for c in cards]
    q = ",".join("?" * len(ids))
    tr: dict[int, list] = {}
    for r in conn.execute(f"""SELECT st.suggestion_id, t.trait_id, t.name, t.facet FROM suggestion_trait st
                              JOIN trait t ON t.trait_id = st.trait_id WHERE st.suggestion_id IN ({q})""", ids):
        tr.setdefault(r[0], []).append({"trait_id": r[1], "name": r[2], "facet": r[3]})
    src: dict[int, list] = {}
    for r in conn.execute(f"""SELECT ss.suggestion_id, e.entry_id, w.title FROM suggestion_source ss
                              JOIN entry e ON e.entry_id = ss.entry_id JOIN work w ON w.work_id = e.work_id
                              WHERE ss.suggestion_id IN ({q})""", ids):
        src.setdefault(r[0], []).append({"entry_id": r[1], "title": r[2]})
    nb = {r[0]: {"trait_id": r[1], "name": r[2], "facet": r[3], "description": r[4]} for r in conn.execute(
        f"""SELECT g.suggestion_id, t.trait_id, t.name, t.facet, t.description FROM suggestion g
            JOIN trait t ON t.trait_id = g.new_branch_trait_id WHERE g.suggestion_id IN ({q})""", ids)}
    for c in cards:
        c["traits"] = tr.get(c["suggestion_id"], [])
        c["sources"] = src.get(c["suggestion_id"], [])
        c["new_branch"] = nb.get(c["suggestion_id"])
    return cards


@router.get("/suggestions")
def list_suggestions(status: Literal["new", "want", "dismissed", "done"] = "new", board_id: int | None = None,
                     trait_id: int | None = None, user=Depends(current_user), conn=Depends(get_conn)):
    sql = taste.SUGGESTIONS_SQL.replace("AND g.status = 'new'", "AND g.status = ?")
    args: list = [user["user_id"], status]
    if board_id:
        sql += " AND g.board_id = ?"
        args.append(board_id)
    if trait_id:
        sql += (" AND (g.new_branch_trait_id = ? OR EXISTS (SELECT 1 FROM suggestion_trait st "
                "WHERE st.suggestion_id = g.suggestion_id AND st.trait_id = ?))")
        args += [trait_id, trait_id]
    rows = conn.execute(sql + " ORDER BY g.is_new_branch, g.score DESC, g.suggestion_id DESC LIMIT 200", args).fetchall()
    return _decorate(conn, [taste.suggestion_card(r) for r in rows])


@router.post("/suggestions/{suggestion_id}/act")
def act(suggestion_id: int, body: ActIn, user=Depends(current_user), conn=Depends(get_conn)):
    uid = user["user_id"]
    g = conn.execute("SELECT * FROM suggestion WHERE suggestion_id = ? AND user_id = ?", (suggestion_id, uid)).fetchone()
    if g is None:
        raise HTTPException(404)
    now = now_utc()
    entry_id = None
    if body.action in ("want", "done"):
        if body.action == "done" and body.rating is None:
            raise HTTPException(400, "Give it a rating")
        existing = conn.execute("SELECT entry_id FROM entry WHERE user_id = ? AND work_id = ?", (uid, g["work_id"])).fetchone()
        if existing:
            entry_id = existing[0]
            conn.execute("UPDATE entry SET state = ?, rating = ?, updated_at = ? WHERE entry_id = ?",
                         (body.action, body.rating if body.action == "done" else None, now, entry_id))
        else:
            entry_id = conn.execute(
                """INSERT INTO entry(user_id, board_id, work_id, state, rating, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (uid, g["board_id"], g["work_id"], body.action, body.rating if body.action == "done" else None,
                 now, now)).lastrowid
        jobs.ensure_tagged(conn, g["work_id"], uid)
        conn.execute("UPDATE suggestion SET status = ?, acted_at = ? WHERE suggestion_id = ?",
                     (body.action, now, suggestion_id))
    else:
        conn.execute("UPDATE suggestion SET status = 'dismissed', dismiss_reason = ?, acted_at = ? WHERE suggestion_id = ?",
                     (body.reason, now, suggestion_id))
    return {"ok": True, "entry_id": entry_id}
