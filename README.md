# Veksha

> Automated CI/CD is currently suspended. The deployment target is a manually
> operated netcup VPS, application images are built locally, and the next
> version starts from an empty data store. See
> [`docs/next-version.md`](docs/next-version.md) and the
> [`VPS runbook`](docs/vps-runbook.md).

Learn foreign-language vocabulary from the pages you actually read: select a
word → get a translation → the word becomes a spaced-repetition card
automatically. Plus goal-oriented lessons: state the result you want —
"understand Past Perfect in stories", "get ready for the client call" — and the
lesson builds a checkable route to it and adapts to every answer.

## Repository layout

```
veksha-backend/    FastAPI backend: PostgreSQL storage (users, KB), token auth,
                    spaced repetition, LLM calls (OpenAI), training/goal
                    WebSocket sessions, translation, Reading Coach.
veksha-extension/  Chrome + Firefox extension (MV3, React + TypeScript,
                    Vite) — the capture surface: selection-translate popup,
                    Reading Coach, YouTube subtitles and subtitle study
                    sessions, OCR capture, plus the popup app.
veksha-web/        The same study app (chat / training / goals / stats)
                    as a standalone PWA-installable web page; reuses the
                    extension popup source via shared/platform.ts.
veksha-tgbot/      Telegram companion bot: sells subscriptions in Telegram
                    Stars and reports payments to the backend via webhook
                    (see veksha-backend/entitlements.py for tiers/plans).
veksha-admin/      Internal billing dashboard: per-feature Stars prices and
                    scoped promo-code issuance.
```

## Quick start

The complete local stack is built and started with Docker:

```bash
cp .env.example .env             # add OPENAI_API_KEY for LLM features
docker compose up --build
```

This starts PostgreSQL, Redis, the backend, the PWA and the admin panel. It also
builds both browser extensions into `veksha-extension/dist/` without requiring
Python or Node.js on the host.

- PWA: http://localhost:3000
- Backend and Swagger: http://localhost:8000 and http://localhost:8000/docs
- Admin: http://localhost:4173 (default local secret: `local-admin-secret`)
- Chrome extension: `veksha-extension/dist/chrome`
- Firefox extension: `veksha-extension/dist/firefox/manifest.json`

The Telegram bot needs real credentials and is opt-in:

```bash
docker compose --profile telegram up --build
```

Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME` and
`VEKSHA_BOT_WEBHOOK_SECRET` in `.env` first. Stop the stack with
`docker compose down`; add `--volumes` only when you intentionally want to
delete the local PostgreSQL and Redis data.

## Tests and local checks

Install each module's dependencies before running its checks (`requirements.txt`
plus `requirements-dev.txt` for Python modules, the lockfile-backed package
manager for JavaScript modules). Run these commands from the indicated module
directory:

| Module | Test command | Full local check |
|---|---|---|
| `veksha-backend/` | `python -m pytest -q` | `python -m compileall -q . && python -m ruff check --select E9,F63,F7,F82 . && python -m pytest -q` |
| `veksha-extension/` | `npm run test:architecture && npm run test:version` | `npm run check` |
| `veksha-web/` | No separate automated test suite yet | `npm run typecheck && npm run build` |
| `veksha-tgbot/` | `python -m pytest -q` | `python -m compileall -q . && python -m ruff check --select E9,F63,F7,F82 . && python -m pytest -q` |
| `veksha-admin/` | `pnpm run test` | `pnpm run typecheck && pnpm run test && pnpm run build` |

Backend API tests use a disposable PostgreSQL service on port `55432`. Start it
before the tests from the repository root:

```bash
docker compose --profile test up -d --wait postgres-test
cd veksha-backend
python -m pytest -q
```

The service stores its data in temporary container storage. The test fixture
also refuses to run against a database whose name does not end in `_test`,
because the API suite clears the selected database before it starts. Override
`DATABASE_URL` only when using another disposable test database.

The backend command discovers all three backend suites: `tests/`,
`learning_core_v2/tests/`, and `learning_core_v2_adapters/tests/`. When extension
shared or popup code changes, also run the web checks because the web app imports
those sources directly. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the checks
expected before a pull request.

## Architecture notes

- User data lives in PostgreSQL; clients
  authenticate with a bearer token issued at registration
  (`POST /api/auth/register`).
- Learning behavior lives in the transport-independent
  `veksha-backend/learning_core_v2/` package. OpenAI Responses API, storage,
  caching, and HTTP composition live in `learning_core_v2_adapters/` and
  `api/`; there is no parallel legacy LLM implementation.
- Trainings and goal lessons run over WebSocket (`/api/training/ws`,
  `/api/learning-goals/ws`); everything else is plain HTTP (see
  `veksha-backend/README.md` for the endpoint list).
- The extension is the *capture* surface; the web app is the *study* surface.
  Extension-only APIs are isolated behind
  `veksha-extension/src/shared/platform.ts` so the popup tree runs in both.
