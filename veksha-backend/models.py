"""
models.py — VocaBot data models (spec v3, section 2).

All models are dataclasses with to_dict/from_dict for JSON serialization
(spec 2: one JSON file per user).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal, Optional, Union


# ---------------------------------------------------------------------------
# Word (spec 2.1)
# ---------------------------------------------------------------------------

@dataclass
class Word:
    name: str                              # word or phrase
    language: str = ""                     # target language this word belongs to
    context: str = ""                      # context from the source text (empty if none)
    translation: str = ""                  # saved dictionary translation
    transcription: str = ""                # IPA or readable phonetic transcription
    counter: int = -1                      # -1 = new (not reviewed yet); otherwise number of reviews
    known: Union[bool, str] = False        # True/False or string explaining what user doesn't know
    delayed: bool = False                  # delayed — priority +1 in next training session
    next_review: float = 0.0               # timestamp of next review
    added_at: float = 0.0                  # timestamp when the word entered the vocabulary
    extra_data: str = ""                   # translation/example shown on incorrect answer
    sentence_mining: dict[str, Any] = field(default_factory=dict)
    # FSRS memory state (see fsrs.py); stability == 0.0 means "no state yet",
    # the first review initializes it. Existing pre-FSRS words migrate the
    # same way: their fixed-interval history is simply not counted.
    stability: float = 0.0                 # S: interval in days at 90% recall
    difficulty: float = 0.0                # D: 1..10
    last_review: float = 0.0               # timestamp of the latest review
    lapses: int = 0                        # number of Again (incorrect) reviews

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Word":
        return Word(
            name=d["name"],
            language=d.get("language", ""),
            context=d.get("context", ""),
            translation=d.get("translation", ""),
            transcription=d.get("transcription", ""),
            counter=d.get("counter", -1),
            known=d.get("known", False),
            delayed=d.get("delayed", False),
            next_review=d.get("next_review", 0.0),
            added_at=d.get("added_at", 0.0),
            extra_data=d.get("extra_data", ""),
            sentence_mining=d.get("sentence_mining", {}) or {},
            stability=d.get("stability", 0.0),
            difficulty=d.get("difficulty", 0.0),
            last_review=d.get("last_review", 0.0),
            lapses=d.get("lapses", 0),
        )


# ---------------------------------------------------------------------------
# Patch (spec 3.4) — patch format for apply_kb_changes
# ---------------------------------------------------------------------------

PatchType = Literal[
    "add_word",
    "delete_word",
    "add_topic",
    "delete_topic",
    "mark_known",       # special case "word learned" (spec 3.4)
]


@dataclass
class Patch:
    type: PatchType
    value: str
    # Extra fields for add_word — populated by code or LLM
    context: str = ""
    counter: int = -1
    known: Union[bool, str] = False

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Patch":
        return Patch(
            type=d["type"],
            value=d["value"],
            context=d.get("context", ""),
            counter=d.get("counter", -1),
            known=d.get("known", False),
        )


# ---------------------------------------------------------------------------
# UserSettings — user preferences (English level, goals, general prompt)
# ---------------------------------------------------------------------------

EnglishLevel = Literal["beginner", "elementary", "intermediate", "upper_intermediate", "advanced"]

VALID_ENGLISH_LEVELS: tuple[str, ...] = (
    "a1", "a1_a2", "a2", "a2_b1", "b1", "b1_b2", "b2", "b2_c1", "c1", "c1_c2", "c2",
)


@dataclass
class UserSettings:
    display_name: str = ""                 # user-facing name; the account id (username) is internal
    native_lang: str = ""                  # ISO 639-1, e.g. "ru" — user's native language
    target_lang: str = ""                  # active language being studied
    language_settings: dict[str, dict[str, str]] = field(default_factory=dict)
    # Reminder intensity (single slider):
    #   1 = plain system notification only
    #   2 = + in-page pop-up with page blur
    #   3 = + shown frequently (hourly instead of every 12h)
    reminder_level: int = 2
    # Separate flag: the in-page close button runs away ("overseer" mode).
    overseer: bool = False
    mining_same_level_examples: int = 2
    mining_higher_level_examples: int = 1

    @property
    def target_langs(self) -> list[str]:
        return list(self.language_settings)

    @property
    def english_level(self) -> Optional[str]:
        return self.language_settings.get(self.target_lang, {}).get("level") or None

    @property
    def goals(self) -> str:
        return self.language_settings.get(self.target_lang, {}).get("goals", "")

    @property
    def general_prompt(self) -> str:
        return self.language_settings.get(self.target_lang, {}).get("prompt", "")

    def is_onboarded(self) -> bool:
        return bool(self.native_lang and self.target_lang)


# ---------------------------------------------------------------------------
# Lesson models (WebSocket topic learning — browser extension)
# ---------------------------------------------------------------------------

@dataclass
class LessonQA:
    question: str
    outcome: str  # "correct" | "incorrect" | "vague"

    def to_dict(self) -> dict:
        return {"question": self.question, "outcome": self.outcome}

    @staticmethod
    def from_dict(d: dict) -> "LessonQA":
        return LessonQA(question=d["question"], outcome=d["outcome"])


@dataclass
class LessonBlock:
    name: str
    content_json: str = ""       # JSON string of BlockContent; empty until first generation
    mastery_score: float = 0.0   # 0.0–1.0
    history: list[LessonQA] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "content_json": self.content_json,
            "mastery_score": self.mastery_score,
            "history": [qa.to_dict() for qa in self.history],
        }

    @staticmethod
    def from_dict(d: dict) -> "LessonBlock":
        return LessonBlock(
            name=d["name"],
            content_json=d.get("content_json", ""),
            mastery_score=d.get("mastery_score", 0.0),
            history=[LessonQA.from_dict(h) for h in d.get("history", [])],
        )


@dataclass
class LessonTopic:
    name: str
    blocks: list[LessonBlock] = field(default_factory=list)
    is_complete: bool = False    # True when there is nothing more to add
    last_reviewed: Optional[float] = None

    def find_block(self, name: str) -> Optional[LessonBlock]:
        for b in self.blocks:
            if b.name == name:
                return b
        return None

    def avg_mastery(self) -> float:
        with_content = [b for b in self.blocks if b.content_json]
        if not with_content:
            return 0.0
        return sum(b.mastery_score for b in with_content) / len(with_content)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "blocks": [b.to_dict() for b in self.blocks],
            "is_complete": self.is_complete,
            "last_reviewed": self.last_reviewed,
        }

    @staticmethod
    def from_dict(d: dict) -> "LessonTopic":
        return LessonTopic(
            name=d["name"],
            blocks=[LessonBlock.from_dict(b) for b in d.get("blocks", [])],
            is_complete=d.get("is_complete", False),
            last_reviewed=d.get("last_reviewed"),
        )
