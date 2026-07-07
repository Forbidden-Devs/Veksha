# Veksha

Learn foreign-language vocabulary from the pages you actually read: select a
word → get a translation → the word becomes a spaced-repetition card
automatically. Plus LLM-generated topic lessons ("blocks") for grammar,
usage patterns, and interview-style topics.

## Repository layout

```
veksha-backend/    FastAPI backend: SQLite storage (users, KB), token auth,
                    spaced repetition, LLM calls (OpenAI), training/lesson
                    WebSocket sessions, translation, immersion, STT proxy.
veksha-extension/  Chrome + Firefox extension (MV3, React + TypeScript,
                    Vite) — the capture surface: selection-translate popup,
                    immersion mode, YouTube subtitles, OCR capture,
                    plus the popup app.
veksha-web/        The same study app (chat / training / lessons / stats)
                    as a standalone PWA-installable web page; reuses the
                    extension popup source via shared/platform.ts.
stt_service.py      Optional local Whisper STT service (dev only).
```

## Quick start

Backend:

```bash
cd veksha-backend
pip install -r requirements.txt
export OPENAI_API_KEY="sk-..."   # required, never commit keys
python main.py                    # http://127.0.0.1:8000, Swagger at /docs
```

Extension (requires Node.js):

```bash
cd veksha-extension
npm install
npm run build                     # both browsers; or build:chrome / build:firefox
# Chrome:  chrome://extensions → Developer mode → Load unpacked → veksha-extension/dist/chrome
# Firefox: about:debugging#/runtime/this-firefox → Load Temporary Add-on → dist/firefox/manifest.json
```

Point the extension at your backend via `src/shared/config.ts`
(`BACKEND_URL`).

## Architecture notes

- User data lives in SQLite (`veksha-backend/data/veksha.db`); clients
  authenticate with a bearer token issued at registration
  (`POST /api/auth/register`).
- All LLM calls live in `veksha-backend/llm/`; business logic that decides
  *when* to call them lives in `pipeline.py`, `training.py`, `lesson.py`,
  `selection.py`.
- Trainings and lessons run over WebSocket (`/api/training/ws`,
  `/api/lesson/ws`); everything else is plain HTTP (see
  `veksha-backend/README.md` for the endpoint list).
- The extension is the *capture* surface; the web app is the *study* surface.
  Extension-only APIs are isolated behind
  `veksha-extension/src/shared/platform.ts` so the popup tree runs in both.
