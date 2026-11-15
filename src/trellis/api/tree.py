from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from trellis import taste, traits
from trellis.api.deps import current_user, get_conn

router = APIRouter(prefix="/api")


@router.get("/tree")
def get_tree(group: Literal["theme", "board"] = "theme", user=Depends(current_user), conn=Depends(get_conn)):
    return taste.tree(conn, user["user_id"], group)


@router.get("/themes")
def my_themes(user=Depends(current_user), conn=Depends(get_conn)):
    """The user's themes by affinity (traits on at least one of their entries)."""
    aff = taste.affinity(conn, user["user_id"])
    rows = conn.execute(
        """SELECT t.trait_id, t.name, t.facet, COUNT(DISTINCT e.entry_id) AS n
           FROM entry e JOIN work_trait wt ON wt.work_id = e.work_id JOIN trait t ON t.trait_id = wt.trait_id
           WHERE e.user_id = ? GROUP BY t.trait_id""", (user["user_id"],)).fetchall()
    out = [dict(r, affinity=(aff.get(r["trait_id"]) or {}).get("affinity") or 0.0) for r in rows]
    return sorted(out, key=lambda t: (-t["affinity"], -t["n"], t["name"]))


@router.get("/themes/{trait_id}")
def theme(trait_id: int, user=Depends(current_user), conn=Depends(get_conn)):
    uid = user["user_id"]
    trait_id = traits.canonical(conn, trait_id)
    t = conn.execute("SELECT trait_id, slug, name, facet, description FROM trait WHERE trait_id = ?",
                     (trait_id,)).fetchone()
    if t is None:
        raise HTTPException(404)
    entries = [dict(taste.entry_card(r), weight=r["weight"]) for r in conn.execute(
        taste.ENTRIES_SQL.replace("WHERE e.user_id = ?",
                                  "JOIN work_trait wt ON wt.work_id = e.work_id AND wt.trait_id = ? WHERE e.user_id = ?")
        .replace("SELECT e.entry_id,", "SELECT wt.weight, e.entry_id,") + " ORDER BY e.rating DESC NULLS LAST, wt.weight DESC",
        (trait_id, uid))]
    sugg = [taste.suggestion_card(r) for r in conn.execute(
        taste.SUGGESTIONS_SQL + """ AND (g.new_branch_trait_id = ? OR EXISTS (
            SELECT 1 FROM suggestion_trait st WHERE st.suggestion_id = g.suggestion_id AND st.trait_id = ?))
            ORDER BY g.score DESC""", (uid, trait_id, trait_id))]
    related = [dict(r) for r in conn.execute(
        """SELECT t2.trait_id, t2.name, t2.facet, COUNT(*) AS n
           FROM entry e JOIN work_trait a ON a.work_id = e.work_id AND a.trait_id = ?
           JOIN work_trait b ON b.work_id = e.work_id AND b.trait_id != a.trait_id
           JOIN trait t2 ON t2.trait_id = b.trait_id
           WHERE e.user_id = ? GROUP BY t2.trait_id ORDER BY n DESC, t2.name LIMIT 8""", (trait_id, uid))]
    a = taste.affinity(conn, uid).get(trait_id) or {}
    return {**dict(t), "affinity": a.get("affinity") or 0.0, "entries": entries, "suggestions": sugg,
            "related": related}
