"""TVmaze: keyless fallback for TV when there is no TMDB token."""

import re

from trellis.catalogue.base import Candidate, ProviderError, RateLimit, WorkData, clip, client, dedupe, year_of

BASE = "https://api.tvmaze.com"
_limit = RateLimit(0.5)


def _strip_html(s: str | None) -> str | None:
    return re.sub(r"<[^>]+>", "", s) if s else None


class TVmaze:
    source = "tvmaze"

    def search(self, q: str) -> list[Candidate]:
        _limit.wait()
        with client() as c:
            r = c.get(f"{BASE}/search/shows", params={"q": q})
        if r.status_code != 200:
            raise ProviderError(f"TVmaze search failed ({r.status_code})")
        out = []
        for hit in r.json()[:10]:
            s = hit["show"]
            out.append(Candidate(source=self.source, source_id=str(s["id"]), title=s.get("name") or "?",
                                 year=year_of(s.get("premiered")), cover_url=(s.get("image") or {}).get("medium"),
                                 url=s.get("url"), blurb=clip(_strip_html(s.get("summary")), 140)))
        return out

    def fetch(self, source_id: str) -> WorkData:
        if not source_id.isdigit():
            raise ProviderError(f"bad TVmaze id {source_id!r}")
        _limit.wait()
        with client() as c:
            r = c.get(f"{BASE}/shows/{source_id}", params={"embed": "crew"})
        if r.status_code != 200:
            raise ProviderError(f"TVmaze show {source_id} not found")
        s = r.json()
        crew = (s.get("_embedded") or {}).get("crew", [])
        creators = [x["person"]["name"] for x in crew if x.get("type") in ("Creator", "Developer")]
        return WorkData(source=self.source, source_id=source_id, title=s.get("name") or "?",
                        creators=dedupe(creators, 3), year=year_of(s.get("premiered")),
                        cover_url=(s.get("image") or {}).get("medium"), url=s.get("url"),
                        summary=clip(_strip_html(s.get("summary"))), raw_tags=dedupe(s.get("genres") or []))
