"""
llm/immersion.py — "comprehensible input" page immersion.

Given a chunk of page text, the LLM:
  1. splits it into sentences (kept verbatim so the client can locate them),
  2. rates each sentence's CEFR difficulty (A1-C2),
  3. translates ONLY the sentences at the learner's level or one step above
     (i+1) into the language being studied.

Results are cached per (block text, native, target, level) so revisits and
re-scrolls are instant.
"""
from __future__ import annotations

import json
import logging

from llm._base import _LANG_NAMES, _call, _clean_json, _truncate
from db_cache import cache_get, cache_set, make_key

log = logging.getLogger(__name__)

_NS = "immersion"

_VALID_CEFR = ("A1", "A2", "B1", "B2", "C1", "C2")

_SYSTEM = """\
You embed "comprehensible input" into a web page for a language learner.

The learner's CEFR level is {level}. They are studying {target_name} and the \
page text is written in {native_name}.

You receive one chunk of page text. Do the following:

1. Split it into individual sentences, in their ORIGINAL order. Keep each \
"text" EXACTLY as it appears in the chunk (same words, punctuation, spacing and \
casing) so it can be located in the page. Do not merge or rephrase.
2. For each sentence estimate how hard it would be to read in {target_name}: one \
of A1, A2, B1, B2, C1, C2.
3. Translate into {target_name} ONLY the sentences whose difficulty equals the \
learner's level ({level}) or is exactly ONE step above it (i+1 — challenging but \
comprehensible). For every other sentence set "translation" to "".

Never translate fragments that are not real sentences (navigation labels, single \
words, code, URLs, pure numbers): set their "translation" to "".

Reply ONLY in JSON, no markdown:
{{"sentences":[{{"text":"<original sentence>","cefr":"B1","translation":"<{target_name} translation or empty string>"}}]}}
"""


def _lang_name(code: str) -> str:
    return _LANG_NAMES.get(code or "en", (code or "en").upper())


async def analyze_block(
    text: str,
    native_lang: str,
    target_lang: str,
    level: str,
) -> list[dict]:
    """
    Return [{"text","cefr","translation"}] for one chunk of page text.
    `translation` is non-empty only for in-band (i+1) sentences.
    """
    text = (text or "").strip()
    if not text:
        return []

    key = make_key(_NS, text, native_lang, target_lang, level)
    cached = await cache_get(_NS, key)
    if isinstance(cached, list):
        log.info("[immersion] cache hit (%d sentences)", len(cached))
        return cached

    system = _SYSTEM.format(
        level=level,
        native_name=_lang_name(native_lang),
        target_name=_lang_name(target_lang),
    )
    try:
        raw = await _call(
            system,
            user=text,
            max_tokens=2000,
            json_mode=True,
            call_name="immersion_analyze",
        )
        data = json.loads(_clean_json(raw))
    except Exception as exc:  # noqa: BLE001 — degrade gracefully, never break the page
        log.error("[immersion] analysis failed: %s | text=%r", exc, _truncate(text))
        return []

    sentences: list[dict] = []
    for item in data.get("sentences", []):
        if not isinstance(item, dict):
            continue
        sent = str(item.get("text", "")).strip()
        if not sent:
            continue
        cefr = str(item.get("cefr", "")).upper().strip()
        if cefr not in _VALID_CEFR:
            cefr = ""
        translation = str(item.get("translation", "") or "").strip()
        # Drop no-op translations (LLM sometimes echoes the source).
        if translation and translation.casefold() == sent.casefold():
            translation = ""
        sentences.append({"text": sent, "cefr": cefr, "translation": translation})

    await cache_set(_NS, key, sentences)
    return sentences
