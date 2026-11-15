"""The shared `work` table: one row per real-world thing, fetched once for all users."""

import json
import sqlite3

from trellis import catalogue
from trellis.catalogue.base import WorkData
from trellis.config import Settings
from trellis.db import now_utc


def upsert(conn: sqlite3.Connection, kind: str, w: WorkData) -> int:
    row = conn.execute(
        """INSERT INTO work(kind, source, source_id, title, creators, year, cover_url, summary, url, raw_tags,
                            verified, fetched_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(source, source_id) DO UPDATE SET
             title = excluded.title, creators = excluded.creators, year = excluded.year,
             cover_url = COALESCE(excluded.cover_url, work.cover_url), summary = COALESCE(excluded.summary, work.summary),
             url = COALESCE(excluded.url, work.url), raw_tags = excluded.raw_tags, fetched_at = excluded.fetched_at
           RETURNING work_id""",
        (kind, w.source, w.source_id, w.title, json.dumps(w.creators), w.year, w.cover_url, w.summary, w.url,
         json.dumps(w.raw_tags), int(w.verified), now_utc())).fetchone()
    return row[0]


def find(conn: sqlite3.Connection, source: str, source_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM work WHERE source = ? AND source_id = ?", (source, source_id)).fetchone()


def get_or_fetch(conn: sqlite3.Connection, s: Settings, kind: str, source: str, source_id: str) -> int:
    """work_id for a catalogue record, fetching it from the provider the first time anyone adds it."""
    existing = find(conn, source, source_id)
    if existing is not None:
        return existing["work_id"]
    p = catalogue.provider(kind, source, s)
    if p is None:
        raise catalogue.ProviderError(f"{source} is not a catalogue for {kind} boards")
    return upsert(conn, kind, p.fetch(source_id))


def add_manual(conn: sqlite3.Connection, kind: str, title: str, creators: list[str], year: int | None,
               url: str | None = None, summary: str | None = None, source: str = "manual",
               source_id: str | None = None, verified: bool = False) -> int:
    """A work with no catalogue record (custom boards). Keyed by normalised title + year so two users typing the
    same thing share one row."""
    from trellis.match import norm_title

    sid = source_id or f"{kind}:{norm_title(title)}:{year or ''}"
    existing = find(conn, source, sid)
    if existing is not None:
        return existing["work_id"]
    return upsert(conn, kind, WorkData(source=source, source_id=sid, title=title.strip(), creators=creators,
                                       year=year, url=url, summary=summary, verified=verified))


def work_out(r) -> dict:
    return {"work_id": r["work_id"], "kind": r["kind"], "source": r["source"], "source_id": r["source_id"],
            "title": r["title"], "creators": json.loads(r["creators"] or "[]"), "year": r["year"],
            "cover_url": r["cover_url"], "summary": r["summary"], "url": r["url"], "verified": bool(r["verified"]),
            "tagged": r["tagged_at"] is not None}
