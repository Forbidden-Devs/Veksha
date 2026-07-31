"""Domain rules for turning vocabulary observations into learner decisions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Sequence
from urllib.parse import urlsplit, urlunsplit


InboxStatus = Literal["suggested", "learning", "known", "ignored"]
InboxDecision = Literal["learn", "known", "ignore"]


@dataclass(frozen=True, slots=True)
class VocabularyEncounter:
    context: str
    source_url: str = ""
    observed_at: float = 0.0


@dataclass(frozen=True, slots=True)
class LexicalItem:
    item_id: str
    term: str
    language: str
    translation: str
    transcription: str = ""
    status: InboxStatus = "suggested"
    encounters: tuple[VocabularyEncounter, ...] = ()


@dataclass(frozen=True, slots=True)
class VocabularyProposal:
    term: str
    language: str
    translation: str
    transcription: str = ""
    context: str = ""
    source_url: str = ""


class SuggestVocabulary:
    """Merge a grounded proposal into an inbox without collapsing its senses."""

    def __init__(self, maximum_encounters: int = 12) -> None:
        if maximum_encounters < 1:
            raise ValueError("maximum encounters must be positive")
        self._maximum_encounters = maximum_encounters

    def execute(
        self,
        items: Sequence[LexicalItem],
        proposal: VocabularyProposal,
        *,
        item_id: str,
        observed_at: float,
    ) -> tuple[LexicalItem, ...]:
        normalized = _normalize_proposal(proposal)
        encounter = VocabularyEncounter(
            context=normalized.context,
            source_url=normalized.source_url,
            observed_at=max(0.0, observed_at),
        )
        key = _sense_key(
            normalized.term,
            normalized.language,
            normalized.translation,
        )
        updated = list(items)
        for index, item in enumerate(updated):
            if _sense_key(item.term, item.language, item.translation) != key:
                continue
            encounters = _merge_encounters(
                item.encounters,
                encounter,
                limit=self._maximum_encounters,
            )
            updated[index] = replace(
                item,
                transcription=item.transcription or normalized.transcription,
                encounters=encounters,
            )
            return tuple(updated)

        clean_id = item_id.strip()
        if not clean_id:
            raise ValueError("vocabulary proposal requires an item id")
        return (
            *updated,
            LexicalItem(
                item_id=clean_id,
                term=normalized.term,
                language=normalized.language,
                translation=normalized.translation,
                transcription=normalized.transcription,
                encounters=(encounter,),
            ),
        )


class DecideVocabulary:
    def execute(self, item: LexicalItem, decision: InboxDecision) -> LexicalItem:
        statuses: dict[InboxDecision, InboxStatus] = {
            "learn": "learning",
            "known": "known",
            "ignore": "ignored",
        }
        if decision not in statuses:
            raise ValueError("unknown vocabulary inbox decision")
        if item.status != "suggested":
            raise ValueError("vocabulary item has already been decided")
        return replace(item, status=statuses[decision])


def _normalize_proposal(proposal: VocabularyProposal) -> VocabularyProposal:
    term = " ".join(proposal.term.split())
    translation = " ".join(proposal.translation.split())
    language = proposal.language.strip().lower().replace("_", "-")
    if not term or not translation:
        raise ValueError("vocabulary proposal requires a term and translation")
    if not language:
        raise ValueError("vocabulary proposal requires a language")
    if len(term) > 200 or len(translation) > 500:
        raise ValueError("vocabulary proposal is too long")
    return VocabularyProposal(
        term=term,
        language=language,
        translation=translation,
        transcription=proposal.transcription.strip()[:200],
        context=" ".join(proposal.context.split())[:1000],
        source_url=_clean_source_url(proposal.source_url),
    )


def _sense_key(term: str, language: str, translation: str) -> tuple[str, str, str]:
    return (
        " ".join(term.split()).casefold(),
        language.strip().lower().replace("_", "-"),
        " ".join(translation.split()).casefold(),
    )


def _clean_source_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))[:2000]


def _merge_encounters(
    existing: Sequence[VocabularyEncounter],
    candidate: VocabularyEncounter,
    *,
    limit: int,
) -> tuple[VocabularyEncounter, ...]:
    signature = (candidate.context.casefold(), candidate.source_url.casefold())
    retained = [
        encounter
        for encounter in existing
        if (encounter.context.casefold(), encounter.source_url.casefold()) != signature
    ]
    return tuple([*retained, candidate][-limit:])
