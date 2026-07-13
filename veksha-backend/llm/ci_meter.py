"""llm/ci_meter.py — LLM-based refinement for the Comprehensible Input Meter.

The local frequency-based estimate (textstats.py) is instant and free but
coarse (and unsupported for a few languages). This is the fallback/refine
path: one cheap call that returns just an overall CEFR band and a one-line
note, no per-sentence structure or translation. Cached like llm/immersion.py
so repeat visits and explicit "refine" clicks on the same text are instant.
"""
from __future__ import annotations

import logging

from llm._base import _LANG_NAMES, _call, _parse_json, _truncate
from db_cache import cache_get, cache_set, make_key

log = logging.getLogger(__name__)

_NS = "ci_meter"

_VALID_CEFR = ("A1", "A2", "B1", "B2", "C1", "C2")

_SAMPLE_CHARS = 4000

_SYSTEM = """\
You estimate the reading difficulty of a page of text for a language learner.

The text is written in {target_name}. Rate its OVERALL difficulty as a single \
CEFR level: one of A1, A2, B1, B2, C1, C2 — considering vocabulary, sentence \
complexity and topic. Then write one short, encouraging sentence (in {native_name}) \
telling the learner what to expect if they read it.

Reply ONLY in JSON, no markdown:
{{"cefr":"B1","note":"<one short sentence in {native_name}>"}}
"""


def _lang_name(code: str) -> str:
    return _LANG_NAMES.get(code or "en", (code or "en").upper())


async def classify_difficulty(text: str, native_lang: str, target_lang: str) -> dict:
    """Return {"cefr","note"} for a page-text sample. Empty dict on failure."""
    text = (text or "").strip()[:_SAMPLE_CHARS]
    if not text:
        return {}

    key = make_key(_NS, text, native_lang, target_lang)
    cached = await cache_get(_NS, key)
    if isinstance(cached, dict):
        log.info("[ci_meter] cache hit")
        return cached

    system = _SYSTEM.format(
        native_name=_lang_name(native_lang),
        target_name=_lang_name(target_lang),
    )
    try:
        raw = await _call(
            system,
            user=text,
            max_tokens=150,
            json_mode=True,
            call_name="ci_meter_classify",
        )
        data = _parse_json(raw)
    except Exception as exc:  # noqa: BLE001 — degrade to the local estimate, never break the badge
        log.error("[ci_meter] classification failed: %s | text=%r", exc, _truncate(text))
        return {}

    cefr = str(data.get("cefr", "")).upper().strip()
    if cefr not in _VALID_CEFR:
        return {}
    note = str(data.get("note", "") or "").strip()

    result = {"cefr": cefr, "note": note}
    await cache_set(_NS, key, result)
    return result
