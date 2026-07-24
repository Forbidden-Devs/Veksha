"""Adapter from core-v2 vocabulary observations to Veksha user storage."""

from __future__ import annotations

from learning_core_v2.translation import VocabularyObservation
from models import Patch
from storage import UserStorage


def _language_base(code: str) -> str:
    return code.strip().lower().replace("_", "-").split("-", 1)[0]


class UserStorageVocabularySink:
    def __init__(self, storage: UserStorage) -> None:
        self._storage = storage

    async def observe(self, observation: VocabularyObservation) -> None:
        if not observation.is_lexical_unit or not observation.dictionary_form:
            return

        observed_language = _language_base(observation.source_language)
        learning_language = _language_base(self._storage.settings.target_lang)
        if not observed_language or observed_language == "auto":
            return
        if learning_language and observed_language != learning_language:
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
