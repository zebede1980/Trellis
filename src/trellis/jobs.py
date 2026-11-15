"""A job queue in SQLite, worked by one daemon thread inside the web process.

Claiming uses BEGIN IMMEDIATE so only one claimer can win a row even if a second process ever appears. Jobs that
were `running` when the process died are re-queued on startup. Each job gets up to MAX_ATTEMPTS tries.
"""

import json
import logging
import sqlite3
import threading
import traceback
from collections.abc import Callable

from trellis import db
from trellis.config import Settings
from trellis.db import now_utc

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
HANDLERS: dict[str, Callable[[sqlite3.Connection, Settings, dict, int | None], dict | None]] = {}
_wake = threading.Event()


def handler(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


def enqueue(conn: sqlite3.Connection, kind: str, payload: dict, user_id: int | None = None) -> int:
    cur = conn.execute("INSERT INTO job(user_id, kind, payload, created_at) VALUES (?, ?, ?, ?)",
                       (user_id, kind, json.dumps(payload), now_utc()))
    _wake.set()
    return cur.lastrowid


def ensure_tagged(conn: sqlite3.Connection, work_id: int, user_id: int | None = None) -> int | None:
    """Queue a tagging pass if this work has no themes yet and none is already queued."""
    w = conn.execute("SELECT tagged_at FROM work WHERE work_id = ?", (work_id,)).fetchone()
    if w is None or w["tagged_at"] is not None:
        return None
    queued = conn.execute("SELECT job_id FROM job WHERE kind = 'tag' AND status = 'queued' LIMIT 1").fetchone()
    return queued[0] if queued else enqueue(conn, "tag", {}, user_id)


def claim(conn: sqlite3.Connection) -> sqlite3.Row | None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT * FROM job WHERE status = 'queued' ORDER BY job_id LIMIT 1").fetchone()
        if row is not None:
            conn.execute("UPDATE job SET status = 'running', started_at = ?, attempts = attempts + 1 WHERE job_id = ?",
                         (now_utc(), row["job_id"]))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return row


def run_one(conn: sqlite3.Connection, s: Settings) -> bool:
    """Claim and run one job. Returns False when the queue is empty."""
    job = claim(conn)
    if job is None:
        return False
    fn = HANDLERS.get(job["kind"])
    try:
        if fn is None:
            raise RuntimeError(f"no handler for job kind {job['kind']!r}")
        result = fn(conn, s, json.loads(job["payload"]), job["user_id"])
        conn.execute("UPDATE job SET status = 'done', finished_at = ?, result = ?, error = NULL WHERE job_id = ?",
                     (now_utc(), json.dumps(result) if result is not None else None, job["job_id"]))
    except Exception as e:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        log.warning("job %s (%s) failed: %s", job["job_id"], job["kind"], e)
        attempts = job["attempts"] + 1
        final = attempts >= MAX_ATTEMPTS or isinstance(e, PermanentError)
        conn.execute("UPDATE job SET status = ?, error = ?, finished_at = ? WHERE job_id = ?",
                     ("failed" if final else "queued", f"{type(e).__name__}: {e}"[:2000],
                      now_utc() if final else None, job["job_id"]))
        if not final:
            log.debug(traceback.format_exc())
    return True


def run_pending(conn: sqlite3.Connection, s: Settings, limit: int = 100) -> int:
    """Run queued jobs synchronously (tests and the CLI)."""
    n = 0
    while n < limit and run_one(conn, s):
        n += 1
    return n


class PermanentError(Exception):
    """A failure that retrying will not fix (bad payload, missing key)."""


def requeue_stale(conn: sqlite3.Connection) -> int:
    return conn.execute("UPDATE job SET status = 'queued' WHERE status = 'running'").rowcount


class Worker:
    def __init__(self, s: Settings):
        self.s = s
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, name="trellis-worker", daemon=True)

    def start(self) -> None:
        conn = db.connect(self.s.db_path)
        n = requeue_stale(conn)
        # pick up works whose tagging failed earlier (one batch; the daily LLM cap bounds any repeat failures)
        stale = conn.execute("""SELECT w.work_id FROM work w WHERE w.tagged_at IS NULL
                                AND EXISTS (SELECT 1 FROM entry e WHERE e.work_id = w.work_id) LIMIT 1""").fetchone()
        if stale:
            ensure_tagged(conn, stale[0])
        conn.close()
        if n:
            log.info("re-queued %d interrupted jobs", n)
        self.thread.start()

    def stop(self) -> None:
        self._stop.set()
        _wake.set()
        self.thread.join(timeout=10)

    def _loop(self) -> None:
        _load_handlers()
        conn = db.connect(self.s.db_path)
        while not self._stop.is_set():
            try:
                busy = run_one(conn, self.s)
            except Exception:
                log.exception("worker loop error")
                busy = False
            if not busy:
                _wake.wait(timeout=5)
                _wake.clear()
        conn.close()


def _load_handlers() -> None:
    # Importing registers the handlers via @handler.
    from trellis import recommend, traits  # noqa: F401
    from trellis.api import admin  # noqa: F401


def job_out(r: sqlite3.Row) -> dict:
    return {"job_id": r["job_id"], "kind": r["kind"], "status": r["status"], "attempts": r["attempts"],
            "error": r["error"], "result": json.loads(r["result"]) if r["result"] else None,
            "created_at": r["created_at"], "finished_at": r["finished_at"]}
