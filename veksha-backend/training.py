"""
training.py — business logic for training sessions in the browser extension.

State is kept on the client (React); the server generates tasks via WebSocket
and checks answers. All task-type selection logic runs here on the server.

Task types:
  translation         — translate the word to the user's native language
  synonym             — name an English synonym
  example             — compose a sentence using the word
  reverse_translation — translate the native-language word back to English
"""
from __future__ import annotations

import logging
import random
import time
import uuid

import i18n
from llm.training import check_synonym_appropriate, get_reverse_translations, check_training_answer, generate_tutor_task
from config import REVIEW_WINDOW_HOURS
from models import Word
from storage import UserStorage

log = logging.getLogger(__name__)

MAX_SESSION_WORDS = 10

_ALL_TYPES = ("translation", "synonym", "example", "reverse_translation")


# ---------------------------------------------------------------------------
# Word selection for training
# ---------------------------------------------------------------------------

def get_available_words(storage: UserStorage) -> list[Word]:
    """
    Words available for training right now:
      1. "Due" — reviewed before, next_review within the look-ahead window
         or overdue (FSRS folds lateness into the next interval)
      2. "New"  — counter == -1
    Priority: due words first, new words as supplement.
    """
    now = time.time()
    window = REVIEW_WINDOW_HOURS * 3600

    active = [w for w in storage.words if w.language == storage.settings.target_lang and not w.known]
    due = [w for w in active if w.counter >= 0 and w.next_review - now <= window]
    seen = {w.name for w in due}
    new_words = [w for w in active if w.counter == -1 and w.name not in seen]
    return due + new_words


# ---------------------------------------------------------------------------
# Task generation (all logic on the server)
# ---------------------------------------------------------------------------

async def generate_task(word: Word, level: str, native_lang: str = "en") -> dict:
    """
    Returns a ready task to send to the client via WebSocket.

    Algorithm:
      1. Randomly pick task type from 4.
      2. If "synonym" → LLM appropriateness check; on rejection — re-pick from 3.
      3. If "reverse_translation" → LLM returns translation list, pick one.
      4. For other types — template question via i18n.
    """
    task_type = random.choice(_ALL_TYPES)

    if task_type == "synonym":
        ok = await check_synonym_appropriate(word.name, level)
        if not ok:
            task_type = random.choice(("translation", "example", "reverse_translation"))

    extra: dict = {}

    if task_type == "reverse_translation":
        translations = await get_reverse_translations(word.name, native_lang=native_lang)
        chosen = random.choice(translations)
        extra["reverse_text"] = chosen
        question = i18n.get_string("training_q_reverse", native_lang, word=chosen)
    elif task_type == "translation":
        question = i18n.get_string("training_q_translation", native_lang, word=word.name)
    elif task_type == "synonym":
        question = i18n.get_string("training_q_synonym", native_lang, word=word.name)
    else:  # example
        question = i18n.get_string("training_q_example", native_lang, word=word.name)

    tutor_task = await generate_tutor_task(
        word=word.name,
        context=word.context,
        task_type=task_type,
        level=level,
        native_lang=native_lang,
        seed_question=question,
    )
    if tutor_task["question"]:
        question = tutor_task["question"]

    task = {
        "task_id": str(uuid.uuid4()),
        "word": word.name,
        "context": word.context or "",
        "task_type": task_type,
        "question": question,
        "counter": word.counter,
        "skill": tutor_task["skill"],
        **extra,
    }
    log.info("[generate_task] word=%r task_type=%s", word.name, task_type)
    return task


# ---------------------------------------------------------------------------
# Answer checking
# ---------------------------------------------------------------------------

async def check_answer(word: str, question: str, answer: str, level: str, native_lang: str = "en") -> dict:
    """
    Check answer via LLM.
    Returns {"outcome", "feedback", "update_kb"}.
    update_kb == False only when outcome == "garbage".
    """
    result = await check_training_answer(word, question, answer, level, native_lang=native_lang)
    result["update_kb"] = result["outcome"] != "garbage"
    return result
