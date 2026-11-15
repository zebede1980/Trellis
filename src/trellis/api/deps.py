import sqlite3
from collections.abc import Iterator

from fastapi import HTTPException, Request

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
