"""Which catalogue serves which board kind.

Keyed providers (TMDB, IGDB) are used when their keys are configured; otherwise films and games fall back to
Wikidata and TV to TVmaze, so every built-in board works without accounts.
"""

from trellis.catalogue.base import Candidate, Provider, ProviderError, TTLCache, WorkData
from trellis.config import Settings

_search_cache = TTLCache()


def providers_for(kind: str, s: Settings) -> list[Provider]:
    from trellis.catalogue.igdb import IGDB
    from trellis.catalogue.musicbrainz import MusicBrainz
    from trellis.catalogue.openlibrary import OpenLibrary
    from trellis.catalogue.tmdb import TMDB
    from trellis.catalogue.tvmaze import TVmaze
    from trellis.catalogue.wikidata import Wikidata

    if kind == "book":
        return [OpenLibrary()]
    if kind == "film":
        return [TMDB(s.tmdb_token, "movie")] if s.tmdb_token else [Wikidata("film")]
    if kind == "tv":
        return [TMDB(s.tmdb_token, "tv")] if s.tmdb_token else [TVmaze()]
    if kind == "game":
        return [IGDB(s.igdb_client_id, s.igdb_client_secret)] if s.igdb_client_id and s.igdb_client_secret \
            else [Wikidata("game")]
    if kind == "music":
        return [MusicBrainz()]
    if kind == "custom":
        from trellis.catalogue.ai_lookup import AILookup
        return [AILookup(s)]
    raise ValueError(f"unknown kind {kind!r}")


def provider(kind: str, source: str, s: Settings) -> Provider | None:
    return next((p for p in providers_for(kind, s) if p.source == source), None)


def search(kind: str, q: str, s: Settings, hint: str | None = None) -> list[Candidate]:
    key = f"{kind}|{hint or ''}|{q.strip().lower()}"
    hit = _search_cache.get(key)
    if hit is not None:
        return hit
    out: list[Candidate] = []
    for p in providers_for(kind, s):
        out += p.search(q, hint) if kind == "custom" else p.search(q)
    _search_cache.put(key, out)
    return out


def find_match(kind: str, title: str, creator: str | None, year: int | None, s: Settings) -> Candidate | None:
    """The catalogue record for a known title, or None. Plain search first, then the provider's targeted lookup
    (fielded title + creator) when it has one."""
    from trellis import match

    hit = match.best_match(title, year, creator, search(kind, title, s))
    if hit is not None:
        return hit
    for p in providers_for(kind, s):
        if hasattr(p, "find"):
            hit = match.best_match(title, year, creator, p.find(title, creator, year))
            if hit is not None:
                return hit
    return None


__all__ = ["Candidate", "WorkData", "ProviderError", "providers_for", "provider", "search"]
