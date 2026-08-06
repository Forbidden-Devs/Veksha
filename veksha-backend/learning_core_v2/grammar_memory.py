"""Domain rules for accumulating grammar patterns from reading encounters."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Sequence
from urllib.parse import urlsplit, urlunsplit


GrammarStatus = Literal["learning", "mastered"]

#: Ordered so response schemas built from it stay byte-identical between runs.
GRAMMAR_CATEGORY_ORDER: tuple[str, ...] = (
    "tense_aspect",
    "voice",
    "mood_modality",
    "clause_link",
    "negation_question",
    "agreement_form",
    "determiner_article",
    "verb_pattern",
    "word_order",
    "comparison",
)
GRAMMAR_CATEGORIES = frozenset(GRAMMAR_CATEGORY_ORDER)


@dataclass(frozen=True, slots=True)
class GrammarEncounter:
    example: str
    source_url: str = ""
    observed_at: float = 0.0


@dataclass(frozen=True, slots=True)
class GrammarMemoryItem:
    item_id: str
    language: str
    category: str
    label: str
    explanation: str
    status: GrammarStatus = "learning"
    seen_count: int = 1
    first_seen_at: float = 0.0
    last_seen_at: float = 0.0
    encounters: tuple[GrammarEncounter, ...] = ()


@dataclass(frozen=True, slots=True)
class GrammarObservation:
    language: str
    category: str
    label: str
    explanation: str
    example: str
    source_url: str = ""


class RememberGrammar:
    def __init__(self, maximum_examples: int = 6) -> None:
        if not 1 <= maximum_examples <= 20:
            raise ValueError("maximum examples must be between one and twenty")
        self._maximum_examples = maximum_examples

    def execute(
        self,
        items: Sequence[GrammarMemoryItem],
        observation: GrammarObservation,
        *,
        item_id: str,
        observed_at: float,
    ) -> tuple[GrammarMemoryItem, ...]:
        clean = _normalize_observation(observation)
        encounter = GrammarEncounter(
            example=clean.example,
            source_url=clean.source_url,
            observed_at=max(0.0, observed_at),
        )
        updated = list(items)
        key = _pattern_key(clean.language, clean.category, clean.label)
        for index, item in enumerate(updated):
            if _pattern_key(item.language, item.category, item.label) != key:
                continue
            encounters, is_new = _merge_encounter(
                item.encounters,
                encounter,
                limit=self._maximum_examples,
            )
            updated[index] = replace(
                item,
                explanation=item.explanation or clean.explanation,
                seen_count=item.seen_count + int(is_new),
                last_seen_at=max(item.last_seen_at, encounter.observed_at),
                encounters=encounters,
            )
            return tuple(updated)

        clean_id = item_id.strip()
        if not clean_id:
            raise ValueError("pattern skill requires an id")
        return (
            *updated,
            GrammarMemoryItem(
                item_id=clean_id,
                language=clean.language,
                category=clean.category,
                label=clean.label,
                explanation=clean.explanation,
                first_seen_at=encounter.observed_at,
                last_seen_at=encounter.observed_at,
                encounters=(encounter,),
            ),
        )


class SetGrammarStatus:
    def execute(self, item: GrammarMemoryItem, status: GrammarStatus) -> GrammarMemoryItem:
        if status not in {"learning", "mastered"}:
            raise ValueError("unknown pattern skill status")
        return replace(item, status=status)


def _normalize_observation(observation: GrammarObservation) -> GrammarObservation:
    category = observation.category.strip().lower()
    if category not in GRAMMAR_CATEGORIES:
        raise ValueError("unknown grammar category")
    language = observation.language.strip().lower().replace("_", "-")
    label = " ".join(observation.label.split())
    example = " ".join(observation.example.split())
    if not language or not label or not example:
        raise ValueError("grammar observation is incomplete")
    if len(label) > 160 or len(example) > 1000:
        raise ValueError("grammar observation is too long")
    return GrammarObservation(
        language=language,
        category=category,
        label=label,
        explanation=" ".join(observation.explanation.split())[:1000],
        example=example,
        source_url=_clean_source_url(observation.source_url),
    )


def _pattern_key(language: str, category: str, label: str) -> tuple[str, str, str]:
    return (
        language.strip().lower().replace("_", "-"),
        category.strip().lower(),
        " ".join(label.split()).casefold(),
    )


def _clean_source_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))[:2000]


def _merge_encounter(
    existing: Sequence[GrammarEncounter],
    candidate: GrammarEncounter,
    *,
    limit: int,
) -> tuple[tuple[GrammarEncounter, ...], bool]:
    signature = (candidate.example.casefold(), candidate.source_url.casefold())
    if any(
        (item.example.casefold(), item.source_url.casefold()) == signature
        for item in existing
    ):
        return tuple(existing), False
    return tuple([*existing, candidate][-limit:]), True
