"""Independent replacement for Veksha's learning domain."""

from .dictionary import (
    DictionaryDetails,
    DictionaryLookupRequest,
    EnrichDictionaryEntry,
)
from .explanation import ExplainText, ExplanationRequest, ExplanationResult
from .immersion import (
    AnalyzeImmersion,
    ImmersionBlock,
    ImmersionContext,
    ImmersionSentence,
)
from .lesson import (
    BuildLessonQuestion,
    CheckLessonAnswer,
    LearnerProfile,
    LessonMaterial,
    LessonTopic,
    LessonUnit,
    PrepareLesson,
    QuestionSchedule,
    RecordLessonResults,
    TopicReviewPolicy,
)
from .phrase_mining import (
    MinePhraseVocabulary,
    PhraseMiningRequest,
    VocabularyCandidate,
)
from .practice import (
    AnswerCheckRequest,
    AnswerEvaluation,
    BuildPracticeTask,
    CheckPracticeAnswer,
    PracticeQueue,
    PracticeTask,
    PracticeWord,
)
from .sentence_mining import (
    BuildSentenceMiningCard,
    SentenceMiningCard,
    SentenceMiningRequest,
)
from .translation import (
    TextTranslation,
    TranslateText,
    TranslationRequest,
    TranslationResult,
)

__all__ = [
    "DictionaryDetails",
    "DictionaryLookupRequest",
    "EnrichDictionaryEntry",
    "ExplainText",
    "ExplanationRequest",
    "ExplanationResult",
    "AnalyzeImmersion",
    "ImmersionBlock",
    "ImmersionContext",
    "ImmersionSentence",
    "BuildLessonQuestion",
    "CheckLessonAnswer",
    "LearnerProfile",
    "LessonMaterial",
    "LessonTopic",
    "LessonUnit",
    "PrepareLesson",
    "QuestionSchedule",
    "RecordLessonResults",
    "TopicReviewPolicy",
    "MinePhraseVocabulary",
    "PhraseMiningRequest",
    "VocabularyCandidate",
    "AnswerCheckRequest",
    "AnswerEvaluation",
    "BuildPracticeTask",
    "CheckPracticeAnswer",
    "PracticeQueue",
    "PracticeTask",
    "PracticeWord",
    "BuildSentenceMiningCard",
    "SentenceMiningCard",
    "SentenceMiningRequest",
    "TextTranslation",
    "TranslateText",
    "TranslationRequest",
    "TranslationResult",
]
