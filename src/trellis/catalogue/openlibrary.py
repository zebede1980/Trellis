"""Open Library: books, keyed by *work* (not edition) so reprints don't duplicate."""

from trellis.catalogue.base import Candidate, ProviderError, RateLimit, WorkData, clip, client, dedupe, year_of

BASE = "https://openlibrary.org"
_limit = RateLimit(0.35)

# Subjects that say nothing about taste.
_NOISE = ("fiction", "accessible book", "protected daisy", "in library", "large type books", "open library",
          "staff picks", "nyt:", "new york times", "reading level", "lending library", "long now")


def _cover(cover_id) -> str | None:
    return f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else None


class OpenLibrary:
    source = "openlibrary"

    def search(self, q: str, **fielded) -> list[Candidate]:
        _limit.wait()
        params = {"q": q} if q else {}
        with client() as c:
            r = c.get(f"{BASE}/search.json", params={
                **params, **fielded, "limit": 10,
                "fields": "key,title,author_name,first_publish_year,cover_i,edition_count"})
        if r.status_code != 200:
            raise ProviderError(f"Open Library search failed ({r.status_code})")
        out = []
        for d in r.json().get("docs", []):
            key = (d.get("key") or "").removeprefix("/works/")
            if not key:
                continue
            out.append(Candidate(source=self.source, source_id=key, title=d.get("title") or "?",
                                 creators=(d.get("author_name") or [])[:3], year=d.get("first_publish_year"),
                                 cover_url=_cover(d.get("cover_i")), url=f"{BASE}/works/{key}"))
        return out

    def find(self, title: str, creator: str | None, year: int | None) -> list[Candidate]:
        return self.search("", title=title, **({"author": creator} if creator else {}))

    def fetch(self, source_id: str, _hops: int = 0) -> WorkData:
        with client() as c:
            _limit.wait()
            r = c.get(f"{BASE}/works/{source_id}.json")
            if r.status_code != 200:
                raise ProviderError(f"Open Library work {source_id} not found")
            w = r.json()
            if (w.get("type") or {}).get("key") == "/type/redirect" and _hops < 3:
                return self.fetch(w["location"].removeprefix("/works/"), _hops + 1)
            authors = []
            for a in (w.get("authors") or [])[:2]:
                key = (a.get("author") or {}).get("key") or ""
                if key.startswith("/authors/"):
                    _limit.wait()
                    ar = c.get(f"{BASE}{key}.json")
                    if ar.status_code == 200 and ar.json().get("name"):
                        authors.append(ar.json()["name"])
        desc = w.get("description")
        if isinstance(desc, dict):
            desc = desc.get("value")
        subjects = [s for s in (w.get("subjects") or []) + (w.get("subject_places") or [])
                    + (w.get("subject_times") or [])
                    if isinstance(s, str) and not any(n in s.lower() for n in _NOISE) and len(s) < 60]
        covers = [c for c in (w.get("covers") or []) if isinstance(c, int) and c > 0]
        key = w.get("key", f"/works/{source_id}")
        year = year_of(w.get("first_publish_date"))
        if year is None:   # many work records lack it; the search index has first_publish_year
            hit = next(iter(self.search(f"key:{key}")), None)
            year = hit.year if hit else None
        return WorkData(source=self.source, source_id=key.removeprefix("/works/"), title=w.get("title") or "?",
                        creators=authors, year=year,
                        cover_url=_cover(covers[0] if covers else None), url=f"{BASE}{key}",
                        summary=clip(desc), raw_tags=dedupe(subjects, 25))
