"""
main.py — FastAPI app entry point for Veksha backend.

Endpoints are split by domain into api/:
  api/translate.py  — /api/translate, /api/quick_translate, /api/explain
  api/settings.py   — /api/settings, /api/reminders, /api/kb_summary
  api/training.py   — /api/training/*
  api/lesson.py     — /api/lesson-topics, /api/lesson/ws
  api/i18n.py       — /api/i18n/*
  api/debug.py      — /api/debug/*
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import i18n
import db
from api import auth as api_auth
from api import admin
from api import billing
from api import debug, settings
from api import immersion_v2 as immersion
from api import i18n as api_i18n
from api import lesson_v2 as lesson
from api import privacy
from api import reading_coach
from api import grammar_lens
from api import quizlet
from api import subtitles as api_subtitles
from api import training_v2 as training
from api import translate_v2 as translate
from api import vocab_frequency
from api import vocabulary_inbox
from config import CORS_ALLOW_ORIGINS, DEBUG_API, HOST, LOG_LEVEL, PORT, RELOAD

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(_: FastAPI):
    for lang in sorted(i18n.known_langs()):
        asyncio.create_task(i18n.ensure_cache_complete(lang))
    yield


app = FastAPI(title="Veksha Backend", version="0.1.0", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz", include_in_schema=False)
async def healthz():
    """Lightweight Railway healthcheck without external API calls."""
    try:
        db.healthcheck()
    except Exception:
        log.exception("Backend healthcheck failed")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "service": "backend"},
        )
    return {
        "status": "ok",
        "service": "backend",
        "revision": os.getenv("RAILWAY_GIT_COMMIT_SHA", "local"),
    }


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    """Fallback handler so unhandled 500s carry CORS headers."""
    origin = request.headers.get("origin", "*")
    log.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
        headers={"Access-Control-Allow-Origin": origin},
    )


app.include_router(api_auth.router)
app.include_router(admin.router)
app.include_router(billing.router)
app.include_router(translate.router)
app.include_router(settings.router)
app.include_router(training.router)
app.include_router(lesson.router)
app.include_router(api_i18n.router)
app.include_router(immersion.router)
app.include_router(grammar_lens.router)
app.include_router(quizlet.router)
app.include_router(vocab_frequency.router)
app.include_router(vocabulary_inbox.router)
app.include_router(api_subtitles.router)
app.include_router(privacy.router)
app.include_router(reading_coach.router)
if DEBUG_API:
    app.include_router(debug.router)
    log.warning("Debug API is enabled (/api/debug/*) — do not use in production.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=RELOAD)
