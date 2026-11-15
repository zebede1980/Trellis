"""Shared types for catalogue providers.

Every provider offers `search(q) -> list[Candidate]` (cheap, for the add sheet) and `fetch(source_id) -> WorkData`
(authoritative details, stored in `work`). The user picks from the candidates, so a human does the disambiguation;
the server then re-fetches by id, so a client can never write made-up titles into the shared `work` table.
"""

import re
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Protocol

import httpx

from trellis.config import USER_AGENT

# Tests swap this for an httpx.MockTransport.
TRANSPORT: httpx.BaseTransport | None = None


def client(**kw) -> httpx.Client:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json", **kw.pop("headers", {})}
    return httpx.Client(transport=TRANSPORT, headers=headers, timeout=kw.pop("timeout", 15),
                        follow_redirects=True, **kw)


@dataclass
class Candidate:
    source: str
    source_id: str
    title: str
    creators: list[str] = field(default_factory=list)
    year: int | None = None
    cover_url: str | None = None
    url: str | None = None
    verified: bool = True
    blurb: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class WorkData(Candidate):
    summary: str | None = None
    raw_tags: list[str] = field(default_factory=list)


class ProviderError(Exception):
    pass


class Provider(Protocol):
    source: str

    def search(self, q: str) -> list[Candidate]: ...

    def fetch(self, source_id: str) -> WorkData: ...


class RateLimit:
    """Minimum interval between requests to one provider, shared by all threads."""

    def __init__(self, interval_s: float):
        self.interval = interval_s
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            gap = self._last + self.interval - time.monotonic()
            if gap > 0:
                time.sleep(gap)
            self._last = time.monotonic()


class TTLCache:
    """Tiny in-process cache for search results, so debounced typing doesn't re-hit rate-limited APIs."""

    def __init__(self, ttl_s: float = 3600, size: int = 300):
        self.ttl, self.size = ttl_s, size
        self._d: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            hit = self._d.get(key)
            if hit and hit[0] > time.monotonic():
                return hit[1]
            self._d.pop(key, None)
            return None

    def put(self, key: str, value) -> None:
        with self._lock:
            if len(self._d) >= self.size:
                self._d.pop(next(iter(self._d)))
            self._d[key] = (time.monotonic() + self.ttl, value)


def year_of(s: str | None) -> int | None:
    m = re.search(r"\b(1[0-9]{3}|20[0-9]{2})\b", s or "")
    return int(m.group(1)) if m else None


def clip(s: str | None, n: int = 1500) -> str | None:
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def dedupe(xs: list[str], limit: int = 30) -> list[str]:
    seen, out = set(), []
    for x in xs:
        k = x.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(x.strip())
    return out[:limit]
