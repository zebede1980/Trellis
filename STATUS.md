# Status

Live: https://trellis.terminuscloud.giize.com (OCI, container `trellis-web`, host port 8090, NPM proxy host #30, cert `npm-45`).
Plan: `C:\Users\joebl\.claude\plans\i-want-to-create-zazzy-puffin.md`. Last updated 2026-11-15.

## Stages

| Stage | State |
|---|---|
| 0 Prerequisites | Done. TMDB token in `.env`. IGDB keys **not yet** (games use Wikidata until added). Models checked against `/api/v1/models`. |
| 1 Skeleton + deploy | Done. ARM64 build fine. NPM host + Let's Encrypt cert created directly (backup of `npm_data` at `~/DockerSource/_backup_npm_before_trellis_20261115-080525.tgz`). |
| 2 Accounts + boards | Done. Prod admin `joe` created; temp password in `~/DockerSource/trellis/initial-admin.txt` on the server. |
| 3 Add things | Done. Open Library, TMDB, MusicBrainz live; Wikidata (films/games fallback), TVmaze (TV fallback), IGDB (mocked only). |
| 4 Themes | Built. **Gate pending: your review** (see below). |
| 5 Tree | Done. Accordion (phone) + Cytoscape map (desktop ≥900px), side panel, theme pages, group by board. |
| 6 Recommendations | Built + one real run. **Gate pending: rate 20 suggestions.** |
| 7 Custom boards | Built (Brave search + LLM lookup, "add exactly what I typed", unverified badges). **Not tried against the real LLM** (budget). |
| 8 Hardening | Mostly done: PWA manifest/icons, admin (users, theme rename/merge, AI "suggest merges", usage), change password, export, backup script, empty states. **Cron not installed** (see open items). |
| 9 Extras | Not started. |

## Gates waiting for you

### Seed vocabulary (Stage 4)
`src/trellis/seed_traits.json`: 90 themes across theme/tone/setting/style/genre/medium. Check the grain
("political intrigue", not "politics"). Edit the file before many works are tagged; renames later go through Admin → Themes.

### Tag eval (Stage 4) — full run, 2026-11-15
`trellis tag-eval` (30 works, 2 runs, batch 5) with `anthropic/claude-haiku-5.5`; 29 resolved (Blackstar, see open items):
- run-to-run overlap **0.68** (target 0.70; the mini run before the temperature-0 change was 0.60)
- spanning ≥2 kinds: **49 of 79 traits (0.62)**, target 0.5 met
- invented (12, sensible grain): childhood-trauma, desert-planet, first-contact, gender-identity, labyrinth,
  metroidvania, neo-noir, pastoral-life, racial-injustice, suburbia, surreal-house, underground-kingdom
- misses are mostly near-synonym swaps (character-driven vs moral-ambiguity, epic vs ensemble-cast), not wrong tags.
  Odd ones: Left Hand of Darkness "deep-space", The Last of Us "horror" (one run each)
- 1 validation retry (a work came back with 10 traits)

Recommendation: keep Haiku. Production tags each work once and stores it, so run-to-run wobble shows up as which of
two near-synonyms gets picked, and Admin → Themes → Suggest merges cleans those up. A Sonnet comparison is ≈12 more calls.
Full output is not committed; rerun the command to reproduce.

### Recommendations (Stage 6) — one real run
`trellis rec-eval dev --mode all` on a 17-entry demo profile (locally): 14 ideas, the first 8 all verified against
catalogues, **0 invented titles dropped**. Picks: I, Claudius; A Memory Called Empire; The Traitor Baru Cormorant;
The Book of the New Sun; There Will Be Blood; Tinker Tailor Soldier Spy; Stalker; Andor. Every reason cited the
user's own entries. Issue found and fixed: the first 8 were all books/films/TV, so ideas are now interleaved across
boards before verification. Gate still needs you to rate 20 suggestions on your own profile.

## NanoGPT spend (you authorised 20 calls)

| What | Calls |
|---|---|
| tag-eval (2 batches × 2 runs + 2 validation retries) | 6 |
| tagging the demo profile: replies truncated at max_tokens, then job retries multiplied it (bug, now fixed) | 10 |
| rec-eval run (1 Sonnet recommend + 2 Haiku tag) | 3 |
| **First block total (of 20)** | **19** |
| Second block (you authorised 15): full tag-eval, 12 calls + 1 validation retry | 13 |
| **Grand total** | **32** |

First block tokens: 54.6k in / 44.1k out, all Haiku except the one Sonnet call; roughly US$0.05 at list prices.
Second block: 34.2k in / 34.7k out, all Haiku. 2 of the 15 left; no further calls made. The deployed app *will* call the
LLM when you use it (tagging on add, Discover runs); `LLM_DAILY_CAP` (default 400/day) and `REC_RUNS_PER_DAY` (10)
bound it.

## Open items

1. **Backup cron**: the script works (first backup taken), but adding it to your crontab was blocked for me. Run on the
   server: `(crontab -l; echo "15 3 * * * /home/ubuntu/DockerSource/trellis/scripts/backup.sh >> /home/ubuntu/DockerSource/trellis/backups/backup.log 2>&1") | crontab -`
2. **IGDB keys**: add `IGDB_CLIENT_ID` / `IGDB_CLIENT_SECRET` to `~/DockerSource/trellis/.env`, then `docker compose up -d`.
   Existing Wikidata game entries stay as they are.
3. **TMDB logo**: their terms want their logo on the About page. I used a text credit only (didn't want to download
   their asset unasked). Drop their SVG into `web/static/` and reference it in `settings/+page.svelte`.
4. **Open Library years**: some work records lack a first-publish year; fixed for new fetches (falls back to the search
   index), existing rows keep `NULL`.
5. **Music edge case**: albums whose official title differs from the common one (Bowie's "★" vs "Blackstar") can't be
   matched from AI suggestions. Rare; leave unless it bites.
6. Map: dagre layout re-runs on every expand/collapse (resets zoom to the tapped branch). Fine at this scale.

## Local dev

`data/dev-login.txt` (gitignored) holds the local `dev` admin's password; `data/trellis.db` has the demo profile.
