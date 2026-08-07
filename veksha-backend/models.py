"""
models.py — VocaBot data models (spec v3, section 2).

All models are dataclasses with to_dict/from_dict for JSON serialization
(spec 2: one JSON file per user).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# UserSettings — user preferences (English level, goals, general prompt)
# ---------------------------------------------------------------------------

VALID_ENGLISH_LEVELS = tuple(
    f"{left}_{right}" if right else left
    for left, right in (
        ("a1", ""), ("a1", "a2"), ("a2", ""), ("a2", "b1"),
        ("b1", ""), ("b1", "b2"), ("b2", ""), ("b2", "c1"),
        ("c1", ""), ("c1", "c2"), ("c2", ""),
    )
)


@dataclass(slots=True)
class UserSettings:
    display_name: str = ""
    native_lang: str = ""
    target_lang: str = ""
    language_settings: dict[str, dict[str, str]] = field(default_factory=dict)
    reminder_level: int = 2
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
