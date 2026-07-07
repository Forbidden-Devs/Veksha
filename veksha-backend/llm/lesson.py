"""
llm/lesson.py — LLM calls for topic lessons (WebSocket sessions).

  suggest_block_names      — propose grammar/language-pattern block names for a topic
  generate_block_content   — generate structured language-learning material for a block
  review_block_content     — quality-check the generated material; verdict: good/revise/words_only
  generate_lesson_question — vocabulary/grammar question based on block content
  check_lesson_answer      — answer verdict for the WebSocket lesson module
"""
from __future__ import annotations

import logging

from config import OPENAI_SMART_MODEL
from llm._base import _LANG_NAMES, _call, _parse_json, _truncate

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# WebSocket lesson — block name suggestion
# ---------------------------------------------------------------------------

_SUGGEST_BLOCKS_SYSTEM = """\
You are designing a {target_lang_name} language lesson plan for the topic "{topic}".
Learner: native {native_lang_name} speaker, {target_lang_name} level {level}.

IMPORTANT: Each block must teach a LANGUAGE PATTERN, not subject matter.
Blocks that belong here:
- Grammar rules specific to {target_lang_name} (articles, tenses, word order, prepositions)
- Fixed expressions, idioms, or collocations that do NOT translate literally to {native_lang_name}
- Domain-specific {target_lang_name} usage that differs from how {native_lang_name} speakers expect
  (e.g. how professionals actually phrase things in {target_lang_name} in this field)
- Abbreviations and terminology where knowing the {target_lang_name} form is non-obvious

Blocks that do NOT belong here (just add words to the vocabulary list instead):
- Topics where {target_lang_name} words are direct translations with no special usage rules
- Factual subject-matter knowledge (history, geography, science facts)
- Simple word lists where every item has an obvious {native_lang_name} equivalent

Topic examples that produce GOOD blocks: "Articles in English", "Phrasal verbs in tech",
  "How professionals describe OOP patterns in English interviews",
  "Speech therapy terminology: {target_lang_name} vs {native_lang_name} naming conventions"
Topic examples with NO good blocks: "17th century art", "Basic kitchen utensils", "Countries of Europe"

Already created blocks: {existing}
Suggest {count} new blocks not yet covered.
If this topic has no meaningful language-pattern content at level {level} — return an empty list.

Reply ONLY in JSON without markdown: {{"names": ["..."]}}
"""


async def suggest_block_names(
    topic: str,
    existing: list[str],
    level: str,
    count: int = 3,
    native_lang: str = "en",
    target_lang: str = "en",
) -> list[str]:
    log.info("[suggest_block_names] topic=%r existing=%s level=%s", topic, existing, level)
    native_lang_name = _LANG_NAMES.get(native_lang or "en", native_lang or "English")
    target_lang_name = _LANG_NAMES.get(target_lang or "en", target_lang or "English")
    existing_str = ", ".join(f'"{n}"' for n in existing) if existing else "none"
    system = _SUGGEST_BLOCKS_SYSTEM.format(
        topic=topic,
        existing=existing_str,
        level=level,
        count=count,
        native_lang_name=native_lang_name,
        target_lang_name=target_lang_name,
    )
    try:
        raw = await _call(system, user="", max_tokens=200, json_mode=True, call_name="suggest_block_names")
        names = _parse_json(raw).get("names", [])
        result = [str(n) for n in names if n and str(n) not in existing][:count]
        log.info("[suggest_block_names] -> %s", result)
        return result
    except Exception:
        log.exception("[suggest_block_names] failed")
        return []


# ---------------------------------------------------------------------------
# WebSocket lesson — block content generation
# ---------------------------------------------------------------------------

_GENERATE_CONTENT_SYSTEM = """\
Create a {target_lang_name} language lesson block for the topic "{topic}", block "{block_name}".
Learner: native {native_lang_name} speaker, {target_lang_name} level {level}.
Other blocks in this topic: {all_blocks}

This block must teach a LANGUAGE PATTERN — not explain the subject matter.
Focus on:
- {target_lang_name} expressions, phrases, or constructions that do not translate literally
- Grammar rules or usage patterns specific to this topic in {target_lang_name}
- Fixed collocations and how they are actually used by native speakers
- Terminology where the {target_lang_name} usage differs from what a {native_lang_name} speaker would expect

Every example must be in {target_lang_name} with a {native_lang_name} explanation.
{revision_section}
Reply ONLY in JSON without markdown:
{{
  "title": "block title",
  "intro": "2-3 sentences in {native_lang_name} explaining what {target_lang_name} language pattern \
this block covers and why it matters",
  "sections": [
    {{
      "icon": "emoji",
      "header": "section header in {native_lang_name}",
      "items": [
        "{target_lang_name} expression / pattern — {native_lang_name} explanation of usage",
        "..."
      ],
      "highlight": false
    }}
  ]
}}

Include 2-4 sections:
- Core expressions or patterns (icon 📌, highlight: false, 4-8 items): key {target_lang_name} \
phrases with {native_lang_name} usage notes, NOT just translations
- Usage examples in context (icon 💬, highlight: true, 3-5 items): real {target_lang_name} sentences \
showing the pattern, with {native_lang_name} commentary
- Common mistakes or contrasts with {native_lang_name} (icon ⚠️, highlight: false), if relevant
"""


async def generate_block_content(
    topic: str,
    block_name: str,
    all_block_names: list[str],
    level: str,
    native_lang: str = "en",
    target_lang: str = "en",
    revision_feedback: str = "",
) -> dict:
    log.info(
        "[generate_block_content] topic=%r block=%r level=%s revision=%s",
        topic, block_name, level, bool(revision_feedback),
    )
    native_lang_name = _LANG_NAMES.get(native_lang or "en", native_lang or "English")
    target_lang_name = _LANG_NAMES.get(target_lang or "en", target_lang or "English")
    all_str = ", ".join(f'"{n}"' for n in all_block_names) if all_block_names else "none"

    revision_section = (
        f"\nREVISION INSTRUCTIONS (from previous review):\n{revision_feedback}\n"
        if revision_feedback else ""
    )

    system = _GENERATE_CONTENT_SYSTEM.format(
        topic=topic,
        block_name=block_name,
        all_blocks=all_str,
        level=level,
        native_lang_name=native_lang_name,
        target_lang_name=target_lang_name,
        revision_section=revision_section,
    )
    model = OPENAI_SMART_MODEL if revision_feedback else None
    try:
        raw = await _call(
            system, user="", max_tokens=1200, temp=0.4,
            json_mode=True, call_name="generate_block_content", model=model,
        )
        data = _parse_json(raw)
        if "sections" not in data:
            data["sections"] = []
        for s in data["sections"]:
            if "highlight" not in s:
                s["highlight"] = False
        log.info("[generate_block_content] generated block %r (%d sections)", block_name, len(data["sections"]))
        return data
    except Exception:
        log.exception("[generate_block_content] failed for block %r", block_name)
        return {"title": block_name, "intro": "", "sections": []}


# ---------------------------------------------------------------------------
# WebSocket lesson — content review
# ---------------------------------------------------------------------------

_REVIEW_BLOCK_SYSTEM = """\
You are a senior {target_lang_name} teacher reviewing a generated lesson block.

User profile:
- Native language: {native_lang_name}
- {target_lang_name} level: {level}
- Learning goals: {goals}

Topic: "{topic}"
Block: "{block_name}"

Generated content:
{content_text}

A lesson block is valuable when it teaches a LANGUAGE PATTERN — something the learner cannot figure \
out by simply looking a word up in a dictionary. This means:
- {target_lang_name} expressions that do NOT translate literally to {native_lang_name}
- Grammar or usage rules specific to this topic in {target_lang_name}
- Collocations, fixed phrases, or professional register differences
- Terminology where the correct {target_lang_name} usage is non-obvious

Return ONE of three verdicts:

"good" — the block genuinely teaches a {target_lang_name} language pattern at the right level.
  {{"verdict": "good", "feedback": "", "fallback_words": []}}

"revise" — the block has real language-pattern potential but the current content is weak.
  Describe EXACTLY what is missing or wrong. Be specific.
  Example issues:
  - "The examples are just word translations, not real collocations or usage patterns"
  - "Level is too easy: for {level} you should include more idiomatic expressions"
  - "Missing the key {target_lang_name}-specific expressions that {native_lang_name} speakers get wrong"
  - "Needs 'Common mistakes' section showing how {native_lang_name} speakers misuse these phrases"
  {{"verdict": "revise", "feedback": "specific revision instructions", "fallback_words": []}}

"words_only" — this topic/block does not contain meaningful language-pattern content for this learner.
  Use this when the content is just a word list with translations, or the topic is factual with no \
{target_lang_name}-specific usage patterns worth a full lesson.
  Return 5-10 {target_lang_name} words for the vocabulary list, strictly matched to level {level}:
  - beginner/elementary (A1–A2): basic topic words the learner doesn't know yet.
  - intermediate (B1–B2): topic-specific vocabulary, not words they clearly already know.
  - upper_intermediate/advanced (C1–C2): non-obvious terms, rare collocations, domain jargon.
    Do NOT include words any competent speaker would know — only genuinely challenging ones.
  {{"verdict": "words_only", "feedback": "brief reason", \
"fallback_words": ["word1", "word2", ...]}}

Reply ONLY in JSON without markdown.
"""


def _content_to_review_text(content: dict) -> str:
    lines = [f"Title: {content.get('title', '')}", f"Intro: {content.get('intro', '')}"]
    for s in content.get("sections", []):
        lines.append(f"\nSection [{s.get('header', '')}]:")
        for item in s.get("items", []):
            lines.append(f"  - {item}")
    return "\n".join(lines)


async def review_block_content(
    content: dict,
    topic: str,
    block_name: str,
    level: str,
    goals: str,
    native_lang: str = "en",
    target_lang: str = "en",
) -> dict:
    """Review generated block. Returns {verdict, feedback, fallback_words}."""
    log.info("[review_block_content] topic=%r block=%r level=%s", topic, block_name, level)
    native_lang_name = _LANG_NAMES.get(native_lang or "en", native_lang or "English")
    target_lang_name = _LANG_NAMES.get(target_lang or "en", target_lang or "English")
    system = _REVIEW_BLOCK_SYSTEM.format(
        topic=topic,
        block_name=block_name,
        level=level,
        goals=goals or "general language improvement",
        native_lang_name=native_lang_name,
        target_lang_name=target_lang_name,
        content_text=_truncate(_content_to_review_text(content), 1200),
    )
    try:
        raw = await _call(
            system, user="", max_tokens=400, json_mode=True,
            call_name="review_block_content", model=OPENAI_SMART_MODEL,
        )
        data = _parse_json(raw)
        verdict = data.get("verdict", "good")
        if verdict not in ("good", "revise", "words_only"):
            verdict = "good"
        result = {
            "verdict": verdict,
            "feedback": str(data.get("feedback", "")),
            "fallback_words": [str(w).strip().lower() for w in data.get("fallback_words", []) if w],
        }
        log.info(
            "[review_block_content] -> verdict=%s feedback=%r words=%s",
            result["verdict"], _truncate(result["feedback"], 100), result["fallback_words"],
        )
        return result
    except Exception:
        log.exception("[review_block_content] failed, accepting content as-is")
        return {"verdict": "good", "feedback": "", "fallback_words": []}


# ---------------------------------------------------------------------------
# WebSocket lesson — question generation
# ---------------------------------------------------------------------------

def _content_to_text(content: dict) -> str:
    lines = []
    if content.get("intro"):
        lines.append(content["intro"])
    for s in content.get("sections", []):
        lines.append(f"[{s.get('header', '')}]")
        for item in s.get("items", []):
            lines.append(f"  - {item}")
        if s.get("text"):
            lines.append(f"  {s['text']}")
    return "\n".join(lines)


_GENERATE_QUESTION_SYSTEM = """\
Create a question to test the learner's knowledge of {target_lang_name} from this lesson block.
The learner's native language is {native_lang_name}.

Topic: "{topic}"
Block: "{block_name}"
Block content:
{content_text}

Already asked (do not repeat):
{history_text}

Level: {level}

The block teaches a {target_lang_name} LANGUAGE PATTERN. Test whether the learner has grasped it.
Good question types:
- "How would you say [concept] in {target_lang_name}? (not a literal translation)"
- "Translate this {native_lang_name} phrase naturally into {target_lang_name}: [phrase]"
- "Use the expression '[{target_lang_name} phrase from block]' in a sentence"
- "What is wrong with: [incorrect {target_lang_name} sentence that a {native_lang_name} speaker would write]?"
- "What does '[{target_lang_name} fixed expression]' mean and when do you use it?"

Ask in {native_lang_name}. Test language use, not subject-matter knowledge.

Reply ONLY in JSON without markdown: {{"question": "..."}}
"""


async def generate_lesson_question(
    topic: str,
    block_name: str,
    content: dict,
    history: list[str],
    level: str,
    native_lang: str = "en",
    target_lang: str = "en",
) -> str:
    log.info("[generate_lesson_question] topic=%r block=%r history_len=%d", topic, block_name, len(history))
    native_lang_name = _LANG_NAMES.get(native_lang or "en", native_lang or "English")
    target_lang_name = _LANG_NAMES.get(target_lang or "en", target_lang or "English")
    history_text = "\n".join(f"- {q}" for q in history) if history else "none"
    system = _GENERATE_QUESTION_SYSTEM.format(
        topic=topic,
        block_name=block_name,
        content_text=_truncate(_content_to_text(content), 600),
        history_text=history_text,
        level=level,
        native_lang_name=native_lang_name,
        target_lang_name=target_lang_name,
    )
    try:
        raw = await _call(system, user="", max_tokens=150, temp=0.5, json_mode=True, call_name="generate_lesson_question")
        question = _parse_json(raw).get("question", "")
        log.info("[generate_lesson_question] -> %r", _truncate(question, 80))
        return question or f"What do you know about '{block_name}'?"
    except Exception:
        log.exception("[generate_lesson_question] failed")
        return f"Describe the key {target_lang} pattern from '{block_name}'."


# ---------------------------------------------------------------------------
# WebSocket lesson — answer check
# ---------------------------------------------------------------------------

_CHECK_LESSON_ANSWER_SYSTEM = """\
Check the learner's answer about a {target_lang_name} language pattern.
Learner's native language: {native_lang_name}.

Topic: "{topic}"
Block: "{block_name}"
Question: "{question}"
User's answer: "{answer}"
Level: {level}

The question tests knowledge of a {target_lang_name} expression, usage pattern, or grammar rule.

Outcome:
- "correct": right answer (accept minor spelling, synonyms, paraphrasing that shows understanding)
- "incorrect": wrong, but the user genuinely tried to answer
- "vague": started an answer but too imprecise to show real understanding
- "garbage": junk, random characters, or obvious attempt to skip (aaa, 123, ???, ...)

Feedback in {native_lang_name}:
- correct: one-sentence approval
- incorrect / vague: give the correct {target_lang_name} answer + 2-3 sentence {native_lang_name} \
explanation of WHY the correct form is used (focus on the language pattern, not the subject)
- garbage: ask politely to try seriously

Reply ONLY in JSON without markdown:
{{"outcome": "correct|incorrect|vague|garbage", "feedback": "..."}}
"""


async def check_lesson_answer(
    topic: str,
    block_name: str,
    question: str,
    answer: str,
    level: str,
    native_lang: str = "en",
    target_lang: str = "en",
) -> dict:
    log.info("[check_lesson_answer] block=%r answer=%r", block_name, _truncate(answer, 40))
    native_lang_name = _LANG_NAMES.get(native_lang or "en", native_lang or "English")
    target_lang_name = _LANG_NAMES.get(target_lang or "en", target_lang or "English")
    system = _CHECK_LESSON_ANSWER_SYSTEM.format(
        topic=topic,
        block_name=block_name,
        question=question,
        answer=answer,
        level=level,
        native_lang_name=native_lang_name,
        target_lang_name=target_lang_name,
    )
    try:
        raw = await _call(system, user="", max_tokens=300, temp=0.2, json_mode=True, call_name="check_lesson_answer")
        data = _parse_json(raw)
        outcome = data.get("outcome", "incorrect")
        if outcome not in ("correct", "incorrect", "vague", "garbage"):
            outcome = "incorrect"
        result = {"outcome": outcome, "feedback": data.get("feedback", "")}
        log.info("[check_lesson_answer] -> outcome=%s", outcome)
        return result
    except Exception:
        log.exception("[check_lesson_answer] failed")
        return {"outcome": "incorrect", "feedback": ""}
