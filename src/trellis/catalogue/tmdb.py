"""TMDB: films and TV. Free for non-commercial use; attribution is shown on the About page.

source_id is "movie:<id>" or "tv:<id>".
"""

from trellis.catalogue.base import Candidate, ProviderError, RateLimit, WorkData, clip, client, dedupe, year_of

BASE = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p/w342"
_limit = RateLimit(0.1)


class TMDB:
    source = "tmdb"

    def __init__(self, token: str, media: str):
        assert media in ("movie", "tv")
        self.token, self.media = token, media

    def _get(self, path: str, **params) -> dict:
        _limit.wait()
        with client(headers={"Authorization": f"Bearer {self.token}"}) as c:
            r = c.get(f"{BASE}{path}", params=params)
        if r.status_code != 200:
            raise ProviderError(f"TMDB {path} failed ({r.status_code})")
        return r.json()

    def search(self, q: str) -> list[Candidate]:
        data = self._get(f"/search/{self.media}", query=q, include_adult="false")
        out = []
        for d in data.get("results", [])[:10]:
            title = d.get("title") or d.get("name") or "?"
            date = d.get("release_date") or d.get("first_air_date")
            out.append(Candidate(source=self.source, source_id=f"{self.media}:{d['id']}", title=title,
                                 year=year_of(date), cover_url=IMG + d["poster_path"] if d.get("poster_path") else None,
                                 url=f"https://www.themoviedb.org/{self.media}/{d['id']}",
                                 blurb=clip(d.get("overview"), 140)))
        return out

    def fetch(self, source_id: str) -> WorkData:
        media, _, tid = source_id.partition(":")
        if media not in ("movie", "tv") or not tid.isdigit():
            raise ProviderError(f"bad TMDB id {source_id!r}")
        d = self._get(f"/{media}/{tid}", append_to_response="keywords,credits")
        credits = d.get("credits") or {}
        if media == "movie":
            creators = [c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"]
            kw = (d.get("keywords") or {}).get("keywords", [])
        else:
            creators = [c["name"] for c in d.get("created_by", [])]
            kw = (d.get("keywords") or {}).get("results", [])
        tags = [g["name"] for g in d.get("genres", [])] + [k["name"] for k in kw]
        return WorkData(source=self.source, source_id=source_id, title=d.get("title") or d.get("name") or "?",
                        creators=dedupe(creators, 3),
                        year=year_of(d.get("release_date") or d.get("first_air_date")),
                        cover_url=IMG + d["poster_path"] if d.get("poster_path") else None,
                        url=f"https://www.themoviedb.org/{media}/{tid}", summary=clip(d.get("overview")),
                        raw_tags=dedupe(tags, 30))
