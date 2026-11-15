"""Password hashing and login checks (ported from rugby-matchup).

scrypt from the standard library; the session is a signed cookie, so there is no session table.
"""

import base64
import hashlib
import hmac
import os
import sqlite3
import time
from collections import defaultdict, deque

from trellis.db import now_utc

_N, _R, _P = 2**14, 8, 1
MIN_PASSWORD = 8


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, dk = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                             dklen=len(base64.b64decode(dk)))
        return hmac.compare_digest(got, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


def norm_username(username: str) -> str:
    return username.strip().lower()


def create_user(conn: sqlite3.Connection, username: str, pw: str, *, is_admin: bool = False,
                display_name: str | None = None) -> int:
    from trellis import boards

    if len(pw) < MIN_PASSWORD:
        raise ValueError(f"password must be at least {MIN_PASSWORD} characters")
    name = norm_username(username)
    if not name or not name.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise ValueError("username may only contain letters, digits, '-', '_' and '.'")
    cur = conn.execute(
        "INSERT INTO app_user(username, pw_hash, display_name, is_admin, created_at) VALUES (?, ?, ?, ?, ?)",
        (name, hash_password(pw), display_name or username.strip(), int(is_admin), now_utc()))
    boards.create_defaults(conn, cur.lastrowid)
    return cur.lastrowid


def set_password(conn: sqlite3.Connection, user_id: int, pw: str) -> None:
    if len(pw) < MIN_PASSWORD:
        raise ValueError(f"password must be at least {MIN_PASSWORD} characters")
    conn.execute("UPDATE app_user SET pw_hash = ? WHERE user_id = ?", (hash_password(pw), user_id))


_DUMMY = hash_password("timing-equaliser")


def check_login(conn: sqlite3.Connection, username: str, pw: str) -> sqlite3.Row | None:
    row = conn.execute("SELECT * FROM app_user WHERE username = ?", (norm_username(username),)).fetchone()
    # verify against a dummy hash for unknown users so response time doesn't reveal valid usernames
    ok = verify_password(pw, row["pw_hash"] if row else _DUMMY)
    return row if ok and row is not None and not row["disabled"] else None


class Throttle:
    """At most `limit` failed logins per IP per `window` seconds."""

    def __init__(self, limit: int = 5, window: int = 900):
        self.limit, self.window = limit, window
        self.fails: dict[str, deque] = defaultdict(deque)

    def blocked(self, ip: str) -> bool:
        q = self.fails[ip]
        while q and q[0] < time.monotonic() - self.window:
            q.popleft()
        return len(q) >= self.limit

    def fail(self, ip: str) -> None:
        self.fails[ip].append(time.monotonic())

    def clear(self, ip: str) -> None:
        self.fails.pop(ip, None)
