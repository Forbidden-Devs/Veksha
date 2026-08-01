"""Adapter from core-v2 vocabulary observations to Veksha user storage."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from learning_core_v2.acquisition import SuggestVocabulary, VocabularyProposal
from learning_core_v2.phrase_mining import MinePhraseVocabulary, PhraseMiningRequest
from learning_core_v2.translation import VocabularyObservation
from storage import UserStorage


log = logging.getLogger(__name__)


def _language_base(code: str) -> str:
    return code.strip().lower().replace("_", "-").split("-", 1)[0]


class CollectingVocabularySink:
    """Collect observations so an HTTP adapter can persist them in background."""

    def __init__(self) -> None:
        self.observations: list[VocabularyObservation] = []

    async def observe(self, observation: VocabularyObservation) -> None:
        self.observations.append(observation)


class UserStorageVocabularyInboxSink:
    """Store translation observations as suggestions awaiting a user decision."""

    def __init__(
        self,
        storage: UserStorage,
        *,
        phrase_miner: MinePhraseVocabulary | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._storage = storage
        self._phrase_miner = phrase_miner
        self._clock = clock
        self._suggest = SuggestVocabulary()

    async def observe(self, observation: VocabularyObservation) -> None:
        learning_language = _language_base(self._storage.settings.target_lang)
        observation = _learning_observation(observation, learning_language)
        if observation is None:
            return
        observed_language = _language_base(observation.source_language)

        proposals: list[VocabularyProposal] = []
        if observation.is_lexical_unit:
            term = observation.dictionary_form.strip()
            if term:
                proposals.append(
                    VocabularyProposal(
                        term=term,
                        language=observed_language,
                        translation=observation.translation,
                        transcription=observation.transcription,
                        context=observation.source_text,
                        source_url=observation.source_url,
                    )
                )
        elif self._phrase_miner is not None:
            proposals.extend(await self._mine_phrase(observation))

        changed = False
        for proposal in proposals:
            try:
                updated = self._suggest.execute(
                    self._storage.lexical_items,
                    proposal,
                    observed_at=self._clock(),
                )
            except ValueError:
                log.warning("discarding invalid vocabulary inbox proposal")
                continue
            self._storage.lexical_items = list(updated)
            changed = True
        if changed:
            self._storage.save()

    async def _mine_phrase(
        self, observation: VocabularyObservation
    ) -> list[VocabularyProposal]:
        try:
            candidates = await self._phrase_miner.execute(
                PhraseMiningRequest(
                    source_text=observation.source_text,
                    translated_text=observation.translation,
                    learning_language=self._storage.settings.target_lang,
                    native_language=(
                        getattr(self._storage.settings, "native_lang", "en") or "en"
                    ),
                    proficiency=(
                        getattr(
                            self._storage.settings,
                            "english_level",
                            "intermediate",
                        )
                        or "intermediate"
                    ),
                    existing_terms=tuple(
                        item.term for item in self._storage.lexical_items
                    ),
                )
            )
        except Exception:
            log.exception("core-v2 phrase mining failed; translation remains available")
            return []
        return [
            VocabularyProposal(
                term=candidate.term,
                language=observation.source_language,
                translation=candidate.translation,
                transcription=candidate.transcription,
                context=candidate.context,
                source_url=observation.source_url,
            )
            for candidate in candidates
        ]


def _learning_observation(
    observation: VocabularyObservation,
    learning_language: str,
) -> VocabularyObservation | None:
    source_language = _language_base(observation.source_language)
    if source_language and source_language != "auto" and source_language == learning_language:
        return observation

    target_language = _language_base(observation.target_language)
    if target_language != learning_language:
        return None
    return VocabularyObservation(
        source_text=observation.translation,
        translation=observation.source_text,
        source_language=target_language,
        target_language=source_language,
        is_lexical_unit=observation.is_lexical_unit,
        dictionary_form=(
            observation.translation if observation.is_lexical_unit else ""
        ),
        transcription="",
        source_url=observation.source_url,
    )
