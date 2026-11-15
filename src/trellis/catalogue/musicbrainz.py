"""MusicBrainz: albums (release groups) and artists. 1 request/second and a descriptive User-Agent.

source_id is "rg:<mbid>" or "artist:<mbid>". Covers come from the Cover Art Archive; the URL is a redirect that 404s
when there is no art, so the frontend hides broken images.
"""

import re
import time

from trellis.catalogue.base import Candidate, ProviderError, RateLimit, WorkData, client, dedupe, year_of

BASE = "https://musicbrainz.org/ws/2"
_limit = RateLimit(1.1)
_MBID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_LUCENE = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')


def _cover(rgid: str) -> str:
    return f"https://coverartarchive.org/release-group/{rgid}/front-250"


def _credit(ac: list[dict]) -> str:
    return "".join(a.get("name", "") + a.get("joinphrase", "") for a in ac or []).strip()


def _get(path: str, **params) -> dict:
    for attempt in range(3):
        if attempt:
            time.sleep(1.5 * attempt)
        _limit.wait()
        with client() as c:
            r = c.get(f"{BASE}{path}", params={**params, "fmt": "json"})
        if r.status_code == 503:   # "server busy": back off once
            continue
        if r.status_code != 200:
            raise ProviderError(f"MusicBrainz {path} failed ({r.status_code})")
        return r.json()
    raise ProviderError("MusicBrainz is busy; try again in a moment")


class MusicBrainz:
    source = "musicbrainz"

    def search(self, q: str) -> list[Candidate]:
        safe = _LUCENE.sub(r"\\\1", q)
        groups = _get("/release-group/", query=safe, limit=15).get("release-groups", [])

        def rank(g):
            album = g.get("primary-type") == "Album" and not g.get("secondary-types")
            return (-int(g.get("score", 0)), not album, g.get("first-release-date") or "9999")

        out = []
        for g in sorted(groups, key=rank)[:7]:
            kind = g.get("primary-type") or "Release"
            if g.get("secondary-types"):
                kind += " · " + ", ".join(g["secondary-types"])
            out.append(Candidate(source=self.source, source_id=f"rg:{g['id']}", title=g.get("title") or "?",
                                 creators=[_credit(g.get("artist-credit"))], year=year_of(g.get("first-release-date")),
                                 cover_url=_cover(g["id"]), url=f"https://musicbrainz.org/release-group/{g['id']}",
                                 blurb=kind))
        artists = _get("/artist/", query=safe, limit=3).get("artists", [])
        for a in artists:
            if int(a.get("score", 0)) < 90:
                continue
            out.append(Candidate(source=self.source, source_id=f"artist:{a['id']}", title=a.get("name") or "?",
                                 year=year_of((a.get("life-span") or {}).get("begin")),
                                 url=f"https://musicbrainz.org/artist/{a['id']}",
                                 blurb="Artist" + (f" · {a['disambiguation']}" if a.get("disambiguation") else "")))
        return out

    def fetch(self, source_id: str) -> WorkData:
        typ, _, mbid = source_id.partition(":")
        if typ not in ("rg", "artist") or not _MBID.match(mbid):
            raise ProviderError(f"bad MusicBrainz id {source_id!r}")
        if typ == "rg":
            g = _get(f"/release-group/{mbid}", inc="artist-credits+tags+genres")
            tags = [x["name"] for x in sorted(g.get("genres", []) + g.get("tags", []), key=lambda t: -t.get("count", 0))
                    if not re.fullmatch(r"\d{4}s?|.*wochen.*", x["name"])]
            return WorkData(source=self.source, source_id=source_id, title=g.get("title") or "?",
                            creators=[_credit(g.get("artist-credit"))], year=year_of(g.get("first-release-date")),
                            cover_url=_cover(mbid), url=f"https://musicbrainz.org/release-group/{mbid}",
                            summary=None, raw_tags=dedupe(tags, 25))
        a = _get(f"/artist/{mbid}", inc="tags+genres")
        tags = [x["name"] for x in sorted(a.get("genres", []) + a.get("tags", []), key=lambda t: -t.get("count", 0))]
        return WorkData(source=self.source, source_id=source_id, title=a.get("name") or "?", creators=[],
                        year=year_of((a.get("life-span") or {}).get("begin")),
                        url=f"https://musicbrainz.org/artist/{mbid}", summary=a.get("disambiguation") or None,
                        raw_tags=dedupe(tags, 25))
