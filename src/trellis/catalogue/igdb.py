"""IGDB (via a Twitch developer app): games. About 4 requests/second; the app token is cached until it expires."""

import threading
import time

from trellis.catalogue.base import Candidate, ProviderError, RateLimit, WorkData, clip, client, dedupe

BASE = "https://api.igdb.com/v4"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
_limit = RateLimit(0.3)
_token_lock = threading.Lock()
_token: dict = {"value": None, "expires": 0.0, "for": None}

FIELDS = ("name, first_release_date, cover.image_id, url, summary, genres.name, themes.name, keywords.name, "
          "involved_companies.developer, involved_companies.company.name")


def _cover(c: dict | None) -> str | None:
    return f"https://images.igdb.com/igdb/image/upload/t_cover_big/{c['image_id']}.jpg" if c and c.get("image_id") else None


def _year(ts) -> int | None:
    return time.gmtime(ts).tm_year if isinstance(ts, (int, float)) else None


class IGDB:
    source = "igdb"

    def __init__(self, client_id: str, client_secret: str):
        self.client_id, self.client_secret = client_id, client_secret

    def _bearer(self) -> str:
        with _token_lock:
            if _token["value"] and _token["for"] == self.client_id and _token["expires"] > time.time() + 60:
                return _token["value"]
            with client() as c:
                r = c.post(TOKEN_URL, params={"client_id": self.client_id, "client_secret": self.client_secret,
                                              "grant_type": "client_credentials"})
            if r.status_code != 200:
                raise ProviderError(f"IGDB token request failed ({r.status_code})")
            d = r.json()
            _token.update(value=d["access_token"], expires=time.time() + d.get("expires_in", 3600), **{"for": self.client_id})
            return _token["value"]

    def _query(self, body: str) -> list[dict]:
        _limit.wait()
        with client(headers={"Client-ID": self.client_id, "Authorization": f"Bearer {self._bearer()}"}) as c:
            r = c.post(f"{BASE}/games", content=body)
        if r.status_code != 200:
            raise ProviderError(f"IGDB query failed ({r.status_code})")
        return r.json()

    @staticmethod
    def _devs(g: dict) -> list[str]:
        return dedupe([ic["company"]["name"] for ic in g.get("involved_companies", [])
                       if ic.get("developer") and ic.get("company")], 3)

    def search(self, q: str) -> list[Candidate]:
        q = q.replace('"', " ")
        rows = self._query(f'search "{q}"; fields {FIELDS}; limit 10;')
        return [Candidate(source=self.source, source_id=str(g["id"]), title=g.get("name") or "?", creators=self._devs(g),
                          year=_year(g.get("first_release_date")), cover_url=_cover(g.get("cover")), url=g.get("url"),
                          blurb=clip(g.get("summary"), 140)) for g in rows]

    def fetch(self, source_id: str) -> WorkData:
        if not source_id.isdigit():
            raise ProviderError(f"bad IGDB id {source_id!r}")
        rows = self._query(f"fields {FIELDS}; where id = {int(source_id)};")
        if not rows:
            raise ProviderError(f"IGDB game {source_id} not found")
        g = rows[0]
        tags = [x["name"] for k in ("genres", "themes", "keywords") for x in g.get(k, []) if x.get("name")]
        return WorkData(source=self.source, source_id=source_id, title=g.get("name") or "?", creators=self._devs(g),
                        year=_year(g.get("first_release_date")), cover_url=_cover(g.get("cover")), url=g.get("url"),
                        summary=clip(g.get("summary")), raw_tags=dedupe(tags, 30))
