import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from trellis import auth, jobs, llm, traits
from trellis.api.deps import admin_user, current_user, get_conn
from trellis.config import Settings
from trellis.db import now_utc

router = APIRouter(prefix="/api")


# --------------------------------------------------------------------------- export (any user, own data)

@router.get("/export")
def export(user=Depends(current_user), conn=Depends(get_conn)):
    uid = user["user_id"]
    boards = [dict(r) for r in conn.execute(
        "SELECT board_id, name, kind, custom_hint, colour FROM board WHERE user_id = ? ORDER BY sort_order", (uid,))]
    entries = []
    for r in conn.execute(
            """SELECT e.entry_id, e.board_id, e.state, e.rating, e.note, e.consumed_on, e.created_at, e.updated_at,
                      w.work_id, w.kind, w.source, w.source_id, w.title, w.creators, w.year, w.url
               FROM entry e JOIN work w ON w.work_id = e.work_id WHERE e.user_id = ? ORDER BY e.entry_id""", (uid,)):
        d = dict(r)
        d["creators"] = json.loads(d["creators"] or "[]")
        d["themes"] = [x[0] for x in conn.execute(
            "SELECT t.name FROM work_trait wt JOIN trait t ON t.trait_id = wt.trait_id WHERE wt.work_id = ? "
            "ORDER BY wt.weight DESC", (d["work_id"],))]
        entries.append(d)
    sugg = [dict(r) for r in conn.execute(
        """SELECT w.title, w.year, b.name AS board, g.reason, g.status, g.dismiss_reason, g.created_at
           FROM suggestion g JOIN work w ON w.work_id = g.work_id JOIN board b ON b.board_id = g.board_id
           WHERE g.user_id = ? ORDER BY g.suggestion_id""", (uid,))]
    body = {"exported_at": now_utc(), "username": user["username"], "boards": boards, "entries": entries,
            "suggestions": sugg}
    return JSONResponse(body, headers={"Content-Disposition": 'attachment; filename="trellis-export.json"'})


# --------------------------------------------------------------------------- users

class NewUser(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=auth.MIN_PASSWORD, max_length=200)
    display_name: str | None = Field(default=None, max_length=60)
    is_admin: bool = False


class UserPatch(BaseModel):
    password: str | None = Field(default=None, min_length=auth.MIN_PASSWORD, max_length=200)
    disabled: bool | None = None
    is_admin: bool | None = None
    display_name: str | None = Field(default=None, max_length=60)


@router.get("/admin/users")
def users(_=Depends(admin_user), conn=Depends(get_conn)):
    return [dict(r) for r in conn.execute(
        """SELECT u.user_id, u.username, u.display_name, u.is_admin, u.disabled, u.created_at,
                  (SELECT COUNT(*) FROM entry e WHERE e.user_id = u.user_id) AS entries,
                  (SELECT COUNT(*) FROM suggestion g WHERE g.user_id = u.user_id) AS suggestions
           FROM app_user u ORDER BY u.user_id""")]


@router.post("/admin/users", status_code=201)
def add_user(body: NewUser, _=Depends(admin_user), conn=Depends(get_conn)):
    try:
        uid = auth.create_user(conn, body.username, body.password, is_admin=body.is_admin,
                               display_name=body.display_name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "That username is taken")
    return {"user_id": uid}


@router.patch("/admin/users/{user_id}")
def patch_user(user_id: int, body: UserPatch, me=Depends(admin_user), conn=Depends(get_conn)):
    if conn.execute("SELECT 1 FROM app_user WHERE user_id = ?", (user_id,)).fetchone() is None:
        raise HTTPException(404)
    if user_id == me["user_id"] and (body.disabled or body.is_admin is False):
        raise HTTPException(400, "You can't disable or demote yourself")
    if body.password:
        auth.set_password(conn, user_id, body.password)
    for col in ("disabled", "is_admin"):
        val = getattr(body, col)
        if val is not None:
            conn.execute(f"UPDATE app_user SET {col} = ? WHERE user_id = ?", (int(val), user_id))
    if body.display_name is not None:
        conn.execute("UPDATE app_user SET display_name = ? WHERE user_id = ?", (body.display_name.strip(), user_id))
    return {"ok": True}


# --------------------------------------------------------------------------- themes

class ThemePatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    description: str | None = Field(default=None, max_length=300)
    facet: str | None = None


class MergeIn(BaseModel):
    from_id: int
    into_id: int


@router.get("/admin/themes")
def themes(_=Depends(admin_user), conn=Depends(get_conn)):
    return [dict(r) for r in conn.execute(
        """SELECT t.trait_id, t.slug, t.name, t.facet, t.description, t.created_at,
                  (SELECT COUNT(*) FROM work_trait wt WHERE wt.trait_id = t.trait_id) AS works
           FROM trait t WHERE t.merged_into_id IS NULL ORDER BY t.facet, t.name""")]


@router.patch("/admin/themes/{trait_id}")
def patch_theme(trait_id: int, body: ThemePatch, _=Depends(admin_user), conn=Depends(get_conn)):
    if conn.execute("SELECT 1 FROM trait WHERE trait_id = ?", (trait_id,)).fetchone() is None:
        raise HTTPException(404)
    if body.facet is not None and body.facet not in traits.FACETS:
        raise HTTPException(400, f"facet must be one of {traits.FACETS}")
    if body.name:
        name = body.name.strip().lower()
        clash = conn.execute("SELECT trait_id FROM trait WHERE slug = ? AND trait_id != ?",
                             (traits.slugify(name), trait_id)).fetchone()
        if clash:
            raise HTTPException(409, "A theme with that name exists; merge into it instead")
        conn.execute("UPDATE trait SET name = ?, slug = ? WHERE trait_id = ?", (name, traits.slugify(name), trait_id))
    if body.description is not None:
        conn.execute("UPDATE trait SET description = ? WHERE trait_id = ?", (body.description.strip() or None, trait_id))
    if body.facet:
        conn.execute("UPDATE trait SET facet = ? WHERE trait_id = ?", (body.facet, trait_id))
    return {"ok": True}


@router.post("/admin/themes/merge")
def merge(body: MergeIn, _=Depends(admin_user), conn=Depends(get_conn)):
    try:
        traits.merge(conn, body.from_id, body.into_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.post("/admin/themes/suggest-merges", status_code=202)
def suggest_merges(me=Depends(admin_user), conn=Depends(get_conn)):
    return {"job_id": jobs.enqueue(conn, "suggest_merges", {}, me["user_id"])}


MERGE_SYSTEM = """You maintain a controlled vocabulary of themes used to tag books, films, TV, games and music. Find pairs that are near-duplicates or so close that keeping both splits the user's taste in two (e.g. "found family" / "chosen family"). Do not pair themes that are merely related ("grief and loss" vs "mortality" are different).
For each pair say which to keep (the clearer, more reusable name).
Return ONLY JSON: {"pairs": [{"merge": "<slug to fold away>", "into": "<slug to keep>", "why": "short"}]}"""


@jobs.handler("suggest_merges")
def job_suggest_merges(conn: sqlite3.Connection, s: Settings, payload: dict, user_id: int | None) -> dict:
    vocab = [dict(t) for t in traits.vocabulary(conn)]
    slugs = {t["slug"]: t for t in vocab}

    def validate(obj):
        if not isinstance(obj.get("pairs"), list):
            return ["'pairs' must be a list"]
        obj["pairs"] = [p for p in obj["pairs"] if isinstance(p, dict) and p.get("merge") in slugs
                        and p.get("into") in slugs and p["merge"] != p["into"]]
        return []

    try:
        obj = llm.call_json(conn, s, purpose="suggest_merges", model=s.tag_model, user_id=user_id, max_tokens=3000,
                            messages=[{"role": "system", "content": MERGE_SYSTEM},
                                      {"role": "user", "content": json.dumps(
                                          [{"slug": t["slug"], "name": t["name"], "facet": t["facet"]} for t in vocab])}],
                            validate=validate)
    except llm.LLMError as e:
        raise jobs.PermanentError(str(e)) from e
    return {"pairs": [{"from_id": slugs[p["merge"]]["trait_id"], "from": slugs[p["merge"]]["name"],
                       "into_id": slugs[p["into"]]["trait_id"], "into": slugs[p["into"]]["name"],
                       "why": str(p.get("why", ""))[:200]} for p in obj["pairs"]]}


@router.get("/admin/jobs/{job_id}")
def admin_job(job_id: int, _=Depends(admin_user), conn=Depends(get_conn)):
    r = conn.execute("SELECT * FROM job WHERE job_id = ?", (job_id,)).fetchone()
    if r is None:
        raise HTTPException(404)
    return jobs.job_out(r)


# --------------------------------------------------------------------------- AI usage

@router.get("/admin/usage")
def usage(_=Depends(admin_user), conn=Depends(get_conn)):
    by = [dict(r) for r in conn.execute(
        """SELECT COALESCE(u.username, '(system)') AS username, c.purpose, c.model, COUNT(*) AS calls,
                  SUM(c.ok = 0) AS failed, SUM(c.prompt_tokens) AS prompt_tokens,
                  SUM(c.completion_tokens) AS completion_tokens, MAX(c.created_at) AS last
           FROM llm_call c LEFT JOIN app_user u ON u.user_id = c.user_id
           WHERE c.created_at >= date('now', '-30 days')
           GROUP BY u.username, c.purpose, c.model ORDER BY calls DESC""")]
    daily = [dict(r) for r in conn.execute(
        """SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS calls, SUM(ok = 0) AS failed
           FROM llm_call WHERE created_at >= date('now', '-30 days') GROUP BY day ORDER BY day DESC""")]
    return {"by_user_purpose": by, "daily": daily, "calls_today": llm.calls_today(conn)}
