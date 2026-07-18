# Veksha Backend (FastAPI)

HTTP + WebSocket API for the Veksha extension: vocabulary knowledge base
with spaced repetition, LLM-backed translation/explanation, word-training and
topic-lesson sessions, and page immersion.

## Running

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="sk-..."    # required
python main.py                     # or: uvicorn main:app --reload
```

Listens on `127.0.0.1:8000` by default. Swagger UI: `http://127.0.0.1:8000/docs`.

Optional env vars: `OPENAI_MODEL`, `OPENAI_SMART_MODEL`, `REDIS_URL`
(shared translation cache), `HOST`, `PORT`, `LOG_LEVEL`,
`VEKSHA_DATA_DIR` (runtime data location — point at a persistent volume in
production), `CORS_ALLOW_ORIGINS`, `VEKSHA_DEBUG_API`.

Google login additionally requires a **Web application** OAuth client and:

```bash
export GOOGLE_CLIENT_ID="<id>.apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="<web-client-secret>"
export GOOGLE_OAUTH_REDIRECT_URI="https://veksha.app/api/auth/google/callback"
```

Register the exact `GOOGLE_OAUTH_REDIRECT_URI` under **Authorized redirect
URIs** in Google Cloud Console. Keep the client secret on the backend only.

## Auth & storage

`POST /api/auth/register {"display_name"}` creates an account under a
generated internal id (`username`, keys every table; the display name is an
editable settings field) and issues a bearer token (once). Accounts created
before the id/name split keep their self-chosen username as the id and fall
back to it as the display name. Every other endpoint requires
`Authorization: Bearer <token>`; WebSocket routes authenticate with a first
message `{"type": "auth", "token": "..."}` after connecting (never in the
URL — query strings end up in access logs).

Google sign-in uses an Authorization Code flow whose only redirect is the
backend HTTPS callback. The extension opens the authorization URL in a normal
tab and polls with a separate high-entropy, single-use secret. No extension
redirect URI or custom browser scheme is exposed to Google, so the same flow
works in Chromium-, Firefox-, and WebKit-based browsers that support the
extension APIs. The returned Google identity resolves to the same internal
account and re-issues its bearer token, so signing in on another device or
after clearing extension storage restores the same vocabulary and settings.
Linking attaches a Google identity to an existing account (409 if it belongs
to someone else). Without a Google link, a lost local token still means a new
account.

All user data (accounts, KBs, chat history) lives in SQLite at
`data/veksha.db` (WAL mode). The KB is stored as one JSON document per user;
normalizing into tables is deferred to the FSRS rework.

## Subscriptions (Telegram Stars)

Premium features (Grammar Lens, page immersion, dual subtitles — see
`entitlements.py`) require an active subscription; gated endpoints return
HTTP 402 with `detail.code = "subscription_required"`. Payments are collected
by the companion bot (`veksha-tgbot/`) in Telegram Stars and reported to
`POST /api/billing/telegram/webhook` (header `X-Veksha-Bot-Secret`,
idempotent by `telegram_payment_charge_id`). Accounts are bound to Telegram
via a single-use deep-link code from `POST /api/billing/telegram/link`.
Configure `TELEGRAM_BOT_USERNAME` and `TELEGRAM_BOT_WEBHOOK_SECRET`; both
empty disables billing (the link endpoint returns 503, everyone stays on the
free tier).

Accounts default to the free tier. For manual test grants (e.g. beta
testers), mint a promo code with `ADMIN_API_SECRET` set and:

```
curl -X POST $API/api/billing/promo/create \
  -H "X-Veksha-Admin-Secret: $ADMIN_API_SECRET" -H "Content-Type: application/json" \
  -d '{"code": "BETA30", "days": 30, "max_redemptions": 20}'
```

Users redeem it once each via `POST /api/billing/promo/redeem` (Bearer
token, body `{"code": "..."}`) for `days` of Premium; without a code an
account stays on the free tier.

## Module map

```
main.py               app entry point, routers, CORS, error handler
config.py             env-based configuration
db.py                 SQLite: users/tokens, KB documents, chat history, review log
auth.py               bearer-token dependencies (HTTP + WebSocket)
models.py             Word, Patch, UserSettings, LessonTopic/LessonBlock
storage.py            per-user KB object model, spaced repetition primitives
fsrs.py               FSRS-4.5 scheduler (pure functions; default weights)
session_state.py      assistant-chat history (context for the input processor)
pipeline.py           /api/message flow: classify → answer or edit KB
selection.py          selection translate → KB update
training.py           word-training sessions (task generation, answer check)
lesson.py             topic lessons: block generation/review, mastery
i18n.py               UI/server strings + LLM-translated catalogues
entitlements.py       subscription tiers, plans, feature gating (require_feature)
llm/                  all OpenAI calls (pipeline, training, lesson,
                      selection, immersion, _base)
db_cache.py           SQLite cache for reusable LLM outputs
translation_cache.py  memory/Redis cache for short translations
api/                  routers (one file per domain)
```

## Endpoints

| Route | Purpose |
|---|---|
| `POST /api/auth/register` | create account, returns bearer token |
| `POST /api/auth/google/start`, `/api/auth/google/link/start` | start Google sign-in / identity link |
| `GET /api/auth/google/callback`, `GET /api/auth/google/*/status/{flow_id}` | Google HTTPS callback / one-time result |
| `POST /api/message` | assistant chat: answer questions or edit the KB |
| `POST /api/translate`, `/api/quick_translate` | selection translation (+background KB update) |
| `POST /api/explain` | expanded explanation for a selection |
| `GET/POST /api/settings` | user settings |
| `GET /api/reminders` | due words / topics for extension alarms |
| `GET /api/kb_summary`, `/api/kb_words`, `DELETE /api/kb_word` | vocabulary UI |
| `GET /api/training/init`, `POST /api/training/validate`, `WS /api/training/ws` | word training |
| `GET /api/training/review_log` | recent FSRS reviews (`?word=`, `?limit=`) |
| `GET/POST /api/lesson-topics`, `WS /api/lesson/ws` | topic lessons |
| `POST /api/immersion/analyze` | comprehensible-input page immersion (premium) |
| `POST /api/subtitles/translate` | dual-subtitle line translation with word alignment (premium) |
| `GET /api/billing/status`, `POST /api/billing/telegram/link` | subscription status / bot deep link |
| `POST /api/billing/promo/redeem` | redeem a promo code for temporary Premium |
| `GET /api/billing/plans`, `POST /api/billing/telegram/webhook` | companion-bot API (shared secret) |
| `POST /api/billing/promo/create` | mint a promo code (admin shared secret) |
| `GET /api/i18n/{lang}`, `POST /api/i18n/translate` | UI string catalogues |
| `POST /api/debug/*` | development helpers (reset, simulate, advance-day) |

WebSocket protocols are documented in the module docstrings of
`api/training.py` and `api/lesson.py`.

## Spaced repetition (FSRS)

Scheduling is FSRS-4.5 (`fsrs.py`, published default weights). Each word
carries a memory state — `stability` (interval in days at 90% recall),
`difficulty` (1–10), `last_review`, `lapses` — updated per review from the
LLM answer-check outcome: `correct` → Good, `vague` → Hard, `incorrect` →
Again (`garbage` is not a review). `next_review = now + interval` for
`config.FSRS_DESIRED_RETENTION` (0.9), clamped to
`FSRS_MIN/MAX_INTERVAL_DAYS`. A word is due once `next_review` is less than
`REVIEW_WINDOW_HOURS` away or overdue — lateness needs no special handling
because low retrievability at review time yields a bigger stability jump.
Overdue words only get `delayed=True` (weight ×2 in selection). `counter`
survives as the review count (`-1` = new, drives the UI badge).

Every review appends to the `review_log` table (rating, outcome, task type,
elapsed/scheduled days, post-review stability/difficulty, pre-review
retrievability) — read it via `GET /api/training/review_log`; it is also the
training data for fitting per-user FSRS weights later. Words created before
the FSRS switch have `stability == 0` and are initialized on their next
review.

## Known limitations

- Single-worker assumption: the in-process `storage._storages` cache is not
  shared across uvicorn workers.
- No rate limiting; CORS defaults to `*` (set `CORS_ALLOW_ORIGINS` in prod).
- Debug endpoints are mounted only when `VEKSHA_DEBUG_API=1` (default on for
  localhost, off otherwise).
