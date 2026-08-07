# Veksha Backend (FastAPI)

HTTP + WebSocket API for the Veksha extension: vocabulary knowledge base
with spaced repetition, LLM-backed translation/explanation, word-training and
goal-oriented lesson sessions, and an actionable Reading Coach.

## Running

```bash
docker compose -f ../compose.yaml up -d postgres
pip install -r requirements.txt
export OPENAI_API_KEY="sk-..."    # required
export DATABASE_URL="postgresql://veksha:veksha@localhost:5432/veksha"
python main.py                     # or: uvicorn main:app --reload
```

Listens on `127.0.0.1:8000` by default. Swagger UI: `http://127.0.0.1:8000/docs`.

Required env vars: `OPENAI_API_KEY`, `DATABASE_URL`. Speech features additionally
require `SPEECH_SHARED_SECRET` and `SPEECH_DEFAULT_VOICE_ID`.

Optional env vars: `OPENAI_MODEL`, `OPENAI_SMART_MODEL`, `REDIS_URL`
(shared translation cache), `HOST`, `PORT`, `LOG_LEVEL`,
`VEKSHA_DATA_DIR` (downloaded runtime files), `CORS_ALLOW_ORIGINS`,
`VEKSHA_DEBUG_API`, `DATABASE_POOL_MIN_SIZE`, `DATABASE_POOL_MAX_SIZE`.

Speech is an external HTTP dependency; Veksha neither imports its code nor
accesses its database. Configure `SPEECH_BASE_URL` (default
`http://localhost:8080`) and `SPEECH_TIMEOUT` (default `60s`). The
consumer shared secret and current provider-specific default voice stay in the backend
environment. The browser calls only Veksha's authenticated `/api/speech/*`
routes. TTS remains binary throughout and is streamed through the backend;
temporary `429`, `502`, and `503` responses are retried before streaming begins.
Successful response units from `X-Speech-*` are persisted per Veksha user in
`speech_usage`; streamed TTS bytes are counted locally when trailers are unavailable.

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

Lessons are goal-oriented: a stated result becomes checkable criteria, and the
next step is chosen from the last answer rather than from a fixed list of
blocks — see [Goal-Oriented Lessons](#goal-oriented-lessons) below. Select the
model with `VEKSHA_CORE_V2_LESSON_MODEL` (default `gpt-5.6-terra`).

Reading Coach estimates page difficulty from CEFR bands and the learner's
LexicalItem collection, identifies high-impact blockers, and prepares selected
terms in the Vocabulary Inbox. It uses `/api/reading-coach/analyze` and
`/api/reading-coach/prepare`. Page assessment is free; vocabulary preparation,
paragraph help, and comprehension questions use the existing paid entitlement.
Comprehension uses `VEKSHA_CORE_V2_READING_MODEL` (default `gpt-5.6-luna`).
The stable `immersion` billing identifier is
retained only so existing purchases continue to unlock Reading Coach.

Pattern Workshop analysis is independently implemented and grounds every segment
and annotation in the submitted text before saving examples. Its model is
selected through `VEKSHA_CORE_V2_GRAMMAR_MODEL` (default `gpt-5.6-luna`). The
the Pattern Workshop API and its `pattern_workshop` entitlement
remain compatible.

Dual subtitles use the rewritten structured-output translator. Alignment is
validated against the submitted token counts and partial batches retry only
missing cues. A bounded process-local cache avoids retaining subtitle text in
PostgreSQL. Select the model with `VEKSHA_CORE_V2_SUBTITLES_MODEL` (default
`gpt-5.6-luna`).

Subtitle study sessions (`learning_core_v2/subtitle_study.py`) build on the same
track. A dialogue line is addressed by a stable temporal id derived from
`(media_key, start_ms, text)`, so clients only ever send cues; a saved word, a
comprehension check and a generated cloze all carry the timecode they came from.
Two of the six comprehension checks — "which word was spoken" and "which line
continues" — are assembled from the caption track itself and never reach a
model; the other four are authored through
`VEKSHA_CORE_V2_SUBTITLE_STUDY_MODEL` (default `gpt-5.6-luna`) and graded server
side, so a client never receives the expected answer before it answers. Sessions
persist in the user document under `subtitle_sessions` and resume on the line
they stopped on.

Generated UI catalogues use the rewritten catalogue translator. Unknown keys,
empty values, and translations that alter placeholders such as `{name}` are
discarded. Select its model with `VEKSHA_CORE_V2_I18N_MODEL` (default
`gpt-5.6-luna`).

Local runs grant premium-gated development features automatically, so dual
subtitles, Pattern Workshop, and Reading Coach can be exercised without Telegram
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

Paid features (Pattern Workshop, Reading Coach, dual subtitles — see
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
  -d '{"code": "BETA30", "days": 30, "max_redemptions": 20, "features": ["pattern_workshop"]}'
```

New promo codes start paused. Launch one from the admin panel or with:

```
curl -X PUT $API/api/billing/promo/BETA30/pause \
  -H "X-Veksha-Admin-Secret: $ADMIN_API_SECRET" -H "Content-Type: application/json" \
  -d '{"paused": false}'
```

Users can then redeem it once each via `POST /api/billing/promo/redeem`
(Bearer token, body `{"code": "..."}`) for `days` of the selected features.
Omit `features` when creating a promo to grant all paid features.

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
models.py             transitional settings records
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
| `POST /api/speech/synthesize` | stream configured-platform TTS audio |
| `POST /api/speech/transcribe` | transcribe a PCM WAV recording (up to the platform's 30-second limit) |
| `GET/POST /api/settings` | user settings |
| `GET /api/reminders` | due words / unfinished goals for extension alarms |
| `GET /api/kb_summary`, `/api/kb_words`, `DELETE /api/kb_word` | vocabulary UI |
| `GET /api/training/init`, `POST /api/training/validate`, `WS /api/training/ws` | word training |
| `GET /api/training/review_log` | recent FSRS reviews (`?item_id=`, `?word=`, `?limit=`) |
| `GET/POST /api/learning-goals`, `DELETE /api/learning-goals/{goal_id}`, `WS /api/learning-goals/ws` | goal-oriented lessons |
| `POST /api/reading-coach/analyze` | page readiness and vocabulary blockers (premium) |
| `POST /api/reading-coach/prepare` | enrich selected blockers into the Vocabulary Inbox (premium) |
| `POST /api/subtitles/translate` | dual-subtitle line translation with word alignment (premium) |
| `POST /api/subtitles/translate-batch` | contextual pretranslation of adjacent timed subtitle cues (premium) |
| `POST /api/subtitle-study/session`, `.../{id}/progress`, `.../{id}/display` | start or resume a study session, flush watched/replay events, change what is shown (premium) |
| `GET /api/subtitle-study/session/{id}/summary`, `POST .../{id}/close` | session difficulties, with and without closing (premium) |
| `POST /api/subtitle-study/fragment` | padded replay window for one dialogue line (premium) |
| `POST /api/subtitle-study/comprehension/question`, `.../check` | ask and grade a question about a real fragment (premium) |
| `POST /api/subtitle-study/word/senses`, `POST /api/subtitle-study/word` | meanings a form already carries / save one sense with its timecode (premium) |
| `POST /api/subtitle-study/cloze` | fill-in-the-blank generated from the spoken line (premium) |
| `GET /api/billing/status`, `GET /api/billing/features` | active selection / feature prices |
| `POST /api/billing/telegram/link`, `DELETE /api/billing/subscription` | checkout deep link / cancel subscription |
| `POST /api/billing/promo/redeem` | redeem a promo code for temporary Premium |
| `GET /api/billing/plans`, `POST /api/billing/telegram/webhook` | companion-bot API (shared secret) |
| `POST /api/billing/promo/create` | mint a promo code (admin shared secret) |
| `PUT /api/billing/promo/{code}/pause` | pause or resume a promo code (admin shared secret) |
| `GET /api/billing/admin/overview` | read feature prices and recent promo codes (admin shared secret) |
| `PUT /api/billing/features/{feature}/price` | change a feature price (admin shared secret) |
| `GET /api/i18n/{lang}`, `POST /api/i18n/translate` | UI string catalogues |
| `POST /api/debug/*` | development helpers (reset, simulate, advance-day) |

WebSocket protocols are documented in the module docstrings of
`api/training_v2.py` and `api/goal_v2.py`.

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
audio uses Speech Platform through the Veksha backend in popup/web contexts,
with the Web Speech API as an availability fallback. The client declares
`audio` support in the `init` message and the planner omits listening otherwise.
Each task carries a structured `reason` the client localizes into
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

## Goal-Oriented Lessons

`learning_core_v2/goal.py` starts a lesson from a result the learner wants —
"understand Past Perfect in stories", "get ready for the client call", "work
through this article" — rather than from a topic sliced into a fixed list of
blocks.

**Checkable criteria.** "Learn Past Perfect" is not a stop condition. `FrameGoal`
turns the wish into ordered criteria the learner can demonstrate in one answer
— recognize the form, explain the sequence, tell it apart from Past Simple, use
it in a fresh story — each with a depth of 1–4. Depth sets the minimum demand
that counts: recognizing a form never proves you can write with it, so a
depth-4 criterion is only met by a productive answer. The domain rejects a
framing with nothing to demonstrate and always keeps one criterion at
production depth.

**Evidence, not verdicts.** One answer never settles a criterion. Every answer
is stored as `Evidence` carrying the outcome *and* why it went that way:
`unknown_term`, `missed_signal`, `rule_not_applied`, `lucky_guess`,
`explains_not_produces`, `transfers_confidently`, `unclear`. Status is derived
from the whole run — a right answer the learner cannot account for moves a
criterion far less than one they can explain, and a criterion counts as met
only after several answers with at least one correct at the required demand.

**Routing from the last answer.** `GoalRoute` is pure: given the goal and its
evidence it names the next criterion, the next activity, and the reason. The
first step diagnoses near the top of the goal, so clearing it marks the
shallower criteria `implied` and the lesson never walks a capable learner back
through basic theory; missing it drops the route to the shallowest untested
criterion. After that the route repairs the *cause* — a blocking word leads to
a worked example, an unnoticed cue to finding the phenomenon in the learner's
own text, an unapplied rule to fixing a wrong sentence, a guess to a re-probe
in a different shape, "explains but cannot build" to writing their own example.
The same activity is never used twice in a row, and `find_in_material` is only
planned when the goal has source material.

Activities span `find_in_material`, `explain_example`, `compare_forms`,
`correct_error`, `predict_continuation`, `paraphrase`, `create_example`,
`role_reply`, and `apply_unaided`. A goal is reached only when every criterion
is settled *and* the deepest one has been demonstrated unaided.

**Closing and resuming.** A session ends when the goal is reached or the chosen
minutes are spent — time accumulates across the whole goal, not one sitting.
The report states what the learner can now do, the evidence behind it, what is
still unstable, examples from their material, and a suggested next goal. Words
and grammar patterns the lesson surfaced go to the Vocabulary Inbox as
`suggested` and to Pattern Workshop; the lesson decides nothing on the learner's
behalf. Criteria, evidence, and the planned next step are persisted, so
reopening a goal resumes the route instead of restarting it.

Steps live server-side keyed by `step_id`: the criterion and question a client
echoes back are ignored when the answer is judged. A `garbage` verdict leaves
the step open to answer again and is not written into the evidence.

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
