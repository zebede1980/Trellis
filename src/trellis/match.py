"""Title normalisation and candidate matching.

Used to check that an AI-suggested title is a real catalogue record. Deliberately strict: a wrong match shows the
user the wrong thing with a confident cover, which is worse than dropping the suggestion.
"""

import re
import unicodedata
from difflib import SequenceMatcher

_ARTICLES = re.compile(r"^(the|a|an|le|la|les|el|der|die|das)\s+")
_ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10"}


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def norm_title(s: str, keep_subtitle: bool = True) -> str:
    s = _ascii(s or "").lower().replace("&", " and ")
    if not keep_subtitle:
        s = re.split(r"\s*[:(\[]\s*|\s+-\s+", s, maxsplit=1)[0]
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = _ARTICLES.sub("", s)
    return " ".join(_ROMAN.get(w, w) for w in s.split())


def title_ratio(a: str, b: str) -> float:
    """Best similarity of the two titles, with and without subtitles."""
    best = SequenceMatcher(None, norm_title(a), norm_title(b)).ratio()
    short_a, short_b = norm_title(a, False), norm_title(b, False)
    if short_a and short_b:
        # "Dune" vs "Dune: Part One" counts only if one side has no subtitle at all
        if short_a == short_b and (short_a == norm_title(a) or short_b == norm_title(b)):
            best = max(best, 0.95)
    return best


def _numbers(s: str) -> set[str]:
    return set(re.findall(r"\b\d+\b", norm_title(s)))


def name_tokens(names: list[str]) -> set[str]:
    out = set()
    for n in names or []:
        out |= {t for t in norm_title(n).split() if len(t) > 2}
    return out


def is_match(want_title: str, want_year: int | None, want_creator: str | None,
             got_title: str, got_year: int | None, got_creators: list[str]) -> tuple[bool, float]:
    """Normalised title ratio >= 0.9 AND (year within 1 OR a creator name overlap). Sequel numbers must agree."""
    r = title_ratio(want_title, got_title)
    if r < 0.9 or _numbers(want_title) != _numbers(got_title):
        return False, r
    year_ok = want_year is not None and got_year is not None and abs(want_year - got_year) <= 1
    creator_ok = bool(want_creator) and bool(name_tokens([want_creator]) & name_tokens(got_creators))
    return year_ok or creator_ok, r


def best_match(want_title: str, want_year: int | None, want_creator: str | None, candidates: list):
    """The best matching candidate (objects with .title/.year/.creators), or None."""
    scored = []
    for c in candidates:
        ok, r = is_match(want_title, want_year, want_creator, c.title, c.year, c.creators)
        if ok:
            year_gap = abs((want_year or 0) - (c.year or 0)) if want_year and c.year else 5
            scored.append((r, -year_gap, c))
    if not scored:
        return None
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return scored[0][2]
