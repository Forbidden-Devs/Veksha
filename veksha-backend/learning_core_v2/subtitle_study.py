"""Domain rules for a subtitle study session.

Parallel subtitles are a reading aid; a *study session* is something else. This
module turns a timed caption track into learning units and owns the rules that
make one dialogue line practicable:

    line identity → what is shown → how it is replayed → what is asked about it

A line is addressed by a stable temporal id, so the same cue keeps its identity
across reloads, sessions and saved words. Everything that refers to a moment in
a video — a saved expression, a comprehension check, a cloze exercise — carries
a :class:`MediaAnchor`, which is what lets the learner return to the exact
second the phrase was actually spoken.

Scaffolding is removed gradually rather than toggled: the ladder starts with
both texts, drops the translation, then hides everything until the learner
answers. Errors and heavy replaying push it back down.

Two of the six comprehension checks — "which word was spoken" and "which line
continues the conversation" — are built here from the track itself, not by a
model: their options *are* the neighbouring dialogue. The remaining four are
authored by a provider, still grounded in the real cue and its neighbours.

Nothing in this module performs I/O, and no format is drawn at random: every
choice is derived from the material and from a counter the caller owns.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass, replace
from typing import Literal, Protocol, Sequence


_SUBTITLE_LINE_NAMESPACE = uuid.UUID("6f0b5a3e-2a1c-5f6d-9b2a-7c1f4d8e0a35")

# Caption timings drift by a few milliseconds between fetches of the same
# track (ASR tracks are re-decoded server side). Bucketing the start time makes
# the identifier survive that jitter while still separating adjacent cues.
_TIME_BUCKET_MS = 100

_WORD_PATTERN = re.compile(r"[^\W\d_](?:[\w'’‑-]*[^\W_])?", re.UNICODE)


# ---------------------------------------------------------------------------
# Learning units
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MediaAnchor:
    """The exact moment a line was spoken, and how to get back to it."""

    media_key: str
    media_url: str = ""
    start_ms: int = 0
    end_ms: int = 0
    line_text: str = ""
    line_translation: str = ""
    language: str = ""
    speaker: str = ""
    audio_url: str = ""

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)


@dataclass(frozen=True, slots=True)
class SubtitleLine:
    """One dialogue line with a stable identity inside its track."""

    line_id: str
    index: int
    start_ms: int
    end_ms: int
    text: str
    translation: str = ""
    speaker: str = ""

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)

    @property
    def words(self) -> tuple[str, ...]:
        return tuple(match.group(0) for match in _WORD_PATTERN.finditer(self.text))

    def anchor(
        self, media_key: str, media_url: str = "", language: str = "", audio_url: str = ""
    ) -> MediaAnchor:
        return MediaAnchor(
            media_key=media_key,
            media_url=media_url,
            start_ms=self.start_ms,
            end_ms=self.end_ms,
            line_text=self.text,
            line_translation=self.translation,
            language=language,
            speaker=self.speaker,
            audio_url=audio_url,
        )


@dataclass(frozen=True, slots=True)
class SubtitleContext:
    """A line together with the dialogue around it."""

    line: SubtitleLine
    previous: tuple[SubtitleLine, ...] = ()
    following: tuple[SubtitleLine, ...] = ()

    @property
    def neighbours(self) -> tuple[SubtitleLine, ...]:
        return (*self.previous, *self.following)

    def transcript(self) -> str:
        return "\n".join(
            _speaker_prefix(line) + line.text
            for line in (*self.previous, self.line, *self.following)
        )


def subtitle_line_id(media_key: str, start_ms: int, text: str) -> str:
    """Return the stable identifier of one cue inside one caption track.

    Re-fetching the same track yields the same identifiers, so a word saved
    yesterday still points at the line it came from.
    """
    key = _normalize_key(media_key)
    if not key:
        raise ValueError("subtitle line id requires a media key")
    body = _normalize_text(text)
    if not body:
        raise ValueError("subtitle line id requires text")
    bucket = max(0, int(start_ms)) // _TIME_BUCKET_MS
    canonical = "\x1f".join(
        unicodedata.normalize("NFKC", part) for part in (key, str(bucket), body)
    )
    return str(uuid.uuid5(_SUBTITLE_LINE_NAMESPACE, canonical))


@dataclass(frozen=True, slots=True)
class CueDraft:
    """An untrusted cue as delivered by a caption track."""

    start_ms: int
    end_ms: int
    text: str
    translation: str = ""
    speaker: str = ""


class BuildSubtitleTimeline:
    """Turn raw cues into ordered, identified, non-overlapping dialogue lines."""

    def __init__(self, maximum_lines: int = 4000) -> None:
        if maximum_lines < 1:
            raise ValueError("maximum lines must be positive")
        self._maximum_lines = maximum_lines

    def execute(self, media_key: str, cues: Sequence[CueDraft]) -> tuple[SubtitleLine, ...]:
        key = _normalize_key(media_key)
        if not key:
            raise ValueError("subtitle timeline requires a media key")
        ordered = sorted(
            (cue for cue in cues if _normalize_text(cue.text)),
            key=lambda cue: (max(0, int(cue.start_ms)), _normalize_text(cue.text)),
        )[: self._maximum_lines]
        lines: list[SubtitleLine] = []
        seen: set[str] = set()
        for cue in ordered:
            text = " ".join(cue.text.split())[:600]
            start = max(0, int(cue.start_ms))
            end = max(start + 1, int(cue.end_ms))
            line_id = subtitle_line_id(key, start, text)
            if line_id in seen:
                continue
            seen.add(line_id)
            lines.append(
                SubtitleLine(
                    line_id=line_id,
                    index=len(lines),
                    start_ms=start,
                    end_ms=end,
                    text=text,
                    translation=" ".join(cue.translation.split())[:600],
                    speaker=" ".join(cue.speaker.split())[:80],
                )
            )
        return tuple(lines)


def context_for(
    lines: Sequence[SubtitleLine],
    line_id: str,
    *,
    before: int = 2,
    after: int = 2,
) -> SubtitleContext:
    """The learning unit around one line: the line plus its adjacent dialogue."""
    if before < 0 or after < 0:
        raise ValueError("context window must not be negative")
    index = next(
        (position for position, line in enumerate(lines) if line.line_id == line_id),
        None,
    )
    if index is None:
        raise ValueError("subtitle line is not part of this timeline")
    return SubtitleContext(
        line=lines[index],
        previous=tuple(lines[max(0, index - before) : index]),
        following=tuple(lines[index + 1 : index + 1 + after]),
    )


# ---------------------------------------------------------------------------
# Display modes and the scaffolding ladder
# ---------------------------------------------------------------------------


DisplayMode = Literal["dual", "original", "translation", "reveal_on_tap", "hidden"]

# Ordered from most to least support. The ladder only ever moves one rung.
SCAFFOLD_LADDER: tuple[DisplayMode, ...] = (
    "dual",
    "original",
    "reveal_on_tap",
    "hidden",
)


@dataclass(frozen=True, slots=True)
class SubtitleDisplay:
    """What the player currently shows.

    The two texts are independent flags rather than one enum, because a learner
    may want the translation alone (a first pass through a hard scene) just as
    much as the original alone.
    """

    show_original: bool = True
    show_translation: bool = True
    reveal_on_tap: bool = False
    auto_pause: bool = False

    @property
    def mode(self) -> DisplayMode:
        if self.reveal_on_tap:
            return "reveal_on_tap"
        if self.show_original and self.show_translation:
            return "dual"
        if self.show_original:
            return "original"
        if self.show_translation:
            return "translation"
        return "hidden"

    @property
    def rung(self) -> int:
        """Position on the ladder; -1 for modes that are not part of it."""
        mode = self.mode
        return SCAFFOLD_LADDER.index(mode) if mode in SCAFFOLD_LADDER else -1

    def with_mode(self, mode: DisplayMode) -> "SubtitleDisplay":
        return replace(self, **_MODE_FLAGS[_display_mode(mode)])

    def with_auto_pause(self, auto_pause: bool) -> "SubtitleDisplay":
        return replace(self, auto_pause=bool(auto_pause))


_MODE_FLAGS: dict[DisplayMode, dict[str, bool]] = {
    "dual": {"show_original": True, "show_translation": True, "reveal_on_tap": False},
    "original": {"show_original": True, "show_translation": False, "reveal_on_tap": False},
    "translation": {"show_original": False, "show_translation": True, "reveal_on_tap": False},
    # Nothing is painted until the learner asks for it; the tap reveals both.
    "reveal_on_tap": {"show_original": True, "show_translation": True, "reveal_on_tap": True},
    "hidden": {"show_original": False, "show_translation": False, "reveal_on_tap": False},
}


class ScaffoldLadder:
    """Removes support only after the learner has earned it, and restores it fast.

    Promotion needs a run of clean lines — understood without a replay and
    without a failed check. A single failure drops one rung immediately, because
    a learner who has stopped following the dialogue gains nothing from staring
    at a blank subtitle bar.
    """

    PROMOTE_AFTER_CLEAN_LINES = 8
    DEMOTE_AFTER_ERRORS = 1

    def __init__(
        self,
        promote_after_clean_lines: int = PROMOTE_AFTER_CLEAN_LINES,
        demote_after_errors: int = DEMOTE_AFTER_ERRORS,
    ) -> None:
        if promote_after_clean_lines < 1 or demote_after_errors < 1:
            raise ValueError("scaffold thresholds must be positive")
        self._promote_after = promote_after_clean_lines
        self._demote_after = demote_after_errors

    def adjust(
        self, display: SubtitleDisplay, *, clean_lines: int, recent_errors: int
    ) -> SubtitleDisplay:
        rung = display.rung
        if rung < 0:
            # "translation only" is a deliberate choice, not a rung: leave it be.
            return display
        if recent_errors >= self._demote_after:
            return display.with_mode(SCAFFOLD_LADDER[max(0, rung - 1)])
        if clean_lines >= self._promote_after:
            return display.with_mode(SCAFFOLD_LADDER[min(len(SCAFFOLD_LADDER) - 1, rung + 1)])
        return display


# ---------------------------------------------------------------------------
# Fragment replay
# ---------------------------------------------------------------------------


MIN_PLAYBACK_RATE = 0.5
MAX_PLAYBACK_RATE = 1.5
MAX_PADDING_MS = 3000
MAX_LOOP_REPEATS = 20


@dataclass(frozen=True, slots=True)
class FragmentLoop:
    """A precise replay window over the media timeline."""

    line_id: str
    start_ms: int
    end_ms: int
    playback_rate: float = 1.0
    repeats: int = 1
    """1 = single replay, 0 = loop until the learner stops it."""

    @property
    def looping(self) -> bool:
        return self.repeats == 0

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)


class PlanFragment:
    """Builds the replay window for one line, with context padding.

    Padding is what makes a replay usable: a cue cut exactly on its timestamps
    clips the first syllable and swallows the intonation that carries the
    meaning. It is clamped to the media bounds and never extends past the far
    edge of an adjacent line, so a "replay this line" never turns into
    "replay the scene".
    """

    def __init__(
        self,
        lead_in_ms: int = 400,
        lead_out_ms: int = 400,
    ) -> None:
        if not 0 <= lead_in_ms <= MAX_PADDING_MS or not 0 <= lead_out_ms <= MAX_PADDING_MS:
            raise ValueError("fragment padding is out of range")
        self._lead_in_ms = lead_in_ms
        self._lead_out_ms = lead_out_ms

    def execute(
        self,
        context: SubtitleContext,
        *,
        playback_rate: float = 1.0,
        repeats: int = 1,
        media_duration_ms: int = 0,
        include_previous_line: bool = False,
    ) -> FragmentLoop:
        line = context.line
        previous = context.previous[-1] if context.previous else None
        following = context.following[0] if context.following else None

        start = line.start_ms - self._lead_in_ms
        if include_previous_line and previous is not None:
            # Returning to a problem area: begin at the line that set it up.
            start = min(start, previous.start_ms)
        elif previous is not None:
            start = max(start, previous.start_ms)
        end = line.end_ms + self._lead_out_ms
        if following is not None:
            end = min(end, following.end_ms)

        start = max(0, start)
        if media_duration_ms > 0:
            end = min(end, media_duration_ms)
        end = max(end, start + max(1, line.duration_ms // 4))

        return FragmentLoop(
            line_id=line.line_id,
            start_ms=start,
            end_ms=end,
            playback_rate=_playback_rate(playback_rate),
            repeats=_repeats(repeats),
        )


def _playback_rate(value: float) -> float:
    rate = round(float(value), 2)
    if not MIN_PLAYBACK_RATE <= rate <= MAX_PLAYBACK_RATE:
        raise ValueError("playback rate is out of range")
    return rate


def _repeats(value: int) -> int:
    repeats = int(value)
    if not 0 <= repeats <= MAX_LOOP_REPEATS:
        raise ValueError("loop repeats are out of range")
    return repeats


# ---------------------------------------------------------------------------
# Difficulty signal
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LineStat:
    """What the learner did with one line — the planner's difficulty signal."""

    line_id: str
    start_ms: int = 0
    replays: int = 0
    slowed: int = 0
    errors: int = 0
    saves: int = 0

    REPLAY_WEIGHT = 0.18
    SLOWED_WEIGHT = 0.12
    ERROR_WEIGHT = 0.35
    SAVE_WEIGHT = 0.1

    @property
    def difficulty(self) -> float:
        """0..1 — how much this fragment resisted the learner."""
        return min(
            1.0,
            self.replays * self.REPLAY_WEIGHT
            + self.slowed * self.SLOWED_WEIGHT
            + self.errors * self.ERROR_WEIGHT
            + self.saves * self.SAVE_WEIGHT,
        )


def hardest_lines(stats: Sequence[LineStat], limit: int = 5) -> tuple[LineStat, ...]:
    if limit < 1:
        raise ValueError("limit must be positive")
    ranked = sorted(
        (stat for stat in stats if stat.difficulty > 0),
        key=lambda stat: (-stat.difficulty, stat.line_id),
    )
    return tuple(ranked[:limit])


# ---------------------------------------------------------------------------
# Comprehension checks
# ---------------------------------------------------------------------------


CheckKind = Literal[
    "what_said",
    "why_said",
    "expression_meaning",
    "next_line",
    "which_word",
    "retell",
]
CheckOutcome = Literal["correct", "vague", "incorrect", "garbage"]

# Built here from the dialogue itself — the options *are* real lines and real
# spoken words, so a distractor can never be an invented phrase.
GROUNDED_CHECK_KINDS: tuple[CheckKind, ...] = ("which_word", "next_line")
# Authored by a provider, still anchored to the real cue and its neighbours.
AUTHORED_CHECK_KINDS: tuple[CheckKind, ...] = (
    "what_said",
    "why_said",
    "expression_meaning",
    "retell",
)
CHECK_KINDS: tuple[CheckKind, ...] = (*GROUNDED_CHECK_KINDS, *AUTHORED_CHECK_KINDS)

MIN_CHECK_OPTIONS = 3
MAX_CHECK_OPTIONS = 4


@dataclass(frozen=True, slots=True)
class ComprehensionCheck:
    check_id: str
    kind: CheckKind
    line_id: str
    question: str
    anchor: MediaAnchor
    options: tuple[str, ...] = ()
    expected_answer: str = ""

    @property
    def is_choice(self) -> bool:
        return bool(self.options)


@dataclass(frozen=True, slots=True)
class ComprehensionResult:
    outcome: CheckOutcome
    feedback: str = ""
    expected_answer: str = ""

    @property
    def passed(self) -> bool:
        return self.outcome in {"correct", "vague"}


@dataclass(frozen=True, slots=True)
class SubtitleQuestionRequest:
    kind: CheckKind
    line: str
    line_translation: str
    transcript: str
    speaker: str
    expression: str
    learner_cefr: str
    learning_language: str
    native_language: str


@dataclass(frozen=True, slots=True)
class SubtitleQuestionDraft:
    question: str
    expected_answer: str = ""


@dataclass(frozen=True, slots=True)
class SubtitleAnswerRequest:
    kind: CheckKind
    line: str
    transcript: str
    question: str
    answer: str
    expected_answer: str
    learner_cefr: str
    learning_language: str
    native_language: str


@dataclass(frozen=True, slots=True)
class SubtitleAnswerEvaluation:
    outcome: CheckOutcome
    feedback: str = ""


class SubtitleComprehensionProvider(Protocol):
    async def create_subtitle_question(
        self, request: SubtitleQuestionRequest
    ) -> SubtitleQuestionDraft: ...

    async def evaluate_subtitle_answer(
        self, request: SubtitleAnswerRequest
    ) -> SubtitleAnswerEvaluation: ...


class IdentifierSource(Protocol):
    def new(self) -> str: ...


class ComprehensionPolicy:
    """When to interrupt playback, and what the material can actually support."""

    def __init__(self, every_lines: int = 5) -> None:
        if not 1 <= every_lines <= 50:
            raise ValueError("comprehension interval must be between 1 and 50 lines")
        self._every_lines = every_lines

    @property
    def every_lines(self) -> int:
        return self._every_lines

    def due(self, lines_since_check: int) -> bool:
        return lines_since_check >= self._every_lines

    def feasible(self, context: SubtitleContext, *, expression: str = "") -> tuple[CheckKind, ...]:
        kinds: list[CheckKind] = []
        if _word_options(context)[0]:
            kinds.append("which_word")
        if _line_options(context)[0]:
            kinds.append("next_line")
        kinds.append("what_said")
        if context.previous or context.following:
            kinds.append("why_said")
        if expression.strip():
            kinds.append("expression_meaning")
        if len(context.line.words) >= 6 or context.neighbours:
            kinds.append("retell")
        return tuple(kinds)

    def select(
        self, context: SubtitleContext, *, checks_done: int, expression: str = ""
    ) -> CheckKind:
        """Rotate deterministically through the kinds this fragment supports."""
        kinds = self.feasible(context, expression=expression)
        if not kinds:
            raise ValueError("this fragment supports no comprehension check")
        return kinds[max(0, checks_done) % len(kinds)]


class BuildComprehensionCheck:
    """Grounded checks are assembled here; the rest are authored by a provider."""

    def __init__(
        self,
        provider: SubtitleComprehensionProvider,
        identifiers: IdentifierSource,
    ) -> None:
        self._provider = provider
        self._identifiers = identifiers

    async def execute(
        self,
        context: SubtitleContext,
        kind: CheckKind,
        *,
        anchor: MediaAnchor,
        learner_cefr: str,
        learning_language: str,
        native_language: str,
        expression: str = "",
    ) -> ComprehensionCheck:
        if kind not in CHECK_KINDS:
            raise ValueError("unknown comprehension check kind")
        if kind == "expression_meaning" and not expression.strip():
            raise ValueError("an expression check needs an expression")

        if kind == "which_word":
            options, expected = _word_options(context)
            if not options:
                raise ValueError("this line has no distinguishable spoken word")
            return self._check(kind, context, anchor, _WHICH_WORD_PROMPT, options, expected)
        if kind == "next_line":
            options, expected = _line_options(context)
            if not options:
                raise ValueError("this fragment has no continuation to choose from")
            return self._check(kind, context, anchor, _NEXT_LINE_PROMPT, options, expected)

        draft = await self._provider.create_subtitle_question(
            SubtitleQuestionRequest(
                kind=kind,
                line=context.line.text,
                line_translation=context.line.translation,
                transcript=context.transcript(),
                speaker=context.line.speaker,
                expression=" ".join(expression.split())[:200],
                learner_cefr=learner_cefr,
                learning_language=learning_language,
                native_language=native_language,
            )
        )
        question = " ".join(draft.question.split())
        if not question:
            raise ValueError("comprehension provider returned an empty question")
        return ComprehensionCheck(
            check_id=self._identifiers.new(),
            kind=kind,
            line_id=context.line.line_id,
            question=question,
            anchor=anchor,
            expected_answer=" ".join(draft.expected_answer.split())[:600],
        )

    def _check(
        self,
        kind: CheckKind,
        context: SubtitleContext,
        anchor: MediaAnchor,
        question: str,
        options: tuple[str, ...],
        expected: str,
    ) -> ComprehensionCheck:
        return ComprehensionCheck(
            check_id=self._identifiers.new(),
            kind=kind,
            line_id=context.line.line_id,
            question=question,
            anchor=anchor,
            options=options,
            expected_answer=expected,
        )


# Localization happens client side; these are stable keys, not display copy.
_WHICH_WORD_PROMPT = "subtitle_check_which_word"
_NEXT_LINE_PROMPT = "subtitle_check_next_line"


class CheckComprehensionAnswer:
    """Choice answers are graded here; open answers go to the provider."""

    def __init__(self, provider: SubtitleComprehensionProvider) -> None:
        self._provider = provider

    async def execute(
        self,
        check: ComprehensionCheck,
        answer: str,
        *,
        transcript: str,
        learner_cefr: str,
        learning_language: str,
        native_language: str,
    ) -> ComprehensionResult:
        given = " ".join(answer.split())
        if not given:
            return ComprehensionResult("garbage", expected_answer=check.expected_answer)
        if check.is_choice:
            correct = _normalize_text(given) == _normalize_text(check.expected_answer)
            return ComprehensionResult(
                "correct" if correct else "incorrect",
                expected_answer=check.expected_answer,
            )
        evaluation = await self._provider.evaluate_subtitle_answer(
            SubtitleAnswerRequest(
                kind=check.kind,
                line=check.anchor.line_text,
                transcript=transcript,
                question=check.question,
                answer=given[:2000],
                expected_answer=check.expected_answer,
                learner_cefr=learner_cefr,
                learning_language=learning_language,
                native_language=native_language,
            )
        )
        if evaluation.outcome not in {"correct", "vague", "incorrect", "garbage"}:
            raise ValueError("comprehension provider returned an invalid outcome")
        return ComprehensionResult(
            evaluation.outcome,
            " ".join(evaluation.feedback.split()),
            check.expected_answer,
        )


def _word_options(context: SubtitleContext) -> tuple[tuple[str, ...], str]:
    """"Which word was spoken?" — the answer is in the line, the rest are not."""
    spoken = [word for word in context.line.words if len(word) >= 3]
    if not spoken:
        return (), ""
    target = max(spoken, key=lambda word: (len(word), word.casefold()))
    seen = {_normalize_text(word) for word in context.line.words}
    distractors: list[str] = []
    for line in context.neighbours:
        for word in line.words:
            key = _normalize_text(word)
            if len(word) < 3 or key in seen:
                continue
            seen.add(key)
            distractors.append(word)
    distractors.sort(key=lambda word: (abs(len(word) - len(target)), word.casefold()))
    if len(distractors) < MIN_CHECK_OPTIONS - 1:
        return (), ""
    return _arrange(target, distractors[: MAX_CHECK_OPTIONS - 1], context.line.line_id), target


def _line_options(context: SubtitleContext) -> tuple[tuple[str, ...], str]:
    """"Which line continues the conversation?" — distractors are real lines."""
    if not context.following:
        return (), ""
    target = context.following[0].text
    seen = {_normalize_text(target), _normalize_text(context.line.text)}
    distractors: list[str] = []
    # Later lines and earlier lines are both plausible-looking continuations,
    # which is the point: the learner has to have followed the dialogue.
    for line in (*context.following[1:], *reversed(context.previous)):
        key = _normalize_text(line.text)
        if not key or key in seen:
            continue
        seen.add(key)
        distractors.append(line.text)
    if len(distractors) < MIN_CHECK_OPTIONS - 1:
        return (), ""
    return _arrange(target, distractors[: MAX_CHECK_OPTIONS - 1], context.line.line_id), target


def _arrange(target: str, distractors: Sequence[str], seed: str) -> tuple[str, ...]:
    """Place the answer at a position derived from the line id.

    Sorting would leak the answer alphabetically and a fixed slot would leak it
    positionally; the line id is stable, so a replayed check keeps its layout.
    """
    options = list(distractors)
    position = _seed_int(seed) % (len(options) + 1)
    options.insert(position, target)
    return tuple(options)


def _seed_int(value: str) -> int:
    try:
        return uuid.UUID(value).int
    except ValueError:
        return sum(index * ord(char) for index, char in enumerate(value))


# ---------------------------------------------------------------------------
# Cloze from a real dialogue line
# ---------------------------------------------------------------------------


BLANK = "___"
MIN_VISIBLE_WORDS = 3
MIN_TARGET_CHARACTERS = 2
MAX_BLANK_RATIO = 0.4


@dataclass(frozen=True, slots=True)
class ClozeExercise:
    """A fill-in-the-blank built from the line as it was actually spoken."""

    line_id: str
    prompt: str
    answer: str
    anchor: MediaAnchor
    translation: str = ""
    blank_count: int = 1

    @property
    def first_letter(self) -> str:
        return self.answer[:1]

    @property
    def letter_count(self) -> int:
        return len(self.answer.replace(" ", ""))


class BuildLineCloze:
    """Hides the exact target, keeps its grammatical form, refuses puzzles.

    The blank covers the surface form the learner met — ``came across``, not the
    dictionary ``come across`` — because the exercise is a memory of a moment in
    the video, and the answer they will compare against is the recording. Every
    occurrence of that form is hidden: leaving a second copy visible turns the
    task into a copying exercise.
    """

    def __init__(
        self,
        minimum_visible_words: int = MIN_VISIBLE_WORDS,
        maximum_blank_ratio: float = MAX_BLANK_RATIO,
    ) -> None:
        if minimum_visible_words < 1:
            raise ValueError("a cloze needs at least one visible word")
        if not 0 < maximum_blank_ratio <= 1:
            raise ValueError("blank ratio must be between zero and one")
        self._minimum_visible_words = minimum_visible_words
        self._maximum_blank_ratio = maximum_blank_ratio

    def execute(
        self, line: SubtitleLine, surface: str, *, anchor: MediaAnchor
    ) -> ClozeExercise:
        target = " ".join(surface.split())
        if len(target.replace(" ", "")) < MIN_TARGET_CHARACTERS:
            raise ValueError("cloze target is too short to be answerable")

        spans = _match_spans(line.text, target)
        if not spans:
            raise ValueError("cloze target does not occur in this line")

        target_words = len(_WORD_PATTERN.findall(target))
        total_words = len(line.words)
        hidden_words = target_words * len(spans)
        if total_words - hidden_words < self._minimum_visible_words:
            raise ValueError("hiding this target leaves too little context")
        if total_words and hidden_words / total_words > self._maximum_blank_ratio:
            raise ValueError("this target covers too much of the line")

        prompt: list[str] = []
        cursor = 0
        for start, end in spans:
            prompt.append(line.text[cursor:start])
            prompt.append(BLANK)
            cursor = end
        prompt.append(line.text[cursor:])

        return ClozeExercise(
            line_id=line.line_id,
            prompt="".join(prompt),
            # The first occurrence carries the casing the learner should produce.
            answer=line.text[spans[0][0] : spans[0][1]],
            anchor=anchor,
            translation=line.translation,
            blank_count=len(spans),
        )


def _match_spans(text: str, target: str) -> tuple[tuple[int, int], ...]:
    """Every whole-word occurrence of the target, in order."""
    pattern = re.compile(
        r"(?<!\w)" + r"\s+".join(re.escape(part) for part in target.split()) + r"(?!\w)",
        re.IGNORECASE | re.UNICODE,
    )
    return tuple((match.start(), match.end()) for match in pattern.finditer(text))


# ---------------------------------------------------------------------------
# Session state, progress and summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SubtitleStudySession:
    """Everything needed to resume a session at the line it stopped on."""

    session_id: str
    media_key: str
    media_url: str = ""
    media_title: str = ""
    learning_language: str = ""
    native_language: str = ""
    display: SubtitleDisplay = SubtitleDisplay()
    check_interval: int = 5
    cursor_line_id: str = ""
    cursor_ms: int = 0
    lines_watched: int = 0
    lines_since_check: int = 0
    clean_streak: int = 0
    checks_asked: int = 0
    checks_passed: int = 0
    saved_item_ids: tuple[str, ...] = ()
    stats: tuple[LineStat, ...] = ()
    started_at: float = 0.0
    updated_at: float = 0.0
    closed_at: float = 0.0

    @property
    def open(self) -> bool:
        return self.closed_at <= 0

    def stat(self, line_id: str) -> LineStat:
        return next(
            (stat for stat in self.stats if stat.line_id == line_id),
            LineStat(line_id=line_id),
        )


@dataclass(frozen=True, slots=True)
class SubtitleSessionSummary:
    session_id: str
    media_key: str
    media_title: str
    lines_watched: int
    checks_asked: int
    checks_passed: int
    saved_items: int
    accuracy: float
    hardest: tuple[LineStat, ...]


class TrackSubtitleSession:
    """Folds one session event into a new immutable session state.

    Progress is recorded per event rather than reconstructed at the end, so a
    session that is abandoned mid-video still resumes on the right line and
    still carries its difficulty signal into the practice planner.
    """

    def __init__(
        self,
        ladder: ScaffoldLadder | None = None,
        maximum_tracked_lines: int = 400,
    ) -> None:
        if maximum_tracked_lines < 1:
            raise ValueError("tracked line budget must be positive")
        self._ladder = ladder or ScaffoldLadder()
        self._maximum_tracked_lines = maximum_tracked_lines

    def watched(
        self, session: SubtitleStudySession, line: SubtitleLine, *, now: float
    ) -> SubtitleStudySession:
        """Advance the cursor. Re-watching the current line is not progress."""
        if session.cursor_line_id == line.line_id:
            return replace(session, cursor_ms=max(0, int(line.start_ms)), updated_at=now)
        session = self._merge(session, line.line_id, start_ms=line.start_ms)
        return replace(
            session,
            cursor_line_id=line.line_id,
            cursor_ms=max(0, int(line.start_ms)),
            lines_watched=session.lines_watched + 1,
            lines_since_check=session.lines_since_check + 1,
            clean_streak=session.clean_streak + (1 if session.stat(line.line_id).replays == 0 else 0),
            updated_at=now,
        )

    def replayed(
        self,
        session: SubtitleStudySession,
        line_id: str,
        *,
        start_ms: int = 0,
        slowed: bool = False,
        now: float,
    ) -> SubtitleStudySession:
        """A repeated fragment is the strongest difficulty signal this slice has."""
        updated = self._merge(
            session,
            line_id,
            start_ms=start_ms,
            replays=1,
            slowed=1 if slowed else 0,
        )
        return replace(updated, clean_streak=0, updated_at=now)

    def checked(
        self,
        session: SubtitleStudySession,
        line_id: str,
        result: ComprehensionResult,
        *,
        start_ms: int = 0,
        now: float,
    ) -> SubtitleStudySession:
        passed = result.passed
        updated = self._merge(
            session, line_id, start_ms=start_ms, errors=0 if passed else 1
        )
        clean_streak = updated.clean_streak if passed else 0
        display = self._ladder.adjust(
            updated.display,
            clean_lines=clean_streak,
            recent_errors=0 if passed else 1,
        )
        if display.mode != updated.display.mode or not passed:
            clean_streak = 0
        return replace(
            updated,
            display=display,
            clean_streak=clean_streak,
            lines_since_check=0,
            checks_asked=updated.checks_asked + 1,
            checks_passed=updated.checks_passed + (1 if passed else 0),
            updated_at=now,
        )

    def saved(
        self,
        session: SubtitleStudySession,
        line_id: str,
        item_id: str,
        *,
        start_ms: int = 0,
        now: float,
    ) -> SubtitleStudySession:
        updated = self._merge(session, line_id, start_ms=start_ms, saves=1)
        saved = updated.saved_item_ids
        if item_id and item_id not in saved:
            saved = (*saved, item_id)
        return replace(updated, saved_item_ids=saved, updated_at=now)

    def displayed(
        self, session: SubtitleStudySession, display: SubtitleDisplay, *, now: float
    ) -> SubtitleStudySession:
        """An explicit learner choice restarts the ladder from where they put it."""
        return replace(session, display=display, clean_streak=0, updated_at=now)

    def closed(self, session: SubtitleStudySession, *, now: float) -> SubtitleStudySession:
        return replace(session, closed_at=now, updated_at=now)

    def _merge(
        self,
        session: SubtitleStudySession,
        line_id: str,
        *,
        start_ms: int = 0,
        replays: int = 0,
        slowed: int = 0,
        errors: int = 0,
        saves: int = 0,
    ) -> SubtitleStudySession:
        if not line_id:
            raise ValueError("a session event must name a line")
        current = session.stat(line_id)
        merged = LineStat(
            line_id=line_id,
            # The timecode is what a summary can actually take the learner back
            # to, so the first event that knows it wins and later ones keep it.
            start_ms=current.start_ms or max(0, int(start_ms)),
            replays=current.replays + replays,
            slowed=current.slowed + slowed,
            errors=current.errors + errors,
            saves=current.saves + saves,
        )
        retained = [stat for stat in session.stats if stat.line_id != line_id]
        # Oldest entries fall out first; the hardest fragments of a long video
        # are the recent ones the learner is still working through.
        stats = (*retained, merged)[-self._maximum_tracked_lines :]
        return replace(session, stats=stats)


def summarize(session: SubtitleStudySession, limit: int = 5) -> SubtitleSessionSummary:
    return SubtitleSessionSummary(
        session_id=session.session_id,
        media_key=session.media_key,
        media_title=session.media_title,
        lines_watched=session.lines_watched,
        checks_asked=session.checks_asked,
        checks_passed=session.checks_passed,
        saved_items=len(session.saved_item_ids),
        accuracy=(
            session.checks_passed / session.checks_asked if session.checks_asked else 0.0
        ),
        hardest=hardest_lines(session.stats, limit),
    )


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def _display_mode(value: str) -> DisplayMode:
    if value not in _MODE_FLAGS:
        raise ValueError("unknown subtitle display mode")
    return value  # type: ignore[return-value]


def _normalize_key(value: str) -> str:
    return " ".join(value.split())[:200]


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _speaker_prefix(line: SubtitleLine) -> str:
    return f"{line.speaker}: " if line.speaker else ""
