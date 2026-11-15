"""Quality evals for the AI parts. Run from the CLI; output is for a human to read and sign off."""

import json
import sqlite3
from collections import defaultdict

from trellis import catalogue, db, traits, works
from trellis.config import Settings

# Well-known works across every kind, chosen so that real cross-media links exist
# (political intrigue, found family, grief, AI, survival...).
EVAL_WORKS = [
    ("book", "Dune", "Frank Herbert", 1965),
    ("book", "The Left Hand of Darkness", "Ursula K. Le Guin", 1969),
    ("book", "Piranesi", "Susanna Clarke", 2020),
    ("book", "The Remains of the Day", "Kazuo Ishiguro", 1989),
    ("book", "A Little Life", "Hanya Yanagihara", 2015),
    ("book", "The Name of the Wind", "Patrick Rothfuss", 2007),
    ("book", "Project Hail Mary", "Andy Weir", 2021),
    ("film", "Arrival", "Denis Villeneuve", 2016),
    ("film", "Spirited Away", "Hayao Miyazaki", 2001),
    ("film", "The Godfather", "Francis Ford Coppola", 1972),
    ("film", "Ex Machina", "Alex Garland", 2015),
    ("film", "Paddington 2", "Paul King", 2017),
    ("film", "Mad Max: Fury Road", "George Miller", 2015),
    ("tv", "Succession", "Jesse Armstrong", 2018),
    ("tv", "The Expanse", None, 2015),
    ("tv", "Severance", "Dan Erickson", 2022),
    ("tv", "The Wire", "David Simon", 2002),
    ("tv", "Ted Lasso", None, 2020),
    ("game", "Disco Elysium", None, 2019),
    ("game", "Hollow Knight", None, 2017),
    ("game", "The Last of Us", None, 2013),
    ("game", "Stardew Valley", None, 2016),
    ("game", "Crusader Kings III", None, 2020),
    ("game", "Outer Wilds", None, 2019),
    ("music", "OK Computer", "Radiohead", 1997),
    ("music", "Carrie & Lowell", "Sufjan Stevens", 2015),
    ("music", "To Pimp a Butterfly", "Kendrick Lamar", 2015),
    ("music", "Rumours", "Fleetwood Mac", 1977),
    ("music", "The Suburbs", "Arcade Fire", 2010),
    ("music", "Blackstar", "David Bowie", 2016),
]


def resolve_eval_works(conn: sqlite3.Connection, s: Settings, items: list[tuple], log=print) -> list[sqlite3.Row]:
    out = []
    for kind, title, creator, year in items:
        try:
            hit = catalogue.find_match(kind, title, creator, year, s)
        except catalogue.ProviderError as e:
            log(f"  ! {title}: {e}")
            continue
        if hit is None:
            log(f"  ! {title}: no catalogue match")
            continue
        wid = works.get_or_fetch(conn, s, kind, hit.source, hit.source_id)
        out.append(conn.execute("SELECT * FROM work WHERE work_id = ?", (wid,)).fetchone())
    return out


def tag_eval(s: Settings, *, models: list[str], runs: int = 2, limit: int | None = None, batch: int = 5,
             log=print) -> dict:
    """Tag the eval works `runs` times per model without saving, and report consistency and cross-media reach."""
    conn = db.connect(s.data_dir / "eval.db")
    db.migrate(conn)
    traits.load_seed(conn)
    items = EVAL_WORKS[:limit] if limit else EVAL_WORKS
    # spread a limited run across kinds rather than taking the first N books
    if limit:
        by_kind = defaultdict(list)
        for it in EVAL_WORKS:
            by_kind[it[0]].append(it)
        items, i = [], 0
        while len(items) < limit:
            for k in by_kind:
                if i < len(by_kind[k]) and len(items) < limit:
                    items.append(by_kind[k][i])
            i += 1
    log(f"resolving {len(items)} works against the catalogues…")
    ws = resolve_eval_works(conn, s, items, log)
    kind_of = {w["work_id"]: w["kind"] for w in ws}
    title_of = {w["work_id"]: w["title"] for w in ws}
    report = {}
    for model in models:
        log(f"\n=== {model} ===")
        results: list[dict[int, list[tuple[str, float]]]] = []
        for r in range(runs):
            merged: dict = {}
            for i in range(0, len(ws), batch):
                merged.update(traits.tag_works(conn, s, ws[i:i + batch], model=model, write=False))
            results.append(merged)
        overlaps = []
        for wid in kind_of:
            sets = [{slug for slug, _ in res.get(wid, [])} for res in results]
            if len(sets) >= 2 and sets[0] | sets[1]:
                overlaps.append(len(sets[0] & sets[1]) / len(sets[0] | sets[1]))
            log(f"  {title_of[wid][:40]:<40} ({kind_of[wid]}) " + " | ".join(
                ", ".join(sorted(sl)) for sl in sets))
        invented = sorted({slug for res in results for pairs in res.values() for slug, _ in pairs if slug.startswith("+")})
        kinds_per_trait: dict[str, set] = defaultdict(set)
        for wid, pairs in results[0].items():
            for slug, _ in pairs:
                kinds_per_trait[slug].add(kind_of[wid])
        spanning = sum(1 for k in kinds_per_trait.values() if len(k) >= 2)
        rep = {"works": len(ws), "mean_overlap": round(sum(overlaps) / len(overlaps), 3) if overlaps else None,
               "invented": invented, "traits_used": len(kinds_per_trait),
               "traits_spanning_2plus_kinds": spanning,
               "share_spanning": round(spanning / len(kinds_per_trait), 3) if kinds_per_trait else None}
        log(json.dumps(rep, indent=1))
        report[model] = rep
    calls = conn.execute("SELECT COUNT(*), SUM(prompt_tokens), SUM(completion_tokens) FROM llm_call").fetchone()
    log(f"\nLLM calls in eval db so far: {calls[0]} (prompt tokens {calls[1]}, completion tokens {calls[2]})")
    conn.close()
    return report
