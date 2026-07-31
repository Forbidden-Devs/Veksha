"""Adapter from core-v2 vocabulary observations to Veksha user storage."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable

from learning_core_v2.acquisition import SuggestVocabulary, VocabularyProposal
from learning_core_v2.phrase_mining import MinePhraseVocabulary, PhraseMiningRequest
from learning_core_v2.translation import VocabularyObservation
from models import Patch
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


class UserStorageVocabularySink:
    def __init__(
        self,
        storage: UserStorage,
        *,
        phrase_miner: MinePhraseVocabulary | None = None,
    ) -> None:
        self._storage = storage
        self._phrase_miner = phrase_miner

    async def observe(self, observation: VocabularyObservation) -> None:
        observed_language = _language_base(observation.source_language)
        learning_language = _language_base(self._storage.settings.target_lang)
        if not observed_language or observed_language == "auto":
            return
        if learning_language and observed_language != learning_language:
            return

        if not observation.is_lexical_unit:
            await self._observe_phrase(observation)
            return
        if not observation.dictionary_form:
            return

        word = self._storage.find_word(observation.dictionary_form)
        if word is None:
            self._storage.apply_kb_changes(
                [
                    Patch(
                        type="add_word",
                        value=observation.dictionary_form,
                        context=observation.source_text,
                        counter=0,
                        known=False,
                    )
                ]
            )
            word = self._storage.find_word(observation.dictionary_form)

        if word is None:
            return
        word.translation = observation.translation
        word.transcription = observation.transcription
        self._storage.save()

    async def _observe_phrase(self, observation: VocabularyObservation) -> None:
        if self._phrase_miner is None:
            return
        words = self._storage.words
        values = words.values() if isinstance(words, dict) else words
        existing_terms = tuple(
            word.name
            for word in values
            if _language_base(
                getattr(word, "language", "") or self._storage.settings.target_lang
            )
            == _language_base(self._storage.settings.target_lang)
        )
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
                    existing_terms=existing_terms,
                )
            )
        except Exception:
            log.exception("core-v2 phrase mining failed; translation remains available")
            return

        patches = [
            Patch(
                type="add_word",
                value=candidate.term,
                context=candidate.context,
                counter=-1,
                known=False,
            )
            for candidate in candidates
            if self._storage.find_word(candidate.term) is None
        ]
        if not patches:
            return
        self._storage.apply_kb_changes(patches)
        for candidate in candidates:
            word = self._storage.find_word(candidate.term)
            if word is None:
                continue
            word.translation = candidate.translation
            word.transcription = candidate.transcription
        self._storage.save()


class UserStorageVocabularyInboxSink:
    """Store translation observations as suggestions awaiting a user decision."""

    def __init__(
        self,
        storage: UserStorage,
        *,
        phrase_miner: MinePhraseVocabulary | None = None,
        clock: Callable[[], float] = time.time,
        identifier: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self._storage = storage
        self._phrase_miner = phrase_miner
        self._clock = clock
        self._identifier = identifier
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
            if self._storage.find_word(proposal.term) is not None:
                continue
            try:
                updated = self._suggest.execute(
                    self._storage.vocabulary_inbox,
                    proposal,
                    item_id=self._identifier(),
                    observed_at=self._clock(),
                )
            except ValueError:
                log.warning("discarding invalid vocabulary inbox proposal")
                continue
            self._storage.vocabulary_inbox = list(updated)
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
                        word.name for word in self._storage.words
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
