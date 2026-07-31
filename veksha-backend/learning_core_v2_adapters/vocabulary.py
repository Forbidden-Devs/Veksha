"""Adapter from core-v2 vocabulary observations to Veksha user storage."""

from __future__ import annotations

import logging

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
