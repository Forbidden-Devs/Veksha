"""Independent replacement for Veksha's learning domain."""

from .explanation import ExplainText, ExplanationRequest, ExplanationResult
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
from .translation import (
    TextTranslation,
    TranslateText,
    TranslationRequest,
    TranslationResult,
)

__all__ = [
    "ExplainText",
    "ExplanationRequest",
    "ExplanationResult",
    "BuildLessonQuestion",
    "CheckLessonAnswer",
    "LearnerProfile",
    "LessonMaterial",
    "LessonTopic",
    "LessonUnit",
    "PrepareLesson",
    "QuestionSchedule",
    "RecordLessonResults",
    "AnswerCheckRequest",
    "AnswerEvaluation",
    "BuildPracticeTask",
    "CheckPracticeAnswer",
    "PracticeQueue",
    "PracticeTask",
    "PracticeWord",
    "TextTranslation",
    "TranslateText",
    "TranslationRequest",
    "TranslationResult",
]
