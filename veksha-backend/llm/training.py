"""
llm/training.py — LLM calls for word training (WebSocket sessions).

  check_synonym_appropriate — yes/no: does the word have good synonyms for the level
  get_reverse_translations  — native-language translations for the "reverse" task
  check_training_answer     — answer verdict for the WebSocket training module
"""
from __future__ import annotations

import json
import logging

from llm._base import _LANG_NAMES, _call, _clean_json, _native_lang_note, _truncate

log = logging.getLogger(__name__)


_TUTOR_TASK_SYSTEM = """\
You are an experienced one-to-one language tutor preparing one short retrieval-practice task.
Target item: "{word}"
Student CEFR level: {level}
Task skill: {task_type}
Saved context: {context}
Required task direction: {seed_question}

Use the task style a professional tutor would use at this level:
- A1-A2: one concrete situation, short familiar vocabulary, one unambiguous operation.
- B1-B2: a realistic sentence or mini-dialogue, collocation and register awareness.
- C1-C2: nuance, connotation, natural register, or precise reformulation in context.

Do not mention CEFR, the answer, or grading. Do not ask an abstract dictionary question if a
short situation can test the same skill. Keep it to at most 3 short sentences. Address the
student directly. Write the instruction in the student's native language when appropriate.
Reply ONLY in JSON: {{"question":"...","skill":"short pedagogical focus"}}
"""


async def generate_tutor_task(word: str, context: str, task_type: str, level: str, native_lang: str, seed_question: str) -> dict:
    system = _TUTOR_TASK_SYSTEM.format(
        word=word,
        context=context or "none",
        task_type=task_type,
        level=level,
        seed_question=seed_question,
    ) + _native_lang_note(native_lang)
    try:
        raw = await _call(system, user="", max_tokens=220, temp=0.4, json_mode=True, call_name="generate_tutor_task")
        data = json.loads(_clean_json(raw))
        return {"question": str(data.get("question", "")).strip(), "skill": str(data.get("skill", "")).strip()}
    except Exception:
        log.exception("[generate_tutor_task] failed")
        return {"question": "", "skill": "vocabulary recall"}


# ---------------------------------------------------------------------------
# WebSocket training — synonym check
# ---------------------------------------------------------------------------

_SYNONYM_CHECK_SYSTEM = """\
Answer whether this English word has obvious synonyms for the {level} level.

Word: "{word}"

Reply ONLY in JSON without markdown: {{"ok": true|false}}
- true: common word with well-known synonyms (big→large, happy→glad, run→sprint…)
- false: phrasal verb, fixed expression, word with no clear synonym, \
  or too complex for the given level
"""


async def check_synonym_appropriate(word: str, level: str) -> bool:
    log.info("[check_synonym_appropriate] word=%r level=%s", word, level)
    system = _SYNONYM_CHECK_SYSTEM.format(word=word, level=level)
    try:
        raw = await _call(system, user="", max_tokens=20, json_mode=True, call_name="check_synonym_appropriate")
        result = bool(json.loads(_clean_json(raw)).get("ok", False))
        log.info("[check_synonym_appropriate] -> %s", result)
        return result
    except Exception:
        log.exception("[check_synonym_appropriate] failed, defaulting False")
        return False


# ---------------------------------------------------------------------------
# WebSocket training — reverse translation list
# ---------------------------------------------------------------------------

_REVERSE_TRANSLATIONS_SYSTEM = """\
Give all common translations of the English word or phrase into {native_lang_name}. \
Only the words/phrases themselves, no explanations, 1–5 options.

Word: "{word}"

Reply ONLY in JSON without markdown: {{"translations": ["...", "..."]}}
"""


async def get_reverse_translations(word: str, native_lang: str = "en") -> list[str]:
    log.info("[get_reverse_translations] word=%r native_lang=%s", word, native_lang)
    lang_name = _LANG_NAMES.get(native_lang or "en", native_lang or "English")
    system = _REVERSE_TRANSLATIONS_SYSTEM.format(word=word, native_lang_name=lang_name)
    try:
        raw = await _call(system, user="", max_tokens=80, json_mode=True, call_name="get_reverse_translations")
        translations = json.loads(_clean_json(raw)).get("translations", [])
        result = [str(t) for t in translations if t] or [word]
        log.info("[get_reverse_translations] -> %s", result)
        return result
    except Exception:
        log.exception("[get_reverse_translations] failed, returning word")
        return [word]


# ---------------------------------------------------------------------------
# WebSocket training — answer check
# ---------------------------------------------------------------------------

_CHECK_TRAINING_ANSWER_SYSTEM = """\
You are checking a user's answer in a language-learning session.

Correct word/expression: "{word}"
Task: "{question}"
User's answer: "{answer}"
Level: {level}

Determine:
- "outcome":
  - "correct": answer is right (accept synonyms, close variants, minor grammar mistakes)
  - "incorrect": answer is wrong, but the user tried to answer on topic
  - "vague": answer is vague/descriptive instead of specific (e.g. "it's a verb", "I am [asked word]")
  - "garbage": random characters, junk, obvious skip (aaa, 123, ???, single space, etc.)

- "feedback":
  - correct: brief approval (1 sentence)
  - incorrect/vague: correct answer + brief explanation (2-3 sentences)
  - garbage: politely ask user to try answering seriously

Reply ONLY in JSON without markdown:
{{"outcome":"...","feedback":"..."}}
"""


async def check_training_answer(word: str, question: str, answer: str, level: str, native_lang: str = "en") -> dict:
    """Returns {"outcome": correct|incorrect|vague|garbage, "feedback": str}."""
    log.info("[check_training_answer] word=%r answer=%r", word, _truncate(answer))
    system = _CHECK_TRAINING_ANSWER_SYSTEM.format(
        word=word, question=question, answer=answer, level=level
    ) + _native_lang_note(native_lang)
    try:
        raw = await _call(system, user="", max_tokens=300, temp=0.2, json_mode=True, call_name="check_training_answer")
        data = json.loads(_clean_json(raw))
        outcome = data.get("outcome", "incorrect")
        if outcome not in ("correct", "incorrect", "vague", "garbage"):
            outcome = "incorrect"
        result = {"outcome": outcome, "feedback": data.get("feedback", "")}
        log.info("[check_training_answer] -> outcome=%s feedback=%r", outcome, _truncate(result["feedback"]))
        return result
    except Exception:
        log.exception("[check_training_answer] failed")
        return {"outcome": "incorrect", "feedback": f"Correct answer: {word}"}
