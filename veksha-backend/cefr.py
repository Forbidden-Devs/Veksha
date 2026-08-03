"""cefr.py — shared CEFR band helpers.

Used by the rewritten immersion adapter and Reading Coach so the level-to-band
mapping and ordering live in exactly one place.
"""
from __future__ import annotations

# Ordered A1 (easiest) .. C2 (hardest).
BANDS: tuple[str, ...] = ("A1", "A2", "B1", "B2", "C1", "C2")
_BAND_INDEX: dict[str, int] = {band: i for i, band in enumerate(BANDS)}


def band_index(band: str) -> int:
    """Position of a CEFR band in BANDS (0=A1..5=C2); unknown bands sort last."""
    return _BAND_INDEX.get(band, len(BANDS) - 1)


# Map the stored level to a CEFR anchor for the i+1 filter. Slash grades resolve
# to their upper band; legacy values are kept so existing users keep working.
LEVEL_TO_CEFR: dict[str, str] = {
    "a1": "A1", "a1_a2": "A2", "a2": "A2", "a2_b1": "B1", "b1": "B1",
    "b1_b2": "B2", "b2": "B2", "b2_c1": "C1", "c1": "C1", "c1_c2": "C2", "c2": "C2",
    # legacy
    "beginner": "A1", "elementary": "A2", "intermediate": "B1",
    "upper_intermediate": "B2", "advanced": "C1",
}


def level_to_cefr(level: str | None) -> str:
    return LEVEL_TO_CEFR.get(level or "intermediate", "B1")
