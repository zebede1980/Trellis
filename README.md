# Trellis

Track what you've read, watched, played and listened to. Trellis links everything by shared themes, draws it as a
tree, and suggests what to try next across media ("you like slow-burn political intrigue in books and games, here's
a TV series").

- **Boards**: Books, Films, TV, Games, Music, plus custom boards (board games, podcasts, anything).
- **Catalogues are the source of truth** for titles, creators, years and covers. The AI only does taste: themes,
  reasons and ideas. Every suggestion on a built-in board is matched to a real catalogue record or dropped.
- **Themes** are a controlled vocabulary (`src/trellis/seed_traits.json`) the AI must reuse before inventing.
- **Map**: You → themes → your things and suggestions. Canvas map on desktop, accordion on phone.

Invite-only: an admin creates accounts.

## Stack

FastAPI + SQLite (WAL) + a job thread in the same process; SvelteKit (SPA, static build) served by FastAPI;
Cytoscape + dagre for the map; NanoGPT (OpenAI-compatible) for the AI; Brave Search for custom-board lookups.

| Board | Catalogue | Key |
|---|---|---|
| Books | Open Library | none |
| Films, TV | TMDB (`TMDB_READ_TOKEN`); fallback Wikidata (films) / TVmaze (TV) | optional |
| Games | IGDB (`IGDB_CLIENT_ID` + `IGDB_CLIENT_SECRET`); fallback Wikidata | optional |
| Music | MusicBrainz + Cover Art Archive | none |
| Custom | Brave Search + LLM | `BRAVE_SEARCH_API_KEY`, `NANOGPT_API_KEY` |

## Run locally (PowerShell)

```powershell
uv sync
copy .env.example .env   # then fill in keys
uv run trellis user add yourname --admin
cd web; npm install; npm run build; cd ..
uv run trellis serve --port 8000          # serves API + built frontend on http://127.0.0.1:8000
```

For frontend work run `npm run dev` in `web/` as well (Vite proxies `/api` to port 8000).
Set `TRELLIS_WORKER=0` to stop the background worker making LLM calls while you click around.

Tests: `uv run pytest` (HTTP is mocked from recorded fixtures; the LLM is faked). Frontend types: `npm run check` in `web/`.

## Deploy (OCI, bash)

```bash
ssh oci 'cd ~/DockerSource/trellis && git pull && docker compose up -d --build'
curl -fsS https://trellis.terminuscloud.giize.com/api/health
ssh oci 'docker logs --tail 50 trellis-web'
```

Users: `ssh oci 'docker exec -it trellis-web trellis user add <name>'` (prompts for the password), or the Admin page.

## Evals

- `trellis tag-eval [--limit N] [--model M --model M2]`: tags a fixed set of well-known works twice per model and
  reports run-to-run overlap, invented themes, and how many themes span more than one medium. Uses `data/eval.db`.
- `trellis rec-eval <user> [--mode all|explore|trait|board] [--dry-run]`: one recommendation pass, printing what was
  verified, dropped, or already known.

Both make real LLM calls.

## Backups

`scripts/backup.sh` takes an online SQLite backup into `backups/` and keeps 14 days. Cron on the server:

```
15 3 * * * /home/ubuntu/DockerSource/trellis/scripts/backup.sh >> /home/ubuntu/DockerSource/trellis/backups/backup.log 2>&1
```

Restore:

```bash
cd ~/DockerSource/trellis
docker compose stop web
gunzip -c backups/trellis-YYYYMMDD-HHMMSS.db.gz > /tmp/trellis.db
sudo cp /tmp/trellis.db data/trellis.db && sudo rm -f data/trellis.db-wal data/trellis.db-shm
sudo chown 1000:1000 data/trellis.db
docker compose start web
```

## Attribution

This product uses the TMDB API but is not endorsed or certified by TMDB. Data also from Open Library, MusicBrainz,
the Cover Art Archive, TVmaze, Wikidata, Wikipedia and IGDB.
