"""Wikidata + Wikipedia: keyless fallback for films and games when TMDB / IGDB keys are missing.

Search uses `wbsearchentities` and keeps hits whose English description names the medium ("2017 video game",
"1999 American science fiction film"). Details come from the item's claims, with the cover and summary taken from
the English Wikipedia page summary.
"""

import re
from urllib.parse import quote

from trellis.catalogue.base import Candidate, ProviderError, RateLimit, WorkData, clip, client, dedupe, year_of

API = "https://www.wikidata.org/w/api.php"
WP = "https://en.wikipedia.org/api/rest_v1/page/summary/"
_limit = RateLimit(0.2)

MEDIA = {
    # kind: (description must match, creator properties)
    "film": (re.compile(r"\bfilm\b", re.I), ("P57",)),                 # director
    "game": (re.compile(r"\bvideo game\b", re.I), ("P178", "P123")),   # developer, publisher
}
_NOT = re.compile(r"\b(series|franchise|soundtrack|character|universe|wiki|film series|content pack|album)\b", re.I)


def _get(**params) -> dict:
    _limit.wait()
    with client() as c:
        r = c.get(API, params={**params, "format": "json"})
    if r.status_code != 200:
        raise ProviderError(f"Wikidata failed ({r.status_code})")
    return r.json()


def _label(entity: dict) -> str | None:
    # Many items now carry only a language-neutral "mul" label.
    labels = entity.get("labels", {})
    return (labels.get("en") or labels.get("mul") or {}).get("value")


class Wikidata:
    source = "wikidata"

    def __init__(self, kind: str):
        assert kind in MEDIA
        self.kind = kind

    def search(self, q: str) -> list[Candidate]:
        want, _ = MEDIA[self.kind]
        hits = _get(action="wbsearchentities", search=q, language="en", uselang="en", type="item",
                    limit=20).get("search", [])
        out = []
        for h in hits:
            desc = h.get("description") or ""
            if not want.search(desc) or _NOT.search(desc):
                continue
            out.append(Candidate(source=self.source, source_id=h["id"], title=h.get("label") or "?",
                                 year=year_of(desc), url=f"https://www.wikidata.org/wiki/{h['id']}", blurb=desc))
        return out[:10]

    def fetch(self, source_id: str) -> WorkData:
        if not re.fullmatch(r"Q\d+", source_id):
            raise ProviderError(f"bad Wikidata id {source_id!r}")
        e = _get(action="wbgetentities", ids=source_id, props="claims|labels|descriptions|sitelinks/urls",
                 sitefilter="enwiki", languages="en|mul").get("entities", {}).get(source_id)
        if not e or "missing" in e:
            raise ProviderError(f"Wikidata item {source_id} not found")
        claims = e.get("claims", {})

        def ids(prop: str) -> list[str]:
            out = []
            for c in claims.get(prop, []):
                v = (c.get("mainsnak") or {}).get("datavalue", {}).get("value")
                if isinstance(v, dict) and v.get("id"):
                    out.append(v["id"])
            return out

        creator_ids = [i for p in MEDIA[self.kind][1] for i in ids(p)][:3]
        genre_ids = ids("P136")[:10]
        labels = {}
        if creator_ids or genre_ids:
            ents = _get(action="wbgetentities", ids="|".join(dict.fromkeys(creator_ids + genre_ids)), props="labels",
                        languages="en|mul").get("entities", {})
            labels = {k: _label(v) for k, v in ents.items()}
        years = [year_of((c["mainsnak"].get("datavalue") or {}).get("value", {}).get("time"))
                 for c in claims.get("P577", []) if c.get("mainsnak")]
        years = [y for y in years if y]
        title = _label(e) or source_id
        desc = (e.get("descriptions", {}).get("en") or {}).get("value")
        enwiki = (e.get("sitelinks", {}).get("enwiki") or {})
        summary, cover, url = desc, None, enwiki.get("url") or f"https://www.wikidata.org/wiki/{source_id}"
        if enwiki.get("title"):
            _limit.wait()
            with client() as c:
                r = c.get(WP + quote(enwiki["title"].replace(" ", "_"), safe=""))
            if r.status_code == 200:
                s = r.json()
                summary = s.get("extract") or summary
                cover = (s.get("thumbnail") or {}).get("source")
        return WorkData(source=self.source, source_id=source_id, title=title,
                        creators=dedupe([labels[i] for i in creator_ids if labels.get(i)], 3),
                        year=min(years) if years else year_of(desc), cover_url=cover, url=url,
                        summary=clip(summary), raw_tags=dedupe([labels[i] for i in genre_ids if labels.get(i)]))
