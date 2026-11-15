import sqlite3
from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request

from trellis import db


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    conn = db.connect(request.app.state.settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


def require_xhr(request: Request) -> None:
    """CSRF guard for state-changing routes: browsers will not add this header to a cross-site form post."""
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-requested-with") != "trellis":
        raise HTTPException(403, "missing X-Requested-With header")


def current_user(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> sqlite3.Row:
    uid = request.session.get("uid")
    row = conn.execute("SELECT * FROM app_user WHERE user_id = ? AND disabled = 0", (uid,)).fetchone() if uid else None
    if row is None:
        request.session.clear()
        raise HTTPException(401, "not logged in")
    return row


def admin_user(user: sqlite3.Row = Depends(current_user)) -> sqlite3.Row:
    if not user["is_admin"]:
        raise HTTPException(403, "admin only")
    return user
