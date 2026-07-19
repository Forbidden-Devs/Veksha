"""LLM grammar-role analysis for Grammar Lens page highlighting."""
from __future__ import annotations

import json
import logging

from db_cache import cache_get, cache_set, make_key
from llm._base import _LANG_NAMES, _call, _clean_json, _truncate

log = logging.getLogger(__name__)

_NS = "grammar_lens_v2"
VALID_ROLES = frozenset({"subject", "verb", "object", "place", "time", "modifier"})
VALID_CATEGORIES = frozenset({
    "tense_aspect", "voice", "mood_modality", "clause_link",
    "negation_question", "agreement_form", "determiner_article",
    "verb_pattern", "word_order", "comparison",
})

_SYSTEM = """\
You are a multilingual grammar parser for a reading-assistance browser tool.

Analyze the page-text chunk in whatever language it is written. Produce two
complementary layers. Preserve every returned text span EXACTLY (same spelling,
punctuation, whitespace and casing) so it can be found verbatim in the source.

Layer 1, "segments": grammatical roles. Segment spans must be non-overlapping
and in source order.

Allowed roles:
- subject: who or what performs/is described by the clause
- verb: the complete verb or verb phrase, including auxiliaries when adjacent
- object: direct or indirect object/complement
- place: phrase expressing location or direction
- time: phrase expressing time, duration or frequency
- modifier: important adjective/adverb phrase that adds manner or description

Layer 2, "annotations": learner-useful grammar in context. Annotation spans may
overlap role segments and each other. Choose only constructions that are clearly
present and useful to a language learner, with at most 6 annotations per chunk.
Allowed categories:
- tense_aspect: tense, time reference, perfective/progressive aspect
- voice: active, passive, middle or equivalent voice distinctions
- mood_modality: modal meaning, imperative, subjunctive, evidentiality
- clause_link: conditionals, relative/subordinate clauses, cause, purpose, contrast
- negation_question: negation, question formation or scope
- agreement_form: agreement, case, gender, number or important inflection
- determiner_article: articles, determiners, definiteness or quantifiers
- verb_pattern: infinitive/gerund/participle, phrasal or separable verb patterns
- word_order: marked or learner-relevant word order
- comparison: comparative, superlative or comparison pattern

For tense/aspect, attach each annotation to the complete verb phrase that shows
it. If a sentence switches tense/aspect, return separate annotations for the
corresponding verb phrases. For other categories, select the smallest complete
span that demonstrates the construction. Do not force English concepts onto a
language that does not grammaticalize them. Skip obvious facts that do not help
learning, navigation, URLs, code, and incomplete fragments.

The learner's approximate CEFR level is {learner_level}. Prefer patterns that
are commonly confusing at that level or one step above it. Give priority to
tense/aspect contrasts, auxiliary and modal meaning, voice, clause relationships,
negation/question scope, agreement/case/articles, and non-obvious verb patterns
or word order. Never invent a feature merely to fill a category.

For every annotation, "label" is a short conventional grammar name and
"explanation" briefly explains the form and its meaning here. Write labels and
all explanations in {native_name}. Keep role explanations very short.

Reply ONLY in JSON, no markdown:
{{"segments":[{{"text":"exact source span","role":"subject","explanation":"short explanation"}}],"annotations":[{{"text":"had already left","category":"tense_aspect","label":"past perfect","explanation":"completed before another past event"}}]}}
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


def _normalise_annotations(text: str, items: object) -> list[dict[str, str]]:
    """Validate exact source anchors while allowing intentional overlaps."""
    if not isinstance(items, list):
        return []
    result: list[tuple[int, dict[str, str]]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        segment = str(item.get("text", ""))
        category = str(item.get("category", "")).lower().strip()
        label = str(item.get("label", "") or "").strip()[:80]
        if not segment.strip() or category not in VALID_CATEGORIES or not label:
            continue
        index = text.find(segment)
        signature = (segment, category, label.casefold())
        if index < 0 or signature in seen:
            continue
        seen.add(signature)
        result.append((index, {
            "text": segment,
            "category": category,
            "label": label,
            "explanation": str(item.get("explanation", "") or "").strip()[:240],
        }))
    result.sort(key=lambda pair: (pair[0], len(pair[1]["text"])))
    return [item for _, item in result[:6]]


async def analyze_grammar_block(
    text: str,
    native_lang: str,
    learner_level: str = "unknown",
) -> dict[str, list[dict[str, str]]]:
    text = text or ""
    if not text.strip():
        return {"segments": [], "annotations": []}

    key = make_key(_NS, text, native_lang, learner_level)
    cached = await cache_get(_NS, key)
    if isinstance(cached, dict):
        return {
            "segments": _normalise_segments(text, cached.get("segments", [])),
            "annotations": _normalise_annotations(text, cached.get("annotations", [])),
        }

    try:
        raw = await _call(
            _SYSTEM.format(
                native_name=_lang_name(native_lang),
                learner_level=learner_level or "unknown",
            ),
            user=text,
            max_tokens=1800,
            json_mode=True,
            call_name="grammar_lens_analyze",
        )
        data = json.loads(_clean_json(raw))
        result = {
            "segments": _normalise_segments(text, data.get("segments", [])),
            "annotations": _normalise_annotations(text, data.get("annotations", [])),
        }
    except Exception as exc:  # noqa: BLE001 — page enhancement must fail quietly
        log.error("[grammar_lens] analysis failed: %s | text=%r", exc, _truncate(text))
        return {"segments": [], "annotations": []}

    await cache_set(_NS, key, result)
    return result
