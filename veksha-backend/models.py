"""
models.py — VocaBot data models (spec v3, section 2).

All models are dataclasses with to_dict/from_dict for JSON serialization
(spec 2: one JSON file per user).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


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
    # Compatibility field: enables the explicit full-page focus safeguard.
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
