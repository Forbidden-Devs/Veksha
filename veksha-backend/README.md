# Veksha Backend (FastAPI)

HTTP + WebSocket API for the Veksha extension: vocabulary knowledge base
with spaced repetition, LLM-backed translation/explanation, word-training and
topic-lesson sessions, and an actionable Reading Coach.

## Running

```bash
docker compose -f ../compose.yaml up -d postgres
pip install -r requirements.txt
export OPENAI_API_KEY="sk-..."    # required
export DATABASE_URL="postgresql://veksha:veksha@localhost:5432/veksha"
python main.py                     # or: uvicorn main:app --reload
```

Listens on `127.0.0.1:8000` by default. Swagger UI: `http://127.0.0.1:8000/docs`.

Required env vars: `OPENAI_API_KEY`, `DATABASE_URL`.

Optional env vars: `OPENAI_MODEL`, `OPENAI_SMART_MODEL`, `REDIS_URL`
(shared translation cache), `HOST`, `PORT`, `LOG_LEVEL`,
`VEKSHA_DATA_DIR` (downloaded runtime files), `CORS_ALLOW_ORIGINS`,
`VEKSHA_DEBUG_API`, `DATABASE_POOL_MIN_SIZE`, `DATABASE_POOL_MAX_SIZE`.

Region translation uses `GOOGLE_CLOUD_VISION_API_KEY` for primary OCR when it
is configured and falls back to OpenAI vision. Select the fallback model with
`VEKSHA_OCR_VISION_MODEL` (default `gpt-5.6-luna`). Only the crop selected by
the user is sent to `/api/ocr/translate-region`.

The independently rewritten translation core is the only translation
implementation. Its model can be selected with
`VEKSHA_CORE_V2_TRANSLATION_MODEL` (default `gpt-5.6-luna`).

Dictionary-card enrichment for `/api/kb_word` and `/api/kb_word_details` uses
the rewritten use case. Select its model through
`VEKSHA_CORE_V2_DICTIONARY_MODEL` (default `gpt-5.6-luna`).

Sentence Mining cards for `/api/kb_word_mine` always use the new core. Configure
their model with
`VEKSHA_CORE_V2_SENTENCE_MINING_MODEL` (default `gpt-5.6-luna`).

Vocabulary extraction from translated multi-word selections is enabled by
default. `VEKSHA_PHRASE_MINING_ENABLED=0` is an operational cost-control switch;
it does not select a legacy implementation. The model is selected by
`VEKSHA_CORE_V2_PHRASE_MINING_MODEL` (default `gpt-5.6-luna`).

Vocabulary acquisition is learner-controlled. Single-word lookups and
phrase-mining candidates go to the vocabulary
inbox instead of directly entering the review queue. The learner must choose
Learn, Known, or Ignore in My Words. Source URLs are stored without query
parameters or fragments.

`LexicalItem` is the persisted and trained vocabulary unit. Each normalized
term/language/meaning combination has a stable `item_id` and its own FSRS
schedule. Legacy `Word` records migrate on load to `schema_version: 2`; the
backend no longer writes a `words` projection or merges homonymous meanings.

The rewritten training core is the only training implementation. Its Responses
API model is configured via
`VEKSHA_CORE_V2_TRAINING_MODEL` (default `gpt-5.6-terra`).

Practice is planned, not drawn at random — see
[Adaptive Practice Planner](#adaptive-practice-planner) below.

The rewritten topic-lesson core keeps `/api/lesson-topics` and
`/api/lesson/ws` unchanged. Select its model with
`VEKSHA_CORE_V2_LESSON_MODEL` (default `gpt-5.6-terra`). Existing lesson data
is mapped at the storage boundary.

Reading Coach estimates page difficulty from CEFR bands and the learner's
LexicalItem collection, identifies high-impact blockers, and prepares selected
terms in the Vocabulary Inbox. It uses `/api/reading-coach/analyze` and
`/api/reading-coach/prepare`. Page assessment is free; vocabulary preparation,
paragraph help, and comprehension questions use the existing paid entitlement.
Comprehension uses `VEKSHA_CORE_V2_READING_MODEL` (default `gpt-5.6-luna`).
The stable `immersion` billing identifier is
retained only so existing purchases continue to unlock Reading Coach.

Grammar Memory analysis is independently implemented and grounds every segment
and annotation in the submitted text before saving examples. Its model is
selected through `VEKSHA_CORE_V2_GRAMMAR_MODEL` (default `gpt-5.6-luna`). The
existing `POST /api/grammar-lens/analyze` route and `grammar_lens` entitlement
remain compatible.

Dual subtitles use the rewritten structured-output translator. Alignment is
validated against the submitted token counts and partial batches retry only
missing cues. A bounded process-local cache avoids retaining subtitle text in
PostgreSQL. Select the model with `VEKSHA_CORE_V2_SUBTITLES_MODEL` (default
`gpt-5.6-luna`).

Generated UI catalogues use the rewritten catalogue translator. Unknown keys,
empty values, and translations that alter placeholders such as `{name}` are
discarded. Select its model with `VEKSHA_CORE_V2_I18N_MODEL` (default
`gpt-5.6-luna`).

Local runs grant premium-gated development features automatically, so dual
subtitles, Grammar Memory, and Reading Coach can be exercised without Telegram
billing. Set `VEKSHA_DEV_ALL_FEATURES=0` to test the real free-tier gates.

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

All user data (accounts and KBs) lives in PostgreSQL. The KB remains one
versioned JSON document per user; `LexicalItem` schedules are embedded per
meaning while review events live in the relational `review_log` table.

To copy a previous SQLite installation, stop the backend and run:

```bash
export DATABASE_URL="postgresql://..."
python scripts/migrate_sqlite_to_postgres.py --data-dir ./data
```

The reusable LLM cache also lives in PostgreSQL. Redis remains optional and is
used only as an additional cache for one- and two-word translations. For local
testing it can be enabled with
`docker compose -f ../compose.yaml --profile cache up -d` and
`REDIS_URL=redis://localhost:6379/0`.

## Subscriptions (Telegram Stars)

Paid features (Grammar Memory, Reading Coach, dual subtitles — see
`entitlements.py`) can be purchased individually; gated endpoints return
HTTP 402 with `detail.code = "subscription_required"`. Payments are collected
by the companion bot (`veksha-tgbot/`) in Telegram Stars and reported to
`POST /api/billing/telegram/webhook` (header `X-Veksha-Bot-Secret`,
idempotent by `telegram_payment_charge_id`). Accounts are bound to Telegram
via a single-use deep-link code from `POST /api/billing/telegram/link`. Its
`features` body locks a checkout snapshot and the sum of the per-feature
monthly prices stored in PostgreSQL before Telegram opens.
Configure `TELEGRAM_BOT_USERNAME` and `TELEGRAM_BOT_WEBHOOK_SECRET`; both
empty disables billing (the link endpoint returns 503, everyone stays on the
free tier).

Accounts default to the free tier. For manual test grants (e.g. beta
testers), mint a promo code with `ADMIN_API_SECRET` set and:

```
curl -X POST $API/api/billing/promo/create \
  -H "X-Veksha-Admin-Secret: $ADMIN_API_SECRET" -H "Content-Type: application/json" \
  -d '{"code": "BETA30", "days": 30, "max_redemptions": 20, "features": ["grammar_lens"]}'
```

Users redeem it once each via `POST /api/billing/promo/redeem` (Bearer
token, body `{"code": "..."}`) for `days` of the selected features. Omit
`features` when creating a promo to grant all paid features.

Change a monthly feature price for future checkouts with the admin endpoint:

```
curl -X PUT $API/api/billing/features/immersion/price \
  -H "X-Veksha-Admin-Secret: $ADMIN_API_SECRET" -H "Content-Type: application/json" \
  -d '{"stars_monthly": 35}'
```

## Module map

```
main.py               app entry point, routers, CORS, error handler
config.py             env-based configuration
db.py                 PostgreSQL: users/tokens, KB documents, review log
auth.py               bearer-token dependencies (HTTP + WebSocket)
models.py             transitional settings/lesson/message records
storage.py            adapters for the versioned user knowledge document
fsrs.py               FSRS-4.5 scheduler (pure functions; default weights)
learning_core_v2/     independent domain use cases
learning_core_v2_adapters/ HTTP/storage/LLM adapters for the new core
i18n.py               UI/server strings + LLM-translated catalogues
entitlements.py       subscription tiers, plans, feature gating (require_feature)
api/                  routers (one file per domain)
```

## Endpoints

| Route | Purpose |
|---|---|
| `POST /api/auth/register` | create account, returns bearer token |
| `POST /api/auth/google/start`, `/api/auth/google/link/start` | start Google sign-in / identity link |
| `GET /api/auth/google/callback`, `GET /api/auth/google/*/status/{flow_id}` | Google HTTPS callback / one-time result |
| `POST /api/translate`, `/api/quick_translate` | selection translation (+background KB update) |
| `POST /api/explain` | expanded explanation for a selection |
| `GET/POST /api/settings` | user settings |
| `GET /api/reminders` | due words / topics for extension alarms |
| `GET /api/kb_summary`, `/api/kb_words`, `DELETE /api/kb_word` | vocabulary UI |
| `GET /api/training/init`, `POST /api/training/validate`, `WS /api/training/ws` | word training |
| `GET /api/training/review_log` | recent FSRS reviews (`?item_id=`, `?word=`, `?limit=`) |
| `GET/POST /api/lesson-topics`, `WS /api/lesson/ws` | topic lessons |
| `POST /api/reading-coach/analyze` | page readiness and vocabulary blockers (premium) |
| `POST /api/reading-coach/prepare` | enrich selected blockers into the Vocabulary Inbox (premium) |
| `POST /api/subtitles/translate` | dual-subtitle line translation with word alignment (premium) |
| `POST /api/subtitles/translate-batch` | contextual pretranslation of adjacent timed subtitle cues (premium) |
| `GET /api/billing/status`, `GET /api/billing/features` | active selection / feature prices |
| `POST /api/billing/telegram/link`, `DELETE /api/billing/subscription` | checkout deep link / cancel subscription |
| `POST /api/billing/promo/redeem` | redeem a promo code for temporary Premium |
| `GET /api/billing/plans`, `POST /api/billing/telegram/webhook` | companion-bot API (shared secret) |
| `POST /api/billing/promo/create` | mint a promo code (admin shared secret) |
| `GET /api/billing/admin/overview` | read feature prices and recent promo codes (admin shared secret) |
| `PUT /api/billing/features/{feature}/price` | change a feature price (admin shared secret) |
| `GET /api/i18n/{lang}`, `POST /api/i18n/translate` | UI string catalogues |
| `POST /api/debug/*` | development helpers (reset, simulate, advance-day) |

WebSocket protocols are documented in the module docstrings of
`api/training_v2.py` and `api/lesson_v2.py`.

## Adaptive Practice Planner

`learning_core_v2/practice.py` plans each exercise as a triple — lexical sense
× trained skill × a task format that can train it — instead of taking the next
due word and a random format.

Every sense tracks four skills independently (`learning_core_v2/skills.py`):
`recognition`, `recall`, `contextual_meaning`, `listening`. Each holds its own
attempts, errors, streak, last-practice time, and a confidence that is an
exponential moving average over the four FSRS ratings. FSRS still decides
*when* a sense returns; the planner decides *which of its skills is weakest
right now*. Senses stored before the planner have no profile and start
neutral (0.5), so they rank by their schedule rather than as failures.

The planner scores the due queue on review urgency, skill weakness, recent
errors, formats already used this session, and the material each format needs
— a reverse translation needs a saved translation, a context task needs an
observed sentence, a listening task needs a client that can speak. Listening
audio is voiced by the client through the Web Speech API; the client declares
`audio` support in the `init` message and the planner omits listening
otherwise. Each task carries a structured `reason` the client localizes into
"why am I seeing this".

A wrong answer opens a bounded corrective chain rather than only lowering the
interval: the right answer plus a specific error note, an eased task on the
same skill, then a transfer check using a different format and a fresh
example. The chain is capped at `MAX_CORRECTION_STEPS` per sense, and a failed
support step ends it. Corrective tasks move skill confidence only — the sense
was already rescheduled by the review that triggered the repair, so
rescheduling again would distort the interval.

Answers are graded in two steps over the socket: `answer` returns the verdict
and a suggested rating, `commit` applies it. Nothing reaches FSRS until the
commit, so the learner can override the suggestion.

## Spaced repetition (FSRS)

Scheduling is FSRS-4.5 (`fsrs.py`, published default weights). Each lexical
meaning carries its own memory state — `stability` (interval in days at 90%
recall), `difficulty` (1–10), `last_review`, `lapses` — updated per review from
a graded rating that uses all four FSRS values
(`learning_core_v2.practice.suggest_rating`): `incorrect` → Again, `vague` →
Hard, and a correct answer → Easy when it arrives quickly with no help, Hard
when it needed a hint, a repair, or an unusually long pause, Good otherwise
(`garbage` is not a review). Response-time windows are per format, so picking
an option is held to a tighter clock than writing a sentence. The learner may
replace the suggested rating before it is committed. Surfaces that only
produce a verdict, such as the Anki-style `/api/kb_word_review`, still map
`outcome` directly via `fsrs.outcome_to_rating`.
`next_review = now + interval` for
`config.FSRS_DESIRED_RETENTION` (0.9), clamped to
`FSRS_MIN/MAX_INTERVAL_DAYS`. A lexical item is due once `next_review` is less than
`REVIEW_WINDOW_HOURS` away or overdue — lateness needs no special handling
because low retrievability at review time yields a bigger stability jump.
Overdue items only get `delayed=True`. `counter`
survives as the review count (`-1` = new, drives the UI badge).

Every review appends to the `review_log` table (rating, outcome, task type,
elapsed/scheduled days, post-review stability/difficulty, pre-review
retrievability and `lexical_item_id`) — read it via
`GET /api/training/review_log`; it is also the training data for fitting
per-user FSRS weights later. Migrated items without an FSRS state are
initialized on their next review.

## Known limitations

- Single-worker assumption: the in-process `storage._storages` cache is not
  shared across uvicorn workers.
- No rate limiting; CORS defaults to `*` (set `CORS_ALLOW_ORIGINS` in prod).
- Debug endpoints are mounted only when `VEKSHA_DEBUG_API=1` (default on for
  localhost, off otherwise).
