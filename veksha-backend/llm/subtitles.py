"""
llm/subtitles.py — dual-subtitle line translation with word alignment.

Given the tokenized original subtitle line, returns the translation as tokens
plus an alignment: which source token(s) correspond to which translation
token(s). The extension renders the translation as a second subtitle row and
highlights the aligned tokens on hover.

Results are cached in db_cache (ns="dualsub") — subtitle lines repeat heavily
(rewatching, several users watching the same video).
"""
from __future__ import annotations

import asyncio
import json
import logging

import db_cache
from llm._base import _call, _clean_json

log = logging.getLogger(__name__)

_SYSTEM = """\
You translate one video-subtitle line from {source_lang} to {target_lang} for a language learner, \
and word-align the translation.

The source line is given as numbered tokens. Reply ONLY with JSON, no markdown:
{{"translation_tokens": ["...", ...], "alignment": [[[si, ...], [ti, ...]], ...], "source_lang": "xx"}}

Rules:
- translation_tokens: the natural translation of the whole line, split into display tokens \
(words with their punctuation attached).
- alignment: pairs [source_token_indices, translation_token_indices]. Group words only when they \
translate as a unit (idioms, phrasal verbs, articles merging into a word). Every source index and \
every translation index should appear in at most one pair; omit tokens that have no counterpart.
- source_lang: ISO 639-1 of the source line (detect it if the given source language is "auto").
- Keep the translation register informal/natural, as film subtitles.
"""

_BATCH_SYSTEM = """\
You translate multiple timed video-subtitle cues from {source_lang} to {target_lang} for a language learner, \
and word-align every translation independently.

Reply ONLY with one JSON object, no markdown:
{{"lines": [{{"index": 0, "translation_tokens": ["..."], \
"alignment": [[[si, ...], [ti, ...]], ...], "source_lang": "xx"}}, ...]}}

Rules:
- Return exactly one item for every input index, using the same index.
- translation_tokens is a natural subtitle translation split into display tokens, with punctuation attached.
- alignment indices are local to that line. Group words only when they translate as a unit.
- Each source and destination index may occur in at most one alignment pair.
- source_lang is ISO 639-1; detect it when the requested source language is "auto".
- Use the surrounding lines as context, but never merge, split, or reorder cues.
- Keep the register concise and natural, as film subtitles.
"""


def _validate(data: dict, n_src: int) -> dict | None:
    """Sanity-check and normalize the LLM output; None if unusable."""
    tokens = data.get("translation_tokens")
    if not isinstance(tokens, list) or not tokens:
        return None
    tokens = [str(t) for t in tokens if str(t).strip()][:60]
    if not tokens:
        return None

    n_dst = len(tokens)
    alignment: list[dict] = []
    seen_src: set[int] = set()
    seen_dst: set[int] = set()
    for pair in data.get("alignment") or []:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            continue
        src, dst = pair
        if not isinstance(src, (list, tuple)) or not isinstance(dst, (list, tuple)):
            continue
        src_idx = sorted({int(i) for i in src if isinstance(i, (int, float)) and 0 <= int(i) < n_src})
        dst_idx = sorted({int(i) for i in dst if isinstance(i, (int, float)) and 0 <= int(i) < n_dst})
        # Enforce "at most one pair per token" — drop groups reusing indices.
        if not src_idx or not dst_idx:
            continue
        if seen_src.intersection(src_idx) or seen_dst.intersection(dst_idx):
            continue
        seen_src.update(src_idx)
        seen_dst.update(dst_idx)
        alignment.append({"src": src_idx, "dst": dst_idx})

    lang = data.get("source_lang")
    return {
        "translation_tokens": tokens,
        "alignment": alignment,
        "detected_source_lang": str(lang)[:8] if isinstance(lang, str) and lang else None,
    }


async def translate_subtitle_line(
    tokens: list[str], source_lang: str, target_lang: str,
) -> dict:
    """
    Returns {"translation_tokens": [...], "alignment": [{"src": [...], "dst": [...]}, ...],
             "detected_source_lang": "xx" | None}.
    Raises on LLM failure (caller maps to an HTTP error).
    """
    cache_key = db_cache.make_key(source_lang, target_lang, " ".join(tokens))
    cached = await db_cache.cache_get("dualsub", cache_key)
    if cached is not None:
        return cached

    numbered = "\n".join(f"{i}: {tok}" for i, tok in enumerate(tokens))
    raw = await _call(
        system=_SYSTEM.format(source_lang=source_lang or "auto", target_lang=target_lang),
        user=numbered,
        max_tokens=700,
        temp=0.1,
        json_mode=True,
        call_name="dualsub",
    )
    result = _validate(json.loads(_clean_json(raw)), n_src=len(tokens))
    if result is None:
        raise ValueError("subtitle translation: unusable LLM output")

    await db_cache.cache_set("dualsub", cache_key, result)
    return result


async def translate_subtitle_batch(
    lines: list[list[str]], source_lang: str, target_lang: str,
) -> list[dict]:
    """Translate several adjacent cues in one model call, retaining per-line alignment."""
    results: list[dict | None] = [None] * len(lines)
    missing: list[int] = []
    cache_keys: list[str] = []
    for index, tokens in enumerate(lines):
        key = db_cache.make_key(source_lang, target_lang, " ".join(tokens))
        cache_keys.append(key)
        cached = await db_cache.cache_get("dualsub", key)
        if cached is None:
            missing.append(index)
        else:
            results[index] = cached

    if missing:
        payload = [
            {"index": index, "tokens": lines[index]}
            for index in missing
        ]
        by_index: dict[int, dict] = {}
        try:
            raw = await _call(
                system=_BATCH_SYSTEM.format(
                    source_lang=source_lang or "auto", target_lang=target_lang,
                ),
                user=json.dumps(payload, ensure_ascii=False),
                max_tokens=max(900, min(4200, 360 * len(missing))),
                temp=0.1,
                json_mode=True,
                call_name="dualsub_batch",
            )
            data = json.loads(_clean_json(raw))
            returned = data.get("lines") if isinstance(data, dict) else None
            if isinstance(returned, list):
                for item in returned:
                    if not isinstance(item, dict) or not isinstance(item.get("index"), int):
                        continue
                    index = item["index"]
                    if index not in missing:
                        continue
                    validated = _validate(item, n_src=len(lines[index]))
                    if validated is not None:
                        by_index[index] = validated
        except Exception as err:
            log.warning("subtitle batch model call failed; falling back per cue: %s", err)

        # A JSON batch can be truncated or omit one difficult line. Preserve
        # every valid result and retry only missing cues instead of failing the
        # whole prefetch window with HTTP 502.
        retry_indices = [index for index in missing if index not in by_index]
        if retry_indices:
            retry_results = await asyncio.gather(*(
                translate_subtitle_line(lines[index], source_lang, target_lang)
                for index in retry_indices
            ))
            by_index.update(zip(retry_indices, retry_results))

        for index in missing:
            result = by_index[index]
            results[index] = result
            await db_cache.cache_set("dualsub", cache_keys[index], result)

    if any(result is None for result in results):
        raise ValueError("subtitle batch translation: incomplete results")
    return [result for result in results if result is not None]
