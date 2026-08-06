"""
api/subtitle_study.py — turn a subtitle track into a controlled study session.

  POST /api/subtitle-study/session                  — start or resume a session
  POST /api/subtitle-study/session/{id}/progress    — flush watched/replay events
  POST /api/subtitle-study/session/{id}/display     — change what is shown
  POST /api/subtitle-study/session/{id}/close       — close and summarize
  GET  /api/subtitle-study/session/{id}/summary     — summary without closing
  POST /api/subtitle-study/fragment                 — plan a precise replay window
  POST /api/subtitle-study/comprehension/question   — ask about a real fragment
  POST /api/subtitle-study/comprehension/check      — grade that answer
  POST /api/subtitle-study/word/senses              — meanings this form may carry
  POST /api/subtitle-study/word                     — save one sense with a timecode
  POST /api/subtitle-study/cloze                    — blank a word out of the line

Line identities are always derived server side from `(media_key, start_ms,
text)` so one dialogue line keeps the same id across reloads, sessions, saved
words and generated exercises. Clients send cues, never ids.
"""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import CurrentUser
from cefr import level_to_cefr
from entitlements import require_feature
from learning_core_v2.acquisition import (
    LexicalItem,
    SuggestVocabulary,
    VocabularyProposal,
    lexical_item_id,
)
from learning_core_v2.dictionary import DictionaryLookupRequest
from learning_core_v2.subtitle_study import (
    CHECK_KINDS,
    BuildLineCloze,
    BuildSubtitleTimeline,
    CheckKind,
    ComprehensionCheck,
    ComprehensionPolicy,
    CueDraft,
    MediaAnchor,
    PlanFragment,
    SubtitleDisplay,
    SubtitleStudySession,
    TrackSubtitleSession,
    context_for,
    summarize,
)
from learning_core_v2_adapters.openai_responses import LanguageProviderError
from learning_core_v2_adapters.runtime import (
    build_dictionary_enrichment,
    build_subtitle_study_services,
)
from storage import get_storage

log = logging.getLogger(__name__)

router = APIRouter()

MAX_WINDOW_LINES = 40
MAX_PROGRESS_EVENTS = 25
CONTEXT_BEFORE = 3
CONTEXT_AFTER = 3
_CHECK_TTL_SECONDS = 30 * 60
_MAX_PENDING_CHECKS = 500

# Pending checks live in the process, like Reading Coach questions: a check is
# only useful for as long as the learner is still sitting in front of the
# fragment it came from, and a lost one costs a single regenerated question.
_pending_checks: dict[str, tuple[str, ComprehensionCheck, str, float]] = {}

_tracker = TrackSubtitleSession()
_fragments = PlanFragment()
_cloze = BuildLineCloze()


# ---------------------------------------------------------------------------
# Wire models
# ---------------------------------------------------------------------------


class SubtitleCue(BaseModel):
    start_ms: int = Field(..., ge=0, le=100_000_000)
    end_ms: int = Field(..., ge=0, le=100_000_000)
    text: str = Field(..., min_length=1, max_length=600)
    translation: str = Field("", max_length=600)
    speaker: str = Field("", max_length=80)


class MediaRef(BaseModel):
    media_key: str = Field(..., min_length=1, max_length=200)
    media_url: str = Field("", max_length=2000)
    media_title: str = Field("", max_length=300)


class DisplayModel(BaseModel):
    show_original: bool = True
    show_translation: bool = True
    reveal_on_tap: bool = False
    auto_pause: bool = False


class AnchorModel(BaseModel):
    media_key: str
    media_url: str
    start_ms: int
    end_ms: int
    line_text: str
    line_translation: str
    language: str
    speaker: str


class LineStatModel(BaseModel):
    line_id: str
    start_ms: int
    replays: int
    slowed: int
    errors: int
    saves: int
    difficulty: float


class SessionModel(BaseModel):
    session_id: str
    media_key: str
    media_title: str
    display: DisplayModel
    check_interval: int
    cursor_line_id: str
    cursor_ms: int
    lines_watched: int
    lines_since_check: int
    checks_asked: int
    checks_passed: int
    saved_items: int
    check_due: bool
    resumed: bool = False


class SummaryModel(BaseModel):
    session_id: str
    media_key: str
    media_title: str
    lines_watched: int
    checks_asked: int
    checks_passed: int
    saved_items: int
    accuracy: float
    hardest: list[LineStatModel]


class StartSessionRequest(MediaRef):
    display: DisplayModel | None = None
    check_interval: int = Field(5, ge=1, le=50)


class ProgressEvent(BaseModel):
    kind: str = Field(..., pattern="^(watched|replayed)$")
    cue: SubtitleCue
    slowed: bool = False


class ProgressRequest(BaseModel):
    media_key: str = Field(..., min_length=1, max_length=200)
    events: list[ProgressEvent] = Field(..., min_length=1, max_length=MAX_PROGRESS_EVENTS)


class DisplayRequest(BaseModel):
    display: DisplayModel


class FragmentRequest(MediaRef):
    lines: list[SubtitleCue] = Field(..., min_length=1, max_length=MAX_WINDOW_LINES)
    cue: SubtitleCue
    playback_rate: float = Field(1.0, ge=0.5, le=1.5)
    repeats: int = Field(1, ge=0, le=20)
    media_duration_ms: int = Field(0, ge=0, le=100_000_000)
    after_error: bool = False
    session_id: str = Field("", max_length=64)


class FragmentResponse(BaseModel):
    line_id: str
    start_ms: int
    end_ms: int
    playback_rate: float
    repeats: int
    looping: bool


class QuestionRequest(MediaRef):
    lines: list[SubtitleCue] = Field(..., min_length=1, max_length=MAX_WINDOW_LINES)
    cue: SubtitleCue
    expression: str = Field("", max_length=200)
    session_id: str = Field("", max_length=64)
    kind: str = Field("", max_length=32)


class QuestionResponse(BaseModel):
    check_id: str
    kind: str
    line_id: str
    question: str
    options: list[str]
    anchor: AnchorModel


class CheckAnswerRequest(BaseModel):
    check_id: str = Field(..., min_length=16, max_length=128)
    answer: str = Field("", max_length=2000)
    session_id: str = Field("", max_length=64)


class CheckAnswerResponse(BaseModel):
    outcome: str
    passed: bool
    feedback: str
    expected_answer: str
    display: DisplayModel | None = None


class SensesRequest(MediaRef):
    term: str = Field(..., min_length=1, max_length=200)
    cue: SubtitleCue


class SenseModel(BaseModel):
    item_id: str
    term: str
    translation: str
    transcription: str
    status: str
    encounter_count: int
    latest_context: str


class SensesResponse(BaseModel):
    term: str
    language: str
    known_senses: list[SenseModel]
    suggestion: SenseModel | None = None
    needs_disambiguation: bool


class SaveWordRequest(MediaRef):
    term: str = Field(..., min_length=1, max_length=200)
    translation: str = Field(..., min_length=1, max_length=500)
    transcription: str = Field("", max_length=200)
    cue: SubtitleCue
    audio_url: str = Field("", max_length=2000)
    session_id: str = Field("", max_length=64)


class SaveWordResponse(BaseModel):
    item_id: str
    term: str
    translation: str
    status: str
    encounter_count: int
    anchor: AnchorModel


class ClozeRequest(MediaRef):
    cue: SubtitleCue
    surface: str = Field(..., min_length=1, max_length=200)
    item_id: str = Field("", max_length=100)


class ClozeResponse(BaseModel):
    line_id: str
    prompt: str
    answer: str
    first_letter: str
    letter_count: int
    blank_count: int
    translation: str
    anchor: AnchorModel


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


@router.post(
    "/api/subtitle-study/session",
    response_model=SessionModel,
    dependencies=[Depends(require_feature("dual_subtitles"))],
)
async def start_session(req: StartSessionRequest, username: CurrentUser) -> SessionModel:
    """Resume the open session for this video, or open a fresh one."""
    storage = get_storage(username)
    now = time.time()
    existing = storage.subtitle_sessions.open_for_media(req.media_key)
    if existing is not None:
        session = existing
        if req.display is not None:
            session = _tracker.displayed(session, _display(req.display), now=now)
        storage.subtitle_sessions.save(session)
        storage.save()
        return _session_model(session, ComprehensionPolicy(session.check_interval), resumed=True)

    session = SubtitleStudySession(
        session_id=str(uuid.uuid4()),
        media_key=req.media_key.strip(),
        media_url=req.media_url.strip(),
        media_title=" ".join(req.media_title.split()),
        learning_language=storage.settings.target_lang or "en",
        native_language=storage.settings.native_lang or "en",
        display=_display(req.display) if req.display else SubtitleDisplay(),
        check_interval=req.check_interval,
        started_at=now,
        updated_at=now,
    )
    storage.subtitle_sessions.save(session)
    storage.save()
    return _session_model(session, ComprehensionPolicy(session.check_interval))


@router.post(
    "/api/subtitle-study/session/{session_id}/progress",
    response_model=SessionModel,
    dependencies=[Depends(require_feature("dual_subtitles"))],
)
async def record_progress(
    session_id: str, req: ProgressRequest, username: CurrentUser
) -> SessionModel:
    """Fold a batch of watched/replayed events into the session.

    Clients flush in batches rather than per line: a session writes the whole
    user document, and a video is hundreds of lines long.
    """
    storage = get_storage(username)
    session = _require_session(storage, session_id)
    now = time.time()
    lines = BuildSubtitleTimeline().execute(
        req.media_key, [_cue_draft(event.cue) for event in req.events]
    )
    by_id = {line.line_id: line for line in lines}
    for event in req.events:
        line_id = _line_id(req.media_key, event.cue)
        line = by_id.get(line_id)
        if line is None:
            continue
        if event.kind == "watched":
            session = _tracker.watched(session, line, now=now)
        else:
            session = _tracker.replayed(
                session, line_id, start_ms=line.start_ms, slowed=event.slowed, now=now
            )
    storage.subtitle_sessions.save(session)
    storage.save()
    return _session_model(session, ComprehensionPolicy(session.check_interval))


@router.post(
    "/api/subtitle-study/session/{session_id}/display",
    response_model=SessionModel,
    dependencies=[Depends(require_feature("dual_subtitles"))],
)
async def set_display(
    session_id: str, req: DisplayRequest, username: CurrentUser
) -> SessionModel:
    storage = get_storage(username)
    session = _tracker.displayed(
        _require_session(storage, session_id), _display(req.display), now=time.time()
    )
    storage.subtitle_sessions.save(session)
    storage.save()
    return _session_model(session, ComprehensionPolicy(session.check_interval))


@router.get(
    "/api/subtitle-study/session/{session_id}/summary",
    response_model=SummaryModel,
    dependencies=[Depends(require_feature("dual_subtitles"))],
)
async def session_summary(session_id: str, username: CurrentUser) -> SummaryModel:
    storage = get_storage(username)
    return _summary_model(summarize(_require_session(storage, session_id)))


@router.post(
    "/api/subtitle-study/session/{session_id}/close",
    response_model=SummaryModel,
    dependencies=[Depends(require_feature("dual_subtitles"))],
)
async def close_session(session_id: str, username: CurrentUser) -> SummaryModel:
    storage = get_storage(username)
    session = _tracker.closed(_require_session(storage, session_id), now=time.time())
    storage.subtitle_sessions.save(session)
    storage.save()
    return _summary_model(summarize(session))


# ---------------------------------------------------------------------------
# Fragment replay
# ---------------------------------------------------------------------------


@router.post(
    "/api/subtitle-study/fragment",
    response_model=FragmentResponse,
    dependencies=[Depends(require_feature("dual_subtitles"))],
)
async def plan_fragment(req: FragmentRequest, username: CurrentUser) -> FragmentResponse:
    """Return the exact replay window for one line, and log the repeat."""
    context = _context(req.media_key, req.lines, req.cue)
    try:
        loop = _fragments.execute(
            context,
            playback_rate=req.playback_rate,
            repeats=req.repeats,
            media_duration_ms=req.media_duration_ms,
            include_previous_line=req.after_error,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if req.session_id:
        storage = get_storage(username)
        session = storage.subtitle_sessions.find(req.session_id)
        if session is not None:
            storage.subtitle_sessions.save(
                _tracker.replayed(
                    session,
                    loop.line_id,
                    start_ms=context.line.start_ms,
                    slowed=req.playback_rate < 1.0,
                    now=time.time(),
                )
            )
            storage.save()
    return FragmentResponse(
        line_id=loop.line_id,
        start_ms=loop.start_ms,
        end_ms=loop.end_ms,
        playback_rate=loop.playback_rate,
        repeats=loop.repeats,
        looping=loop.looping,
    )


# ---------------------------------------------------------------------------
# Comprehension checks
# ---------------------------------------------------------------------------


@router.post(
    "/api/subtitle-study/comprehension/question",
    response_model=QuestionResponse,
    dependencies=[Depends(require_feature("dual_subtitles"))],
)
async def create_check(req: QuestionRequest, username: CurrentUser) -> QuestionResponse:
    storage = get_storage(username)
    context = _context(req.media_key, req.lines, req.cue)
    session = storage.subtitle_sessions.find(req.session_id) if req.session_id else None
    policy = ComprehensionPolicy(session.check_interval if session else 5)
    try:
        kind = (
            _check_kind(req.kind)
            if req.kind
            else policy.select(
                context,
                checks_done=session.checks_asked if session else 0,
                expression=req.expression,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    builder, _ = build_subtitle_study_services()
    anchor = context.line.anchor(
        req.media_key, req.media_url, storage.settings.target_lang or "en"
    )
    try:
        check = await builder.execute(
            context,
            kind,
            anchor=anchor,
            learner_cefr=level_to_cefr(storage.settings.english_level),
            learning_language=storage.settings.target_lang or "en",
            native_language=storage.settings.native_lang or "en",
            expression=req.expression,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LanguageProviderError as exc:
        raise HTTPException(
            status_code=502, detail="Comprehension check unavailable."
        ) from exc

    _remember_check(username, check, context.transcript())
    return QuestionResponse(
        check_id=check.check_id,
        kind=check.kind,
        line_id=check.line_id,
        question=check.question,
        options=list(check.options),
        anchor=_anchor_model(check.anchor),
    )


@router.post(
    "/api/subtitle-study/comprehension/check",
    response_model=CheckAnswerResponse,
    dependencies=[Depends(require_feature("dual_subtitles"))],
)
async def check_answer(req: CheckAnswerRequest, username: CurrentUser) -> CheckAnswerResponse:
    stored = _pending_checks.get(req.check_id)
    if not stored or stored[0] != username or stored[3] <= time.monotonic():
        _pending_checks.pop(req.check_id, None)
        raise HTTPException(status_code=404, detail="Comprehension check expired.")
    _pending_checks.pop(req.check_id, None)
    _, check, transcript, _ = stored

    storage = get_storage(username)
    _, checker = build_subtitle_study_services()
    try:
        result = await checker.execute(
            check,
            req.answer,
            transcript=transcript,
            learner_cefr=level_to_cefr(storage.settings.english_level),
            learning_language=storage.settings.target_lang or "en",
            native_language=storage.settings.native_lang or "en",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LanguageProviderError as exc:
        raise HTTPException(status_code=502, detail="Answer check unavailable.") from exc

    display: DisplayModel | None = None
    if req.session_id:
        session = storage.subtitle_sessions.find(req.session_id)
        if session is not None:
            # The ladder moves here: a check is the only evidence this slice has
            # that the learner is or is not following without the scaffolding.
            session = _tracker.checked(
                session,
                check.line_id,
                result,
                start_ms=check.anchor.start_ms,
                now=time.time(),
            )
            storage.subtitle_sessions.save(session)
            storage.save()
            display = _display_model(session.display)
    return CheckAnswerResponse(
        outcome=result.outcome,
        passed=result.passed,
        feedback=result.feedback,
        expected_answer=result.expected_answer,
        display=display,
    )


# ---------------------------------------------------------------------------
# Saving a word with its timecode
# ---------------------------------------------------------------------------


@router.post(
    "/api/subtitle-study/word/senses",
    response_model=SensesResponse,
    dependencies=[Depends(require_feature("dual_subtitles"))],
)
async def word_senses(req: SensesRequest, username: CurrentUser) -> SensesResponse:
    """Meanings this spelling already carries, plus one grounded suggestion.

    Two senses of the same form are two cards. The client asks here first so a
    learner saving "figure" from a new scene is offered the choice instead of
    silently extending the card they made for another meaning.
    """
    storage = get_storage(username)
    language = (storage.settings.target_lang or "en").lower().replace("_", "-")
    term = " ".join(req.term.split())
    known = [
        item
        for item in storage.lexicon.all()
        if item.language == language
        and item.term.strip().casefold() == term.casefold()
        and item.status != "ignored"
    ]

    suggestion: SenseModel | None = None
    try:
        details = await build_dictionary_enrichment().execute(
            DictionaryLookupRequest(
                term=term,
                learning_language=language,
                native_language=storage.settings.native_lang or "en",
                proficiency=storage.settings.english_level or "intermediate",
                context=" ".join(req.cue.text.split()),
            )
        )
        suggestion = SenseModel(
            item_id="",
            term=details.headword or term,
            translation=details.translation,
            transcription=details.transcription,
            status="suggested",
            encounter_count=0,
            latest_context=" ".join(req.cue.text.split()),
        )
    except (LanguageProviderError, ValueError) as exc:
        log.info("[subtitle-study] dictionary suggestion unavailable for %r: %s", term, exc)

    duplicate = suggestion is not None and any(
        item.translation.casefold() == suggestion.translation.casefold() for item in known
    )
    return SensesResponse(
        term=term,
        language=language,
        known_senses=[_sense_model(item) for item in known],
        suggestion=None if duplicate else suggestion,
        needs_disambiguation=bool(known) and not duplicate,
    )


@router.post(
    "/api/subtitle-study/word",
    response_model=SaveWordResponse,
    dependencies=[Depends(require_feature("dual_subtitles"))],
)
async def save_word(req: SaveWordRequest, username: CurrentUser) -> SaveWordResponse:
    """Save one chosen sense, anchored to the second it was spoken."""
    storage = get_storage(username)
    language = (storage.settings.target_lang or "en").lower().replace("_", "-")
    line = _timeline(req.media_key, [req.cue])[0]
    anchor = MediaAnchor(
        media_key=req.media_key.strip(),
        media_url=req.media_url.strip(),
        start_ms=line.start_ms,
        end_ms=line.end_ms,
        line_text=line.text,
        line_translation=line.translation,
        language=language,
        speaker=line.speaker,
        audio_url=req.audio_url.strip(),
    )
    try:
        storage.lexicon.replace_all(
            SuggestVocabulary().execute(
                storage.lexicon.all(),
                VocabularyProposal(
                    term=req.term,
                    language=language,
                    translation=req.translation,
                    transcription=req.transcription,
                    context=line.text,
                    source_url=req.media_url,
                    media=anchor,
                ),
                observed_at=time.time(),
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    saved = storage.lexicon.find(
        lexical_item_id(req.term, language, req.translation)
    )
    if saved is None:  # pragma: no cover - SuggestVocabulary always yields the sense
        raise HTTPException(status_code=500, detail="Vocabulary item was not stored.")

    if req.session_id:
        session = storage.subtitle_sessions.find(req.session_id)
        if session is not None:
            storage.subtitle_sessions.save(
                _tracker.saved(
                    session,
                    line.line_id,
                    saved.item_id,
                    start_ms=line.start_ms,
                    now=time.time(),
                )
            )
    storage.save()
    stored_media = saved.latest_media or anchor
    return SaveWordResponse(
        item_id=saved.item_id,
        term=saved.term,
        translation=saved.translation,
        status=saved.status,
        encounter_count=len(saved.encounters),
        anchor=_anchor_model(stored_media),
    )


# ---------------------------------------------------------------------------
# Cloze from the real line
# ---------------------------------------------------------------------------


@router.post(
    "/api/subtitle-study/cloze",
    response_model=ClozeResponse,
    dependencies=[Depends(require_feature("dual_subtitles"))],
)
async def build_cloze(req: ClozeRequest, username: CurrentUser) -> ClozeResponse:
    storage = get_storage(username)
    line = _timeline(req.media_key, [req.cue])[0]
    anchor = line.anchor(
        req.media_key, req.media_url, storage.settings.target_lang or "en"
    )
    try:
        exercise = _cloze.execute(line, req.surface, anchor=anchor)
    except ValueError as exc:
        # A refusal is a real answer here: a blank that leaves no context, or
        # covers half the line, is a puzzle rather than an exercise.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ClozeResponse(
        line_id=exercise.line_id,
        prompt=exercise.prompt,
        answer=exercise.answer,
        first_letter=exercise.first_letter,
        letter_count=exercise.letter_count,
        blank_count=exercise.blank_count,
        translation=exercise.translation,
        anchor=_anchor_model(exercise.anchor),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _timeline(media_key: str, cues: list[SubtitleCue]):
    try:
        lines = BuildSubtitleTimeline().execute(media_key, [_cue_draft(cue) for cue in cues])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not lines:
        raise HTTPException(status_code=422, detail="No usable subtitle lines were sent.")
    return lines


def _context(media_key: str, window: list[SubtitleCue], cue: SubtitleCue):
    """Build the learning unit from the window the client is looking at."""
    lines = _timeline(media_key, [*window, cue])
    try:
        return context_for(
            lines,
            _line_id(media_key, cue),
            before=CONTEXT_BEFORE,
            after=CONTEXT_AFTER,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _cue_draft(cue: SubtitleCue) -> CueDraft:
    return CueDraft(
        start_ms=cue.start_ms,
        end_ms=cue.end_ms,
        text=cue.text,
        translation=cue.translation,
        speaker=cue.speaker,
    )


def _line_id(media_key: str, cue: SubtitleCue) -> str:
    return _timeline(media_key, [cue])[0].line_id


def _require_session(storage, session_id: str) -> SubtitleStudySession:
    session = storage.subtitle_sessions.find(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Subtitle session not found.")
    return session


def _check_kind(value: str) -> CheckKind:
    if value not in CHECK_KINDS:
        raise ValueError("unknown comprehension check kind")
    return value  # type: ignore[return-value]


def _display(model: DisplayModel) -> SubtitleDisplay:
    return SubtitleDisplay(
        show_original=model.show_original,
        show_translation=model.show_translation,
        reveal_on_tap=model.reveal_on_tap,
        auto_pause=model.auto_pause,
    )


def _display_model(display: SubtitleDisplay) -> DisplayModel:
    return DisplayModel(
        show_original=display.show_original,
        show_translation=display.show_translation,
        reveal_on_tap=display.reveal_on_tap,
        auto_pause=display.auto_pause,
    )


def _session_model(
    session: SubtitleStudySession, policy: ComprehensionPolicy, *, resumed: bool = False
) -> SessionModel:
    return SessionModel(
        session_id=session.session_id,
        media_key=session.media_key,
        media_title=session.media_title,
        display=_display_model(session.display),
        check_interval=session.check_interval,
        cursor_line_id=session.cursor_line_id,
        cursor_ms=session.cursor_ms,
        lines_watched=session.lines_watched,
        lines_since_check=session.lines_since_check,
        checks_asked=session.checks_asked,
        checks_passed=session.checks_passed,
        saved_items=len(session.saved_item_ids),
        check_due=policy.due(session.lines_since_check),
        resumed=resumed,
    )


def _summary_model(summary) -> SummaryModel:
    return SummaryModel(
        session_id=summary.session_id,
        media_key=summary.media_key,
        media_title=summary.media_title,
        lines_watched=summary.lines_watched,
        checks_asked=summary.checks_asked,
        checks_passed=summary.checks_passed,
        saved_items=summary.saved_items,
        accuracy=round(summary.accuracy, 4),
        hardest=[
            LineStatModel(
                line_id=stat.line_id,
                start_ms=stat.start_ms,
                replays=stat.replays,
                slowed=stat.slowed,
                errors=stat.errors,
                saves=stat.saves,
                difficulty=round(stat.difficulty, 4),
            )
            for stat in summary.hardest
        ],
    )


def _anchor_model(anchor: MediaAnchor) -> AnchorModel:
    return AnchorModel(
        media_key=anchor.media_key,
        media_url=anchor.media_url,
        start_ms=anchor.start_ms,
        end_ms=anchor.end_ms,
        line_text=anchor.line_text,
        line_translation=anchor.line_translation,
        language=anchor.language,
        speaker=anchor.speaker,
    )


def _sense_model(item: LexicalItem) -> SenseModel:
    return SenseModel(
        item_id=item.item_id,
        term=item.term,
        translation=item.translation,
        transcription=item.transcription,
        status=item.status,
        encounter_count=len(item.encounters),
        latest_context=item.latest_context,
    )


def _remember_check(username: str, check: ComprehensionCheck, transcript: str) -> None:
    """Keep the expected answer server side so the client cannot grade itself."""
    now = time.monotonic()
    for key, value in list(_pending_checks.items()):
        if value[3] <= now:
            _pending_checks.pop(key, None)
    if len(_pending_checks) >= _MAX_PENDING_CHECKS:
        oldest = min(_pending_checks, key=lambda key: _pending_checks[key][3])
        _pending_checks.pop(oldest, None)
    _pending_checks[check.check_id] = (
        username,
        check,
        transcript,
        now + _CHECK_TTL_SECONDS,
    )
