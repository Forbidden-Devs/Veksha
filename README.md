# Veksha

> Automated CI/CD is currently suspended. The next deployment target is a
> manually operated Hetzner VPS, and the next version starts from an empty data
> store. See [`docs/next-version.md`](docs/next-version.md) and the
> [`Hetzner runbook`](docs/hetzner-runbook.md).

Learn foreign-language vocabulary from the pages you actually read: select a
word → get a translation → the word becomes a spaced-repetition card
automatically. Plus LLM-generated topic lessons ("blocks") for grammar,
usage patterns, and interview-style topics.

## Repository layout

```
veksha-backend/    FastAPI backend: PostgreSQL storage (users, KB), token auth,
                    spaced repetition, LLM calls (OpenAI), training/lesson
                    WebSocket sessions, translation, immersion.
veksha-extension/  Chrome + Firefox extension (MV3, React + TypeScript,
                    Vite) — the capture surface: selection-translate popup,
                    immersion mode, YouTube subtitles, OCR capture,
                    plus the popup app.
veksha-web/        The same study app (chat / training / lessons / stats)
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

## Architecture notes

- User data lives in PostgreSQL; clients
  authenticate with a bearer token issued at registration
  (`POST /api/auth/register`).
- Learning behavior lives in the transport-independent
  `veksha-backend/learning_core_v2/` package. OpenAI Responses API, storage,
  caching, and HTTP composition live in `learning_core_v2_adapters/` and
  `api/`; there is no parallel legacy LLM implementation.
- Trainings and lessons run over WebSocket (`/api/training/ws`,
  `/api/lesson/ws`); everything else is plain HTTP (see
  `veksha-backend/README.md` for the endpoint list).
- The extension is the *capture* surface; the web app is the *study* surface.
  Extension-only APIs are isolated behind
  `veksha-extension/src/shared/platform.ts` so the popup tree runs in both.
