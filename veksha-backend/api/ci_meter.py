"""
api/ci_meter.py — Comprehensible Input Meter.

  POST /api/ci_meter/analyze — given a sample of page text, report the % of
  vocabulary the user already knows, an overall CEFR estimate, and an i+1
  verdict, so they can judge whether a page is worth reading before diving in.

Uses the instant local frequency-based estimate (textstats.py) by default;
falls back to (or is explicitly refined by) a single cheap LLM call
(llm.classify_difficulty) when the local estimate has low confidence.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

import llm
import textstats
from auth import CurrentUser
from cefr import band_index, level_to_cefr
from storage import get_storage

log = logging.getLogger(__name__)

router = APIRouter()

_MAX_TEXT_CHARS = 8000


class CiMeterRequest(BaseModel):
    text: str = ""
    refine: bool = False


class CiMeterResponse(BaseModel):
    known_pct: float
    cefr: str
    user_level: str
    verdict: str  # "ideal" | "too_easy" | "too_hard" | "close"
    source: str  # "local" | "llm"
    confidence: str  # "low" | "high"


def _verdict(cefr: str, user_level: str, known_pct: float) -> str:
    gap = band_index(cefr) - band_index(user_level)
    if known_pct >= 0.98:
        return "too_easy"
    if gap >= 2 or known_pct < 0.85:
        return "too_hard"
    if gap == 1 and 0.90 <= known_pct <= 0.97:
        return "ideal"
    return "close"


@router.post("/api/ci_meter/analyze", response_model=CiMeterResponse)
async def api_ci_meter_analyze(req: CiMeterRequest, username: CurrentUser) -> CiMeterResponse:
    storage = get_storage(username)
    s = storage.settings
    native = s.native_lang or "en"
    target = s.target_lang or "en"
    user_level = level_to_cefr(s.english_level)

    text = (req.text or "").strip()[:_MAX_TEXT_CHARS]
    known_overrides = {
        w.name.strip().lower(): bool(w.known)
        for w in storage.words
        if w.language == target
    }

    local = textstats.estimate(text, target, known_overrides, user_level)
    cefr = local.cefr
    source = "local"

    if req.refine or local.confidence == "low":
        refined = await llm.classify_difficulty(text, native, target)
        if refined.get("cefr"):
            cefr = refined["cefr"]
            source = "llm"

    return CiMeterResponse(
        known_pct=round(local.known_pct, 4),
        cefr=cefr,
        user_level=user_level,
        verdict=_verdict(cefr, user_level, local.known_pct),
        source=source,
        confidence=local.confidence,
    )
