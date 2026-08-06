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
