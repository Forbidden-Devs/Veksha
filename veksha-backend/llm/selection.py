"""
llm/selection.py — LLM calls for the text selection (translation popup).

  translate_selection — translate + classify single/not-single + normalize
  explain_selection   — "More details" button: expanded explanation with examples
"""
from __future__ import annotations

import json
import logging

from llm._base import _LANG_NAMES, _call, _clean_json, _truncate
from translation_cache import get_translation, set_translation
from db_cache import cache_get, cache_set, make_key

log = logging.getLogger(__name__)


_TRANSLATE_SELECTION_SYSTEM = """\
You are a translator built into a browser extension for a language learner \
(level: {level}).

Translate the user's text from {source_name} to {target_name}.

Also determine:
- "single": true if the selection is ONE word, phrasal verb, or fixed expression \
(e.g. "running", "an apple", "give up", "by the way"). \
false if it is an extended phrase/sentence/text.
- "normalized_text": ONLY if single == true — the same word/expression restored to its \
dictionary form without typos or grammatical distortions in the source language \
(e.g. "runing" -> "run", "the apples" -> "apple", "went" -> "go"). \
If single == false — empty string "".
- "detected_source_lang": two-letter ISO 639-1 code of the source text's language \
(detect independently of what is specified as source).

Translation rules:
- If single == true — give the most natural dictionary translation (as in a dictionary), \
not a word-by-word one.
- If single == false — translate the full text, preserving tone and meaning.

Reply ONLY in JSON without markdown:
{{"translation": "...", "single": true|false, "normalized_text": "...", \
"detected_source_lang": "xx"}}
"""

_BIDIRECTIONAL_TRANSLATE_SYSTEM = """\
You are a bidirectional translator built into a browser extension for a language learner \
(level: {level}).

The user's language pair is {native_name} and {target_name}.
Detect which of these two languages the user's text is written in, then translate it into \
the other language:
- {native_name} input -> {target_name} output
- {target_name} input -> {native_name} output

Never translate text back into the same language. If the text contains both languages, use \
the predominant language as the source and translate the complete text into the other one.

Also determine:
- "single": true if the selection is ONE word, phrasal verb, or fixed expression \
(e.g. "running", "an apple", "give up", "by the way"). \
false if it is an extended phrase/sentence/text.
- "normalized_text": ONLY if single == true — the same word/expression restored to its \
dictionary form without typos or grammatical distortions in the detected source language. \
If single == false — empty string "".
- "detected_source_lang": two-letter ISO 639-1 code of the language detected in the source text.

Translation rules:
- If single == true — give the most natural dictionary translation, not a word-by-word one.
- If single == false — translate the full text, preserving tone and meaning.

Reply ONLY in JSON without markdown:
{{"translation": "...", "single": true|false, "normalized_text": "...", \
"detected_source_lang": "xx"}}
"""


async def translate_selection(
    text: str,
    source_lang: str,
    target_lang: str,
    level: str = "intermediate",
    bidirectional: bool = False,
) -> dict:
    log.info(
        "[translate_selection] text=%r source=%s target=%s level=%s bidirectional=%s",
        _truncate(text), source_lang, target_lang, level, bidirectional,
    )
    cached = await get_translation(source_lang, target_lang, text, bidirectional)
    if cached is not None:
        return cached

    if bidirectional:
        native_name = _LANG_NAMES.get(source_lang, source_lang)
        target_name = _LANG_NAMES.get(target_lang, target_lang)
        system = _BIDIRECTIONAL_TRANSLATE_SYSTEM.format(
            level=level,
            native_name=native_name,
            target_name=target_name,
        )
    else:
        source_name = "the source language (detect it)" if source_lang == "auto" else source_lang
        system = _TRANSLATE_SELECTION_SYSTEM.format(
            level=level,
            source_name=source_name,
            target_name=target_lang,
        )
    try:
        raw = await _call(system, user=text, max_tokens=400, json_mode=True, call_name="translate_selection")
        data = json.loads(_clean_json(raw))
        result = {
            "translation": data.get("translation", ""),
            "single": bool(data.get("single", False)),
            "normalized_text": data.get("normalized_text", "") or "",
            "detected_source_lang": data.get("detected_source_lang"),
        }
        await set_translation(
            source_lang,
            target_lang,
            text,
            bidirectional,
            result,
        )
        log.info(
            "[translate_selection] -> single=%s normalized=%r translation=%r detected=%s",
            result["single"], result["normalized_text"], _truncate(result["translation"]),
            result["detected_source_lang"],
        )
        return result
    except Exception:
        log.exception("[translate_selection] failed")
        return {"translation": "", "single": False, "normalized_text": "", "detected_source_lang": None}


_EXPLAIN_SELECTION_SYSTEM = """\
You are a language-learning assistant (user level: {level}).

The user selected the text: "{text}"
Brief translation they already saw: "{translation}"

Give an expanded explanation for the translation popup:
- meaning of the word/expression and a brief translation (may repeat/clarify the brief one)
- 1-2 example sentences in the source language with translation
- if the word has multiple meanings or usage nuances — briefly mention them
- match examples and explanations to the {level} difficulty \
(for beginner — simple short sentences; for advanced — more complex constructions and nuances)

Write the explanation in the translation language (the language translated into), \
concisely and to the point — this is a popup, not a lecture.

Reply ONLY in JSON without markdown:
{{"explanation": "..."}}
"""


async def explain_selection(text: str, translation: str, level: str = "intermediate") -> str:
    log.info("[explain_selection] text=%r translation=%r level=%s", _truncate(text), _truncate(translation), level)

    key = make_key(text, translation, level)
    cached = await cache_get("explain", key)
    if isinstance(cached, str) and cached:
        log.info("[explain_selection] cache hit (sqlite)")
        return cached

    system = _EXPLAIN_SELECTION_SYSTEM.format(text=text, translation=translation, level=level)
    try:
        raw = await _call(system, user="", max_tokens=500, json_mode=True, call_name="explain_selection")
        explanation = json.loads(_clean_json(raw)).get("explanation", "")
        if explanation:
            await cache_set("explain", key, explanation)
        log.info("[explain_selection] -> explanation=%r", _truncate(explanation))
        return explanation
    except Exception:
        log.exception("[explain_selection] failed")
        return ""
