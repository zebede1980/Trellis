"""Custom boards: candidates from Brave web search, picked out by the LLM.

A candidate counts as verified only when its URL is one of the search results (the model cannot invent a URL that
passes). Without a Brave key the model answers from memory and everything is unverified. Search results are kept in
a server-side cache and `fetch` reads from it, so a client can only add what the server actually found.
"""

import hashlib
import json

from trellis import db, llm
from trellis.catalogue.base import Candidate, ProviderError, TTLCache, WorkData, clip, client, year_of
from trellis.config import Settings

BRAVE = "https://api.search.brave.com/res/v1/web/search"
_found = TTLCache(ttl_s=6 * 3600, size=2000)


def brave_search(s: Settings, q: str, count: int = 8) -> list[dict]:
    if not s.brave_api_key:
        return []
    with client(headers={"X-Subscription-Token": s.brave_api_key}) as c:
        r = c.get(BRAVE, params={"q": q, "count": count, "safesearch": "moderate", "text_decorations": "false"})
    if r.status_code != 200:
        raise ProviderError(f"web search failed ({r.status_code})")
    out = []
    for x in (r.json().get("web") or {}).get("results", [])[:count]:
        out.append({"title": x.get("title"), "url": x.get("url"), "snippet": clip(x.get("description"), 300)})
    return out


SYSTEM = """You help a user find a specific thing to add to a personal board. The board holds: {hint}.
They typed a search. Using the web results (if any) and your knowledge, list the real, specific items they most likely mean (best first, at most 6). Each item must be a single thing that belongs on this board (not a list article, shop page or category).

For each item give: title, creators (people or company behind it; [] if none), year (first release/publication, or null), url (copy EXACTLY from the web results if one is about this item, else null), blurb (max 20 words, what it is).

Return ONLY JSON: {{"items": [{{"title": "", "creators": [], "year": null, "url": null, "blurb": ""}}]}}"""


def _validate(obj: dict) -> list[str]:
    items = obj.get("items")
    if not isinstance(items, list):
        return ["'items' must be a list"]
    errs = []
    for i, it in enumerate(items):
        if not isinstance(it, dict) or not str(it.get("title", "")).strip():
            errs.append(f"item {i} needs a title")
        elif not isinstance(it.get("creators", []), list):
            errs.append(f"item {i}: creators must be a list")
    return errs


class AILookup:
    source = "ai"

    def __init__(self, s: Settings):
        self.s = s

    def search(self, q: str, hint: str | None = None) -> list[Candidate]:
        hint = hint or "things the user enjoys"
        results = brave_search(self.s, f"{q} {hint}")
        conn = db.connect(self.s.db_path)
        try:
            obj = llm.call_json(conn, self.s, purpose="lookup", model=self.s.lookup_model, max_tokens=1200,
                                messages=[{"role": "system", "content": SYSTEM.format(hint=hint)},
                                          {"role": "user", "content": json.dumps({"search": q, "web_results": results},
                                                                                 ensure_ascii=False)}],
                                validate=_validate)
        except llm.LLMError as e:
            raise ProviderError(str(e))
        finally:
            conn.close()
        urls = {r["url"] for r in results if r.get("url")}
        out = []
        for it in obj["items"][:6]:
            url = it.get("url") if it.get("url") in urls else None
            title = str(it["title"]).strip()[:200]
            year = it.get("year") if isinstance(it.get("year"), int) else year_of(str(it.get("year") or ""))
            creators = [str(c).strip()[:100] for c in it.get("creators", []) if str(c).strip()][:3]
            sid = hashlib.sha1(f"{hint}|{title.lower()}|{year}".encode()).hexdigest()[:16]
            c = Candidate(source=self.source, source_id=sid, title=title, creators=creators, year=year, url=url,
                          verified=url is not None, blurb=clip(str(it.get("blurb") or ""), 160))
            _found.put(sid, c)
            out.append(c)
        return out

    def fetch(self, source_id: str) -> WorkData:
        c = _found.get(source_id)
        if c is None:
            raise ProviderError("That search result has expired; search again.")
        return WorkData(**c.to_dict(), summary=c.blurb, raw_tags=[])


def remember(c: Candidate) -> None:
    """Make a candidate fetchable (used by the recommender for custom-board suggestions)."""
    _found.put(c.source_id, c)
