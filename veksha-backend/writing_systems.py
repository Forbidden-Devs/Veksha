"""Writing-system support for alphabetic language courses.

The classification is intentionally conservative.  Logographic and mixed
systems are reported as unsupported until they have language-specific course
designs; ambiguous multi-script language codes are left on the standard path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


LiteracyStage = Literal["not_started", "learning", "mastered"]
WritingSupportKind = Literal[
    "standard", "latin_extended", "script_variant", "new_alphabet", "unsupported"
]
TranscriptionMode = Literal["always", "on_demand", "standard"]

LITERACY_STAGES = {"not_started", "learning", "mastered"}

# Languages whose normal beginner path cannot be modelled as an alphabet
# course.  Japanese is mixed; Chinese is logographic.
_UNSUPPORTED = {"zh", "ja"}

# Codes with genuinely ambiguous everyday script choices.  Do not guess which
# alphabet the learner selected from the language code alone.
_MULTI_SCRIPT = {"az", "bs", "kk", "ku", "mn", "pa", "sr", "uz"}

_SCRIPT_BY_LANGUAGE: dict[str, tuple[str, str]] = {
    # Cyrillic
    **{code: ("cyrl", "Cyrillic") for code in (
        "ab", "av", "ba", "be", "bg", "ce", "cv", "ky", "mk", "os", "ru", "tg", "tt", "uk",
    )},
    # Greek, Armenian, Georgian and Hangul
    "el": ("grek", "Greek alphabet"),
    "hy": ("armn", "Armenian alphabet"),
    "ka": ("geor", "Georgian alphabet"),
    "ko": ("hang", "Hangul"),
    # Abjads
    **{code: ("arab", "Arabic script") for code in (
        "ar", "fa", "ps", "sd", "ug", "ur",
    )},
    "he": ("hebr", "Hebrew alphabet"),
    "yi": ("hebr", "Hebrew alphabet"),
    # Brahmic abugidas and related alphabetic/syllabic systems.
    "am": ("ethi", "Ge'ez script"),
    "as": ("beng", "Bengali–Assamese script"),
    "bn": ("beng", "Bengali alphabet"),
    "bo": ("tibt", "Tibetan script"),
    "dv": ("thaa", "Thaana"),
    "dz": ("tibt", "Tibetan script"),
    "gu": ("gujr", "Gujarati script"),
    "hi": ("deva", "Devanagari"),
    "km": ("khmr", "Khmer script"),
    "kn": ("knda", "Kannada script"),
    "lo": ("laoo", "Lao script"),
    "ml": ("mlym", "Malayalam script"),
    "mr": ("deva", "Devanagari"),
    "my": ("mymr", "Burmese script"),
    "ne": ("deva", "Devanagari"),
    "or": ("orya", "Odia script"),
    "sa": ("deva", "Devanagari"),
    "si": ("sinh", "Sinhala script"),
    "ta": ("taml", "Tamil script"),
    "te": ("telu", "Telugu script"),
    "th": ("thai", "Thai script"),
    "ti": ("ethi", "Ge'ez script"),
}

# Latin languages whose beginner course benefits from a small orthography
# module even when the learner already reads Latin script.
_LATIN_EXTENDED = {
    "af", "ca", "cs", "cy", "da", "de", "eo", "es", "et", "eu", "fi",
    "fo", "fr", "ga", "gd", "gl", "hr", "hu", "is", "it", "lt", "lv",
    "mt", "nl", "no", "pl", "pt", "ro", "sk", "sl", "sv", "tr", "vi",
}


@dataclass(frozen=True, slots=True)
class WritingSystemProfile:
    kind: WritingSupportKind
    script: str
    script_name: str
    literacy_stage: LiteracyStage
    transcription_mode: TranscriptionMode
    course_available: bool


def normalize_literacy_stage(value: object, *, default: LiteracyStage) -> LiteracyStage:
    stage = str(value or "").strip().lower()
    return stage if stage in LITERACY_STAGES else default  # type: ignore[return-value]


def writing_system_profile(
    native_language: str,
    learning_language: str,
    proficiency: str | None,
    literacy_stage: object = "",
) -> WritingSystemProfile:
    native = _base(native_language)
    learning = _base(learning_language)

    if learning in _UNSUPPORTED:
        return WritingSystemProfile(
            "unsupported", "", "", "not_started", "standard", False
        )
    if learning in _MULTI_SCRIPT:
        return WritingSystemProfile(
            "standard", "", "", "mastered", "standard", False
        )

    target_script, target_name = _SCRIPT_BY_LANGUAGE.get(
        learning, ("latn", "Latin alphabet")
    )
    native_script = _SCRIPT_BY_LANGUAGE.get(native, ("latn", "Latin alphabet"))[0]

    if target_script != native_script:
        default: LiteracyStage = "not_started"
        stage = normalize_literacy_stage(literacy_stage, default=default)
        mode: TranscriptionMode = (
            "on_demand" if stage == "mastered" else "always"
        )
        return WritingSystemProfile(
            "new_alphabet", target_script, target_name, stage, mode, True
        )

    if target_script == "latn" and learning in _LATIN_EXTENDED and learning != native:
        stage = normalize_literacy_stage(literacy_stage, default="learning")
        mode = "on_demand" if stage == "mastered" else (
            "always" if _early_level(proficiency) else "on_demand"
        )
        return WritingSystemProfile(
            "latin_extended", target_script, target_name, stage, mode, True
        )

    if target_script != "latn" and learning != native:
        stage = normalize_literacy_stage(literacy_stage, default="learning")
        mode = "on_demand" if stage == "mastered" else (
            "always" if _early_level(proficiency) else "on_demand"
        )
        return WritingSystemProfile(
            "script_variant", target_script, target_name, stage, mode, True
        )

    return WritingSystemProfile(
        "standard", target_script, target_name, "mastered", "standard", False
    )


def _base(code: str) -> str:
    return code.strip().lower().replace("_", "-").split("-", 1)[0]


def _early_level(level: str | None) -> bool:
    normalized = (level or "").lower()
    return normalized.startswith("a1") or normalized.startswith("a2")
