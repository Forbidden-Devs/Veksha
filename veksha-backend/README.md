# Veksha Backend (FastAPI)

HTTP + WebSocket API for the Veksha extension: vocabulary knowledge base
with spaced repetition, LLM-backed translation/explanation, word-training and
topic-lesson sessions, page immersion, and speech-to-text proxying.

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

## Auth & storage

`POST /api/auth/register {"username"}` issues a bearer token (once). Every
other endpoint requires `Authorization: Bearer <token>`; WebSocket routes take
`?token=`. There is no login/recovery yet — a lost token means a new account
(Google OAuth is the planned replacement).

All user data (accounts, KBs, chat history) lives in SQLite at
`data/veksha.db` (WAL mode). The KB is stored as one JSON document per user;
normalizing into tables is deferred to the FSRS rework.

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
| `POST /api/message` | assistant chat: answer questions or edit the KB |
| `POST /api/translate`, `/api/quick_translate` | selection translation (+background KB update) |
| `POST /api/explain` | expanded explanation for a selection |
| `GET/POST /api/settings` | user settings |
| `GET /api/reminders` | due words / topics for extension alarms |
| `GET /api/kb_summary`, `/api/kb_words`, `DELETE /api/kb_word` | vocabulary UI |
| `GET /api/training/init`, `POST /api/training/validate`, `WS /api/training/ws` | word training |
| `GET /api/training/review_log` | recent FSRS reviews (`?word=`, `?limit=`) |
| `GET/POST /api/lesson-topics`, `WS /api/lesson/ws` | topic lessons |
| `POST /api/immersion/analyze` | comprehensible-input page immersion |
| `POST /api/stt` | microphone speech-to-text (OpenAI proxy) |
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
