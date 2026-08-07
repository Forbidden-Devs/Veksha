"""
main.py — FastAPI app entry point for Veksha backend.

Endpoints are split by domain into api/:
  api/translate.py  — /api/translate, /api/quick_translate, /api/explain
  api/settings.py   — /api/settings, /api/reminders, /api/kb_summary
  api/training.py   — /api/training/*
  api/goal_v2.py    — /api/learning-goals, /api/learning-goals/ws
  api/i18n.py       — /api/i18n/*
  api/debug.py      — /api/debug/*
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import db
from api import auth as api_auth
from api import admin
from api import billing
from api import debug, settings
from api import i18n as api_i18n
from api import goal_v2 as goals
from api import ocr
from api import privacy
from api import reading_coach
from api import pattern_workshop
from api import quizlet
from api import subtitles as api_subtitles
from api import subtitle_study as api_subtitle_study
from api import training_v2 as training
from api import translate_v2 as translate
from api import reading_sessions
from api import speech
from api import vocabulary_inbox
from config import CORS_ALLOW_ORIGINS, DEBUG_API, HOST, LOG_LEVEL, PORT, RELOAD

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


app = FastAPI(title="Veksha Backend", version="0.1.0")

def configure_http(application: FastAPI) -> None:
    application.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_methods=("GET", "POST", "PUT", "DELETE", "OPTIONS"),
        allow_headers=("Authorization", "Content-Type", "X-Veksha-Admin-Secret", "X-Veksha-Bot-Secret"),
    )


configure_http(app)


@app.get("/healthz", include_in_schema=False)
async def healthz():
    """Probe only the durable dependency required to serve user state."""
    try:
        db.healthcheck()
    except Exception as error:
        log.warning("Database health probe failed: %s", type(error).__name__)
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {
        "status": "ok",
        "service": "backend",
        "revision": os.getenv("VEKSHA_REVISION", "local"),
    }


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    """Fallback handler so unhandled 500s carry CORS headers."""
    origin = request.headers.get("origin")
    incident = type(exc).__name__
    log.exception("Unhandled %s on %s", incident, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "incident": incident},
        headers={"Access-Control-Allow-Origin": origin} if origin else {},
    )


app.include_router(api_auth.router)
app.include_router(admin.router)
app.include_router(billing.router)
app.include_router(translate.router)
app.include_router(ocr.router)
app.include_router(settings.router)
app.include_router(training.router)
app.include_router(goals.router)
app.include_router(api_i18n.router)
app.include_router(pattern_workshop.router)
app.include_router(quizlet.router)
app.include_router(reading_sessions.router)
app.include_router(vocabulary_inbox.router)
app.include_router(api_subtitles.router)
app.include_router(api_subtitle_study.router)
app.include_router(privacy.router)
app.include_router(reading_coach.router)
app.include_router(speech.router)
if DEBUG_API:
    app.include_router(debug.router)
    log.warning("Debug API is enabled (/api/debug/*) — do not use in production.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=RELOAD)
