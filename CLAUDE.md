# Trellis — notes for Claude

Read `STATUS.md` first: it says which stage is done and what is open. The original plan lives at
`C:\Users\joebl\.claude\plans\i-want-to-create-zazzy-puffin.md`.

## Layout

- `src/trellis/` — Python package. `api/` routers (all user-scoped queries filter on the session `user_id`),
  `catalogue/` providers, `traits.py` (tagging + vocabulary), `taste.py` (affinity SQL + tree), `recommend.py`
  (suggestion pipeline), `jobs.py` (SQLite queue + worker thread), `llm.py` (NanoGPT + validate/retry + usage log),
  `match.py` (title matching), `migrations/NNN_*.sql` (applied by `PRAGMA user_version`).
- `web/` — SvelteKit **3** SPA. Config is in `vite.config.ts` (there is no `svelte.config.js` in Kit 3).
  Imports use `#lib/...` (package.json `imports`), not `$lib`. State uses Svelte 5 runes; `$app/state`, not stores.
  Never name a variable `state` in a component (it shadows the `$state` rune).
- `tests/` — pytest; `tests/fixtures/` are recorded real API responses; `conftest.py` routes httpx to them and
  provides `fake_llm`.

## Commands

- Tests: `uv run pytest`; frontend: `cd web; npm run check; npm run build`
- Local: `uv run trellis serve --port 8000` (reads `.env`; set `TRELLIS_WORKER=0` to avoid LLM spend)
- Deploy: `ssh oci 'cd ~/DockerSource/trellis && git pull && docker compose up -d --build'`
- Prod host port 8090 (127.0.0.1 only); NPM proxy host #30 → `trellis-web:8000`, cert `npm-45`.

## Rules

- Never render catalogue or AI text with `{@html}`. Never fetch URLs supplied by the AI server-side.
- One uvicorn worker only (the job thread must not be duplicated).
- Each LLM call costs money: recommend and tag jobs fail without job-level retries; `LLM_DAILY_CAP` (default 400)
  caps all calls per day. Ask the user before running evals or anything that calls the LLM in bulk.
- Conventional Commits.
