"""Independent replacement for Veksha's learning domain."""

from .acquisition import (
    DecideVocabulary,
    LexicalItem,
    SuggestVocabulary,
    VocabularyEncounter,
    VocabularyProposal,
)
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
from .grammar_memory import (
    GrammarEncounter,
    GrammarMemoryItem,
    GrammarObservation,
    RememberGrammar,
    SetGrammarStatus,
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
from .reading_coach import (
    AssessReading,
    ReadingAssessment,
    ReadingObstacle,
    ReadingToken,
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
    "DecideVocabulary",
    "LexicalItem",
    "SuggestVocabulary",
    "VocabularyEncounter",
    "VocabularyProposal",
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
    "GrammarEncounter",
    "GrammarMemoryItem",
    "GrammarObservation",
    "RememberGrammar",
    "SetGrammarStatus",
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
    "AssessReading",
    "ReadingAssessment",
    "ReadingObstacle",
    "ReadingToken",
    "BuildSentenceMiningCard",
    "SentenceMiningCard",
    "SentenceMiningRequest",
    "TextTranslation",
    "TranslateText",
    "TranslationRequest",
    "TranslationResult",
]
