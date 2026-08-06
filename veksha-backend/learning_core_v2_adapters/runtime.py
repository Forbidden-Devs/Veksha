"""Composition root for independently rewritten learning services."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import db
from learning_core_v2.catalog_translation import TranslateCatalog
from learning_core_v2.dictionary import EnrichDictionaryEntry
from learning_core_v2.explanation import ExplainText
from learning_core_v2.grammar_analysis import AnalyzeGrammar
from learning_core_v2.goal import (
    BuildGoalStep,
    CheckGoalAnswer,
    CloseGoal,
    FrameGoal,
    GoalRoute,
)
from learning_core_v2.phrase_mining import MinePhraseVocabulary
from learning_core_v2.practice import (
    BuildPracticeTask,
    CheckPracticeAnswer,
    PracticePlanner,
    PracticeQueue,
)
from learning_core_v2.reading_coach import BuildReadingQuestion, CheckReadingAnswer
from learning_core_v2.sentence_mining import BuildSentenceMiningCard
from learning_core_v2.subtitles import TranslateSubtitles
from learning_core_v2.translation import TranslateText, VocabularySink
from storage import UserStorage
from usage_context import get_usage_user

from .openai_responses import OpenAIResponsesLanguageProvider
from .grammar import CachedGrammarProvider
from .practice import RandomChoiceSource, UuidIdentifierSource
from .subtitles import CachedSubtitleTranslator
from .vocabulary import (
    CollectingVocabularySink,
    LexiconVocabularyInboxSink,
)


log = logging.getLogger(__name__)


def _record_usage(call_name: str, model: str, usage: Mapping[str, Any]) -> None:
    username = get_usage_user()
    if not username:
        return
    input_details = usage.get("input_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or {}
    try:
        db.ai_usage_record(
            username=username,
            call_name=call_name,
            model=model,
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            cached_tokens=input_details.get("cached_tokens", 0),
            reasoning_tokens=output_details.get("reasoning_tokens", 0),
        )
    except Exception:
        log.exception("Failed to persist core-v2 AI usage for %s", call_name)


def _provider(model_variable: str, default_model: str) -> OpenAIResponsesLanguageProvider:
    return OpenAIResponsesLanguageProvider(
        api_key=os.getenv("OPENAI_API_KEY", ""),
        model=os.getenv(model_variable, default_model),
        usage_recorder=_record_usage,
        timeout_seconds=float(os.getenv("VEKSHA_CORE_V2_LLM_TIMEOUT_SECONDS", "30")),
    )


def _phrase_miner() -> MinePhraseVocabulary | None:
    if os.getenv("VEKSHA_PHRASE_MINING_ENABLED", "1").lower() not in {
        "1",
        "true",
        "yes",
    }:
        return None
    return MinePhraseVocabulary(
        _provider("VEKSHA_CORE_V2_PHRASE_MINING_MODEL", "gpt-5.6-luna")
    )


def _vocabulary_sink(storage: UserStorage) -> VocabularySink:
    return LexiconVocabularyInboxSink(
        storage.lexicon,
        storage.settings,
        storage.save,
        phrase_miner=_phrase_miner(),
    )


def build_translate_text(storage: UserStorage) -> TranslateText:
    provider = _provider("VEKSHA_CORE_V2_TRANSLATION_MODEL", "gpt-5.6-luna")
    return TranslateText(provider, _vocabulary_sink(storage))


def build_deferred_translate_text(
    storage: UserStorage,
) -> tuple[TranslateText, CollectingVocabularySink, VocabularySink]:
    provider = _provider("VEKSHA_CORE_V2_TRANSLATION_MODEL", "gpt-5.6-luna")
    collector = CollectingVocabularySink()
    return TranslateText(provider, collector), collector, _vocabulary_sink(storage)


def build_dictionary_enrichment() -> EnrichDictionaryEntry:
    provider = _provider("VEKSHA_CORE_V2_DICTIONARY_MODEL", "gpt-5.6-luna")
    return EnrichDictionaryEntry(provider)


def build_sentence_mining() -> BuildSentenceMiningCard:
    provider = _provider("VEKSHA_CORE_V2_SENTENCE_MINING_MODEL", "gpt-5.6-luna")
    return BuildSentenceMiningCard(provider)


def build_explain_text() -> ExplainText:
    return ExplainText(_provider("VEKSHA_CORE_V2_TRANSLATION_MODEL", "gpt-5.6-luna"))


@lru_cache(maxsize=1)
def build_grammar_analyzer() -> AnalyzeGrammar:
    provider = _provider("VEKSHA_CORE_V2_GRAMMAR_MODEL", "gpt-5.6-luna")
    return AnalyzeGrammar(CachedGrammarProvider(provider))


@lru_cache(maxsize=1)
def build_subtitle_translator() -> CachedSubtitleTranslator:
    provider = _provider("VEKSHA_CORE_V2_SUBTITLES_MODEL", "gpt-5.6-luna")
    return CachedSubtitleTranslator(TranslateSubtitles(provider))


@lru_cache(maxsize=1)
def build_catalog_translator() -> TranslateCatalog:
    provider = _provider("VEKSHA_CORE_V2_I18N_MODEL", "gpt-5.6-luna")
    return TranslateCatalog(provider)


def build_practice_planner(queue: PracticeQueue) -> PracticePlanner:
    return PracticePlanner(queue, RandomChoiceSource())


def build_practice_services() -> tuple[BuildPracticeTask, CheckPracticeAnswer]:
    provider = _provider("VEKSHA_CORE_V2_TRAINING_MODEL", "gpt-5.6-terra")
    return BuildPracticeTask(provider, UuidIdentifierSource()), CheckPracticeAnswer(provider)


@dataclass(frozen=True, slots=True)
class GoalServices:
    """Everything one goal-oriented lesson session needs."""

    framer: FrameGoal
    route: GoalRoute
    step_builder: BuildGoalStep
    answer_checker: CheckGoalAnswer
    closer: CloseGoal


def build_goal_services() -> GoalServices:
    provider = _provider("VEKSHA_CORE_V2_LESSON_MODEL", "gpt-5.6-terra")
    return GoalServices(
        framer=FrameGoal(provider),
        route=GoalRoute(),
        step_builder=BuildGoalStep(provider, UuidIdentifierSource()),
        answer_checker=CheckGoalAnswer(provider),
        closer=CloseGoal(provider),
    )


def build_reading_comprehension_services() -> tuple[
    BuildReadingQuestion, CheckReadingAnswer
]:
    provider = _provider("VEKSHA_CORE_V2_READING_MODEL", "gpt-5.6-luna")
    return BuildReadingQuestion(provider), CheckReadingAnswer(provider)
