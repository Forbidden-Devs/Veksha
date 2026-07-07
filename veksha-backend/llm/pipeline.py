"""
llm/pipeline.py — LLM calls for the main message pipeline (spec v3, sections 3.1–3.4).

  input_processor        — 3.1, classify every incoming message
  extract_metadata       — 3.2, add_word patches from expanded text
  update_knowledge_base  — 3.3, patches for edit_knowledge_base
  match_delete_candidate — 3.4, LLM matching for delete_word / delete_topic
  unknown_message        — fixed text for action="unknown" (spec 6, p.2)
"""
from __future__ import annotations

import logging

from models import Patch, ProcessorResult
from config import OPENAI_SMART_MODEL
from llm._base import _LANG_NAMES, _call, _parse_json, _truncate
from db_cache import cache_get, cache_set, make_key

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 3.1 Input Processor
# ---------------------------------------------------------------------------

_INPUT_PROCESSOR_SYSTEM = """\
You are Veksha in Assistant mode.

User profile:
- Native language: {native_lang_name}
- Learning: {target_lang_name}
- Level: {english_level}
- Goals: {goals}
- Preferences: {general_prompt}

Recent conversation:
{context}

Always reply to the user in {native_lang_name}.

You have two responsibilities:
1. Answer ordinary questions and requests helpfully, like a general-purpose assistant.
2. Route clear requests to generate, select, add, remove, or organize learning words/topics
   into the vocabulary knowledge-base action.

IMPORTANT ROUTING RULE:
Never generate or display a requested vocabulary list or generated learning topic in `value`.
When the user clearly wants words, phrases, vocabulary, or a learning topic prepared for a
specific subject, use action="edit_knowledge_base". The downstream knowledge-base generator
will create the actual words/topic. Your `value` should only briefly confirm what will be done.

Examples that MUST use action="edit_knowledge_base":
- "Generate 15 words about travel."
- "Give me vocabulary for a job interview."
- "Create a topic about OOP."
- "I need advanced legal English words."
- "Pick useful phrases for ordering food."
- "Add/remove these words."

This applies even if the user says "give me", "show me", or "generate" rather than explicitly
saying "add to my vocabulary". A concrete subject, requested vocabulary type, or requested
quantity is enough to establish intent.

If the user asks an ordinary informational question, answer it directly with action=null.
Examples:
- "What is polymorphism?" -> explain polymorphism.
- "Help me write an email." -> help write the email.
- "Translate/explain this sentence." -> answer the request.

Exception: any question about grammar or how to correctly formulate something in
{target_lang_name} is an explicit request for a learning topic. Use
action="edit_knowledge_base" to create a topic for that grammar/formulation issue; do not
answer or explain it directly in `value`.

Do not turn a mere mention of a subject into vocabulary generation. Only route to the
knowledge base when the user is asking to create or manage learning material.

If the user wants learning material but essential details are genuinely unclear, use
action=null and ask one concise clarifying question. Do not pre-generate example words while
clarifying. Once the answer makes the request clear, route it to edit_knowledge_base using the
recent conversation context.

--- ACTIONS ---

action="edit_knowledge_base":
  Use for every clear request to generate or manage vocabulary/topics.
  value = a short confirmation in {native_lang_name}; do not include the generated items.
  kb_request = a precise English instruction for the downstream generator. Preserve the user's
  requested subject, quantity, vocabulary type, constraints, and level. Do not invent the final
  word list here.

action=null:
  Use for ordinary assistant answers and concise clarification questions.
  value = the complete user-facing answer or clarification in {native_lang_name}.
  kb_request = "".

Reply ONLY with a JSON object, no markdown:
{{"action": null|"edit_knowledge_base", "value": "...", "kb_request": "..."}}
"""


async def input_processor(
    user_message: str,
    context: str,
    native_lang: str = "en",
    target_lang: str = "en",
    english_level: str = "",
    goals: str = "",
    general_prompt: str = "",
) -> ProcessorResult:
    """Classify every incoming message: language learning response or KB edit."""
    log.info(
        "[input_processor] message=%r native_lang=%s target_lang=%s level=%r",
        _truncate(user_message), native_lang, target_lang, english_level,
    )
    native_lang_name = _LANG_NAMES.get(native_lang or "en", native_lang or "English")
    target_lang_name = _LANG_NAMES.get(target_lang or "en", target_lang or "English")
    system = _INPUT_PROCESSOR_SYSTEM.format(
        context=context or "(none)",
        native_lang_name=native_lang_name,
        target_lang_name=target_lang_name,
        english_level=english_level or "not specified",
        goals=goals or "not specified",
        general_prompt=general_prompt or "not specified",
    )
    try:
        raw = await _call(system, user=user_message, max_tokens=500, json_mode=True, call_name="input_processor")
        data = _parse_json(raw)
        result = ProcessorResult.from_dict(data)
        log.info(
            "[input_processor] action=%r kb_request=%r value=%r",
            result.action, _truncate(result.kb_request), _truncate(result.value),
        )
        return result
    except Exception:
        log.exception("[input_processor] failed, falling back to action=None")
        return ProcessorResult(action=None, value=user_message)


# ---------------------------------------------------------------------------
# 3.2 Extract Metadata
# ---------------------------------------------------------------------------

_EXTRACT_METADATA_SYSTEM = """\
You help maintain the vocabulary of an English learner.

User message: "{user_message}"
Response/translation they received: "{value}"
User's existing topics: {topic_names}

Identify which English words/phrases from the response the user likely does NOT know \
and should add to their training vocabulary (add_word). Skip words they clearly know.

For each new word include:
- name: the word/phrase in English (lowercase)
- context: short fragment of the source text where the word appeared (or "" if none)

Reply ONLY in JSON without markdown:
{{"patches": [{{"type": "add_word", "value": "word", "context": "..."}}, ...]}}

If there are no new words to add — return {{"patches": []}}.
"""


async def extract_metadata(user_message: str, value: str, topic_names: list[str]) -> list[Patch]:
    """Spec 3.2: triggered when action == null and single == false."""
    log.info(
        "[extract_metadata] user_message=%r value=%r topic_names=%s",
        _truncate(user_message), _truncate(value), topic_names,
    )
    system = _EXTRACT_METADATA_SYSTEM.format(
        user_message=user_message,
        value=value,
        topic_names=", ".join(topic_names) if topic_names else "(none)",
    )
    try:
        raw = await _call(system, user="", max_tokens=400, json_mode=True, call_name="extract_metadata")
        data = _parse_json(raw)
        patches = [
            Patch(type="add_word", value=str(p["value"]).strip().lower(), context=p.get("context", ""), counter=-1, known=False)
            for p in data.get("patches", [])
            if p.get("type") == "add_word" and p.get("value")
        ]
        log.info("[extract_metadata] -> %d patch(es): %s", len(patches), [p.value for p in patches])
        return patches
    except Exception:
        log.exception("[extract_metadata] failed")
        return []


# ---------------------------------------------------------------------------
# 3.3 Update Knowledge Base
# ---------------------------------------------------------------------------

_UPDATE_KB_SYSTEM = """\
You manage the {target_lang_name} vocabulary list for a learner who is studying {target_lang_name}.

The user adds topics to learn the {target_lang_name} vocabulary needed to READ, SPEAK, and WRITE
about those topics in {target_lang_name} — not to study the subject itself.
For each topic include: core terms, fixed expressions, collocations, abbreviations, and any
phrasing that is characteristic of this topic in {target_lang_name}.

Example — topic "OOP":
  add_word: "encapsulation", "inheritance", "polymorphism", "override", "instantiate",
            "abstract class", "design pattern", "tight coupling", "OOP" (abbreviation),
            "is-a relationship", "has-a relationship"
  NOT: explanations of OOP concepts, words in other languages.

Special case — if a topic has no meaningful {target_lang_name}-specific vocabulary at the
user's level (e.g. the topic is very narrow or level-inappropriate):
  Still add the topic, but add only 3-5 general terms and set context="limited vocabulary at this level"
  on the add_topic patch.

User request: "{user_message}"
User's {target_lang_name} level: {level}
Existing lesson topics: {topic_names}
Existing vocabulary (skip duplicates): {word_names}

Patch types:
- "add_word": {target_lang_name} word, phrase, fixed expression, or abbreviation (lowercase, \
except abbreviations like "OOP", "API", "MVP").
- "add_topic": topic name to add to the lesson list.
- "delete_word" / "delete_topic": remove from the list.
- "mark_known": exclude a word from training (user already knows it).

Level guidelines for add_word — STRICTLY match the learner's CEFR level:
  A1–A2
    → Include: very common everyday words, basic topic terms.
    → Exclude: anything a beginner would find confusing or overly technical.
  B1
    → Include: topic-specific vocabulary, common collocations.
    → Exclude: words so common a B1 learner already knows them (e.g. "computer", "work", "book").
  B2
    → Include: precise and nuanced topic terms, idiomatic and fixed expressions,
      professional-register words, non-obvious collocations.
    → Exclude: everyday and mid-frequency words an upper-intermediate learner already knows
      (e.g. "pronunciation", "outcome", "self-study", "source code" for someone in IT).
  C1–C2
    → Include: nuanced terms, idioms, domain-specific expressions, low-frequency
      but high-value fixed phrases.
    → Exclude: anything a competent speaker would know without studying
      (e.g. "inheritance" for a developer, "hotel" for a traveller).
For split levels like "B1/B2", apply the stricter (higher) band.

IMPORTANT: for B2 and above, do NOT generate basic or mid-frequency words even if they are
related to the topic. Only words that genuinely challenge this level. If in doubt whether the
learner already knows a word — skip it.

Do NOT add free compositional combinations whose meaning is just the sum of their parts
(e.g. "practice speaking", "run a program", "read a book"). Multi-word entries are allowed
only for fixed expressions, idioms, phrasal verbs, and established collocations that must be
learned as a unit.

For a topic addition: generate add_topic and the number of add_word patches explicitly requested
by the user. If no quantity was requested, generate 8–15 add_word patches at the correct level.
Always preserve explicit constraints from the user request. Avoid words already in the existing
vocabulary list.

Reply ONLY in JSON without markdown:
{{"patches": [{{"type": "...", "value": "...", "context": "..."}}, ...]}}
"""


# Bump when the KB prompt changes meaningfully — invalidates the shared
# generation cache so stale (pre-fix) word lists are not served.
_KB_PROMPT_VERSION = "kb-v2"

# Settings may hold either a CEFR code ("b2", "b1_b2") or a legacy scale name.
_LEVEL_TO_CEFR = {
    "beginner": "A1",
    "elementary": "A2",
    "intermediate": "B1",
    "upper_intermediate": "B2",
    "advanced": "C1",
}


def _cefr_label(level: str) -> str:
    """Normalize a stored level to a CEFR label the prompt guidelines use."""
    raw = (level or "").strip().lower()
    if not raw:
        return "not specified"
    if raw in _LEVEL_TO_CEFR:
        return _LEVEL_TO_CEFR[raw]
    # CEFR codes: "b2" -> "B2", "b1_b2" -> "B1/B2"
    return raw.replace("_", "/").upper()


async def update_knowledge_base(
    user_message: str,
    topic_names: list[str],
    word_names: list[str],
    english_level: str = "",
    target_lang: str = "en",
) -> list[Patch]:
    """Generate KB patches for edit_knowledge_base. Uses the smart model for quality generation."""
    target_lang_name = _LANG_NAMES.get(target_lang or "en", target_lang or "English")
    log.info(
        "[update_knowledge_base] user_message=%r level=%r target_lang=%s topic_names=%s word_names_count=%d",
        _truncate(user_message), english_level, target_lang, topic_names, len(word_names),
    )

    # Shared generation cache by (request + level + language). Per-user dedup still
    # happens at apply time (apply_kb_changes skips words/topics already in the KB).
    cache_key = make_key(user_message, english_level or "", target_lang or "en", _KB_PROMPT_VERSION)
    cached = await cache_get("topic", cache_key)
    if isinstance(cached, list) and cached:
        patches = [Patch.from_dict(d) for d in cached]
        log.info("[update_knowledge_base] cache hit (sqlite) -> %d patch(es)", len(patches))
        return patches

    system = _UPDATE_KB_SYSTEM.format(
        user_message=user_message,
        target_lang_name=target_lang_name,
        level=_cefr_label(english_level),
        topic_names=", ".join(topic_names) if topic_names else "(none)",
        word_names=", ".join(word_names[:50]) if word_names else "(none)",
    )
    try:
        raw = await _call(
            system, user="", max_tokens=800, json_mode=True,
            call_name="update_knowledge_base", model=OPENAI_SMART_MODEL,
        )
        data = _parse_json(raw)
        patches = [
            Patch(
                type=p["type"],
                value=str(p["value"]).strip(),
                context=str(p.get("context", "") or ""),
                counter=-1 if p["type"] == "add_word" else 0,
                known=False,
            )
            for p in data.get("patches", [])
            if p.get("type") in ("add_word", "delete_word", "add_topic", "delete_topic", "mark_known") and p.get("value")
        ]
        log.info("[update_knowledge_base] -> %d patch(es): %s", len(patches), [(p.type, p.value) for p in patches])
        # Cache only purely-additive generations — never delete/manage requests.
        if patches and all(p.type in ("add_word", "add_topic") for p in patches):
            await cache_set("topic", cache_key, [p.to_dict() for p in patches])
        return patches
    except Exception:
        log.exception("[update_knowledge_base] failed")
        return []


# ---------------------------------------------------------------------------
# 3.4 LLM matching for delete_word / delete_topic
# ---------------------------------------------------------------------------

_MATCH_DELETE_SYSTEM = """\
The user asked to delete "{query}".
Among the candidates from their vocabulary, find the one that matches their request.

Candidates: {candidates}

Reply ONLY in JSON without markdown: {{"match": "exact candidate name" | null}}
"""


async def match_delete_candidate(query: str, candidates: list[str]) -> str | None:
    """Spec 3.4, p.2: LLM picks the best match from algorithmic candidates."""
    log.info("[match_delete_candidate] query=%r candidates=%s", query, candidates)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    system = _MATCH_DELETE_SYSTEM.format(query=query, candidates=", ".join(candidates))
    try:
        raw = await _call(system, user="", max_tokens=100, json_mode=True, call_name="match_delete_candidate")
        data = _parse_json(raw)
        match = data.get("match")
        result = match if match in candidates else None
        log.info("[match_delete_candidate] -> match=%r", result)
        return result
    except Exception:
        log.exception("[match_delete_candidate] failed, falling back to first candidate")
        return candidates[0]


# ---------------------------------------------------------------------------
# unknown_message (spec 6, p.2)
# ---------------------------------------------------------------------------

def unknown_message(native_lang: str = "ru") -> str:
    import i18n as _i18n
    log.info("[unknown_message] action=unknown native_lang=%r", native_lang)
    return _i18n.get_string("unknown_msg", native_lang)
