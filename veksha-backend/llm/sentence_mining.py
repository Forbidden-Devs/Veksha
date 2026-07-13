"""Generate level-aware Sentence Mining cards for saved vocabulary."""
from __future__ import annotations

import json
import logging

from llm._base import _LANG_NAMES, _call, _clean_json, _truncate

log = logging.getLogger(__name__)

_SYSTEM = """\
You create a compact Sentence Mining card for a language learner.

Target language: {target_name}
Learner's native language: {native_name}
Saved word or expression: {word}
Known translation: {translation}
Original browsing context: {context}

Generate exactly {same_count} natural example sentence(s) at CEFR {level} and
exactly {higher_count} sentence(s) at CEFR {higher_level}. Every sentence must
use the saved word (or its grammatically inflected form) naturally. Examples
must be distinct, useful in real life, and short enough for a study card.

Also provide:
- one memorable mnemonic in {native_name}; connect sound, spelling, or meaning
  without inventing false etymology
- 3 to 5 frequent, natural collocations in {target_name}, each translated into
  {native_name}

Reply ONLY in JSON, no markdown:
{{"examples":[{{"sentence":"...","translation":"...","level":"{level}"}}],
"mnemonic":"...","collocations":[{{"text":"...","translation":"..."}}]}}
"""


def _lang_name(code: str) -> str:
    return _LANG_NAMES.get(code or "en", (code or "en").upper())


def _normalise_card(
    data: object,
    level: str,
    higher_level: str,
    same_count: int,
    higher_count: int,
) -> dict:
    if not isinstance(data, dict):
        return {"examples": [], "mnemonic": "", "collocations": []}

    same_examples = []
    higher_examples = []
    raw_examples = data.get("examples", [])
    if not isinstance(raw_examples, list):
        raw_examples = []
    for item in raw_examples:
        if not isinstance(item, dict):
            continue
        sentence = str(item.get("sentence", "") or "").strip()
        translation = str(item.get("translation", "") or "").strip()
        item_level = str(item.get("level", level) or level).upper().strip()
        if not sentence:
            continue
        if item_level not in (level, higher_level):
            item_level = level
        normalised = {
            "sentence": sentence,
            "translation": translation,
            "level": item_level,
            "is_higher": item_level == higher_level and higher_level != level,
        }
        if higher_level != level and item_level == higher_level:
            if len(higher_examples) < higher_count:
                higher_examples.append(normalised)
        elif len(same_examples) < same_count + (higher_count if higher_level == level else 0):
            same_examples.append(normalised)

    examples = [*same_examples, *higher_examples]

    collocations = []
    raw_collocations = data.get("collocations", [])
    if not isinstance(raw_collocations, list):
        raw_collocations = []
    for item in raw_collocations[:5]:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "") or "").strip()
        if text:
            collocations.append({
                "text": text,
                "translation": str(item.get("translation", "") or "").strip(),
            })

    return {
        "examples": examples,
        "mnemonic": str(data.get("mnemonic", "") or "").strip()[:500],
        "collocations": collocations,
    }


async def generate_sentence_mining(
    word: str,
    translation: str,
    context: str,
    target_lang: str,
    native_lang: str,
    level: str,
    higher_level: str,
    same_count: int,
    higher_count: int,
) -> dict:
    system = _SYSTEM.format(
        target_name=_lang_name(target_lang),
        native_name=_lang_name(native_lang),
        word=word,
        translation=_truncate(translation, 300) if translation else "(not available)",
        context=_truncate(context, 600) if context else "(not available)",
        level=level,
        higher_level=higher_level,
        same_count=same_count,
        higher_count=higher_count,
    )
    try:
        raw = await _call(
            system,
            user=word,
            max_tokens=1400,
            json_mode=True,
            call_name="sentence_mining",
        )
        return _normalise_card(
            json.loads(_clean_json(raw)),
            level,
            higher_level,
            same_count,
            higher_count,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("[sentence_mining] generation failed: %s | word=%r", exc, _truncate(word))
        return {"examples": [], "mnemonic": "", "collocations": []}
