import sqlite3

from trellis.db import now_utc

KINDS = ("book", "film", "tv", "game", "music", "custom")
KIND_LABEL = {"book": "Books", "film": "Films", "tv": "TV", "game": "Games", "music": "Music", "custom": "Custom"}
DEFAULT_COLOUR = {"book": "#c2703d", "film": "#b8435a", "tv": "#6a5acd", "game": "#2e8b57", "music": "#d4a017",
                  "custom": "#3d8fb8"}
CUSTOM_COLOURS = ["#3d8fb8", "#8b5a2b", "#c05299", "#5f7f2f", "#7a6fb0", "#b05a3c"]


def create_defaults(conn: sqlite3.Connection, user_id: int) -> None:
    now = now_utc()
    conn.executemany(
        "INSERT INTO board(user_id, name, kind, colour, sort_order, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        [(user_id, KIND_LABEL[k], k, DEFAULT_COLOUR[k], i, now) for i, k in enumerate(KINDS[:-1])])


def get(conn: sqlite3.Connection, user_id: int, board_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM board WHERE board_id = ? AND user_id = ?", (board_id, user_id)).fetchone()


def pick_colour(conn: sqlite3.Connection, user_id: int, kind: str) -> str:
    if kind != "custom":
        return DEFAULT_COLOUR[kind]
    used = {r[0] for r in conn.execute("SELECT colour FROM board WHERE user_id = ?", (user_id,))}
    return next((c for c in CUSTOM_COLOURS if c not in used), CUSTOM_COLOURS[0])
