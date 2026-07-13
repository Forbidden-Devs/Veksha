"""LLM grammar-role analysis for Grammar Lens page highlighting."""
from __future__ import annotations

import json
import logging

from db_cache import cache_get, cache_set, make_key
from llm._base import _LANG_NAMES, _call, _clean_json, _truncate

log = logging.getLogger(__name__)

_NS = "grammar_lens"
VALID_ROLES = frozenset({"subject", "verb", "object", "place", "time", "modifier"})

_SYSTEM = """\
You are a multilingual grammar parser for a reading-assistance browser tool.

Analyze the page-text chunk in whatever language it is written. Return only the
most useful grammatical spans, preserving their text EXACTLY (same spelling,
punctuation, whitespace and casing) so each span can be found verbatim in the
source. Spans must be non-overlapping and in source order.

Allowed roles:
- subject: who or what performs/is described by the clause
- verb: the complete verb or verb phrase, including auxiliaries when adjacent
- object: direct or indirect object/complement
- place: phrase expressing location or direction
- time: phrase expressing time, duration or frequency
- modifier: important adjective/adverb phrase that adds manner or description

Prefer clause-level phrases over isolated tokens. Do not classify punctuation,
navigation, URLs, code, or fragments without meaningful grammar. Do not include
the same source characters twice. Keep explanations very short and write them
in {native_name}.

Reply ONLY in JSON, no markdown:
{{"segments":[{{"text":"exact source span","role":"subject","explanation":"short explanation"}}]}}
"""


def _lang_name(code: str) -> str:
    return _LANG_NAMES.get(code or "en", (code or "en").upper())


def _normalise_segments(text: str, items: object) -> list[dict[str, str]]:
    """Validate roles and exact, non-overlapping source order."""
    if not isinstance(items, list):
        return []
    result: list[dict[str, str]] = []
    cursor = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        segment = str(item.get("text", ""))
        role = str(item.get("role", "")).lower().strip()
        if not segment.strip() or role not in VALID_ROLES:
            continue
        index = text.find(segment, cursor)
        if index < 0:
            continue
        result.append({
            "text": segment,
            "role": role,
            "explanation": str(item.get("explanation", "") or "").strip()[:160],
        })
        cursor = index + len(segment)
    return result


async def analyze_grammar_block(text: str, native_lang: str) -> list[dict[str, str]]:
    text = text or ""
    if not text.strip():
        return []

    key = make_key(_NS, text, native_lang)
    cached = await cache_get(_NS, key)
    if isinstance(cached, list):
        return _normalise_segments(text, cached)

    try:
        raw = await _call(
            _SYSTEM.format(native_name=_lang_name(native_lang)),
            user=text,
            max_tokens=1800,
            json_mode=True,
            call_name="grammar_lens_analyze",
        )
        data = json.loads(_clean_json(raw))
        segments = _normalise_segments(text, data.get("segments", []))
    except Exception as exc:  # noqa: BLE001 — page enhancement must fail quietly
        log.error("[grammar_lens] analysis failed: %s | text=%r", exc, _truncate(text))
        return []

    await cache_set(_NS, key, segments)
    return segments
