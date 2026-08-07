"""textstats.py — local, offline "comprehensible input" estimate.

Uses word-frequency (via the `wordfreq` package) as a proxy for CEFR
difficulty: common words are easier, rare words are harder. This gives two
things instantly, with no LLM call:

  1. A CEFR band per word (`band_for_word`), used to estimate the whole
     page's difficulty via the "lexical coverage" method from reading
     research: the page's band is the lowest band whose cumulative,
     occurrence-weighted vocabulary coverage crosses 95%.
  2. A "% known" estimate. The user's knowledge base (kb) only contains
     words they've explicitly looked up — most everyday words they already
     know were never added to it. So we treat every word at or below the
     user's own CEFR level as known by default (a frequency-gated prior),
     and let explicit kb entries (`known=True`/`False`) override that
     per-word guess where we actually have data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re

from wordfreq import available_languages, tokenize, zipf_frequency

from cefr import BANDS, band_index

_AVAILABLE_LANGS = set(available_languages().keys())

# zipf_frequency is roughly 0..8 (higher = more common). Thresholds are a
# heuristic mapping from "how common" to "how hard", not an official CEFR
# wordlist — good enough for an instant estimate, refined by the LLM path
# when confidence is low.
_ZIPF_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (6.0, "A1"),
    (5.0, "A2"),
    (4.0, "B1"),
    (3.0, "B2"),
    (2.0, "C1"),
)

_MIN_CONTENT_TOKENS = 50
_COVERAGE_TARGET = 0.95


def lang_supported(lang: str) -> bool:
    return lang in _AVAILABLE_LANGS


def band_for_word(word: str, lang: str) -> str:
    zipf = zipf_frequency(word, lang)
    for threshold, band in _ZIPF_THRESHOLDS:
        if zipf >= threshold:
            return band
    return "C2"


@dataclass
class EstimateResult:
    known_pct: float
    cefr: str
    sample_size: int
    confidence: str  # "low" | "high"
    coverage_by_band: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StructureResult:
    cefr: str
    average_sentence_words: float
    long_sentence_ratio: float


def estimate_structure(text: str, lang: str) -> StructureResult:
    """Estimate syntactic load without sending page text to a model."""
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]
    lengths = [
        len([token for token in tokenize(sentence, lang) if any(char.isalpha() for char in token)])
        for sentence in sentences
    ]
    lengths = [length for length in lengths if length]
    if not lengths:
        return StructureResult("A1", 0.0, 0.0)
    average = sum(lengths) / len(lengths)
    long_ratio = sum(length >= 24 for length in lengths) / len(lengths)
    if average >= 28 or long_ratio >= 0.5:
        band = "C1"
    elif average >= 22 or long_ratio >= 0.3:
        band = "B2"
    elif average >= 16:
        band = "B1"
    elif average >= 10:
        band = "A2"
    else:
        band = "A1"
    return StructureResult(band, round(average, 2), round(long_ratio, 4))


def estimate(
    text: str,
    lang: str,
    known_overrides: dict[str, bool],
    baseline_band: str,
) -> EstimateResult:
    tokens = [t for t in tokenize((text or "").lower(), lang) if any(c.isalpha() for c in t)]

    if not tokens:
        return EstimateResult(known_pct=0.0, cefr="A1", sample_size=0, confidence="low")

    counts: dict[str, int] = {}
    for tok in tokens:
        counts[tok] = counts.get(tok, 0) + 1

    baseline_idx = band_index(baseline_band)
    total = len(tokens)
    known_occurrences = 0
    band_occurrences = {b: 0 for b in BANDS}

    for tok, n in counts.items():
        band = band_for_word(tok, lang)
        band_occurrences[band] += n

        if tok in known_overrides:
            known = known_overrides[tok]
        else:
            known = band_index(band) <= baseline_idx
        if known:
            known_occurrences += n

    cumulative = 0
    cefr = BANDS[-1]
    coverage_by_band: dict[str, float] = {}
    for band in BANDS:
        cumulative += band_occurrences[band]
        coverage = cumulative / total
        coverage_by_band[band] = coverage
        if coverage >= _COVERAGE_TARGET and cefr == BANDS[-1]:
            cefr = band

    unique_tokens = len(counts)
    confidence = "high" if unique_tokens >= _MIN_CONTENT_TOKENS and lang_supported(lang) else "low"

    return EstimateResult(
        known_pct=known_occurrences / total,
        cefr=cefr,
        sample_size=unique_tokens,
        confidence=confidence,
        coverage_by_band=coverage_by_band,
    )
