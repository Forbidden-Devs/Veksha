from dataclasses import dataclass, field

import pytest

from api import subtitle_study as study_api
from learning_core_v2.acquisition import LexicalItem
from learning_core_v2.dictionary import DictionaryDetails
from learning_core_v2.subtitle_study import (
    ComprehensionCheck,
    ComprehensionResult,
    MediaAnchor,
)
from repositories.lexicon import LexiconRepository
from repositories.subtitle_sessions import SubtitleSessionRepository


MEDIA = {
    "media_key": "youtube:abc123:en:manual",
    "media_url": "https://www.youtube.com/watch?v=abc123&si=tracking",
    "media_title": "A conversation",
}

CUES = [
    {"start_ms": 1000, "end_ms": 3000, "text": "I came across an old photograph yesterday."},
    {"start_ms": 3200, "end_ms": 5200, "text": "Really? Where did you find it?"},
    {"start_ms": 5400, "end_ms": 7400, "text": "In my grandmother's attic, behind a mirror."},
    {"start_ms": 7600, "end_ms": 9600, "text": "That sounds like a proper treasure hunt."},
]


@dataclass
class Settings:
    target_lang: str = "en"
    native_lang: str = "ru"
    english_level: str = "b1"


@dataclass
class Storage:
    settings: Settings = field(default_factory=Settings)
    lexicon: LexiconRepository = field(default_factory=lambda: LexiconRepository("tester"))
    subtitle_sessions: SubtitleSessionRepository = field(
        default_factory=SubtitleSessionRepository
    )
    saves: int = 0

    def save(self):
        self.saves += 1


class Builder:
    def __init__(self, check):
        self.check = check

    async def execute(self, *_args, **_kwargs):
        return self.check


class Checker:
    def __init__(self, result):
        self.result = result

    async def execute(self, *_args, **_kwargs):
        return self.result


class Dictionary:
    async def execute(self, request):
        return DictionaryDetails(request.term, f"перевод {request.term}", "/ipa/")


def cue(index: int) -> study_api.SubtitleCue:
    return study_api.SubtitleCue(**CUES[index])


def window() -> list[study_api.SubtitleCue]:
    return [study_api.SubtitleCue(**value) for value in CUES]


@pytest.fixture
def storage(monkeypatch):
    value = Storage()
    monkeypatch.setattr(study_api, "get_storage", lambda _username: value)
    study_api._pending_checks.clear()
    return value


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_second_start_resumes_the_open_session(storage):
    first = await study_api.start_session(study_api.StartSessionRequest(**MEDIA), "tester")
    await study_api.record_progress(
        first.session_id,
        study_api.ProgressRequest(
            media_key=MEDIA["media_key"],
            events=[study_api.ProgressEvent(kind="watched", cue=cue(1))],
        ),
        "tester",
    )

    second = await study_api.start_session(study_api.StartSessionRequest(**MEDIA), "tester")

    assert second.session_id == first.session_id
    assert second.resumed is True
    assert second.cursor_ms == CUES[1]["start_ms"]
    assert second.lines_watched == 1


@pytest.mark.asyncio
async def test_progress_events_are_folded_in_one_batch(storage):
    session = await study_api.start_session(study_api.StartSessionRequest(**MEDIA), "tester")

    updated = await study_api.record_progress(
        session.session_id,
        study_api.ProgressRequest(
            media_key=MEDIA["media_key"],
            events=[
                study_api.ProgressEvent(kind="watched", cue=cue(0)),
                study_api.ProgressEvent(kind="watched", cue=cue(1)),
                study_api.ProgressEvent(kind="replayed", cue=cue(1), slowed=True),
            ],
        ),
        "tester",
    )

    assert updated.lines_watched == 2
    summary = await study_api.session_summary(session.session_id, "tester")
    assert summary.hardest[0].start_ms == CUES[1]["start_ms"]


@pytest.mark.asyncio
async def test_an_unknown_session_is_not_found(storage):
    with pytest.raises(study_api.HTTPException) as error:
        await study_api.session_summary("missing", "tester")

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_display_changes_are_persisted(storage):
    session = await study_api.start_session(study_api.StartSessionRequest(**MEDIA), "tester")

    updated = await study_api.set_display(
        session.session_id,
        study_api.DisplayRequest(
            display=study_api.DisplayModel(
                show_original=True, show_translation=False, auto_pause=True
            )
        ),
        "tester",
    )

    assert updated.display.show_translation is False
    assert updated.display.auto_pause is True
    stored = storage.subtitle_sessions.find(session.session_id)
    assert stored.display.auto_pause is True


# ---------------------------------------------------------------------------
# Fragments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_fragment_is_padded_and_logged_against_the_session(storage):
    session = await study_api.start_session(study_api.StartSessionRequest(**MEDIA), "tester")

    fragment = await study_api.plan_fragment(
        study_api.FragmentRequest(
            **MEDIA,
            lines=window(),
            cue=cue(1),
            playback_rate=0.7,
            repeats=0,
            session_id=session.session_id,
        ),
        "tester",
    )

    assert fragment.start_ms < CUES[1]["start_ms"]
    assert fragment.end_ms > CUES[1]["end_ms"]
    assert fragment.looping is True
    stored = storage.subtitle_sessions.find(session.session_id)
    assert stored.stat(fragment.line_id).slowed == 1


@pytest.mark.asyncio
async def test_a_cue_with_no_words_cannot_be_replayed(storage):
    """A blank cue has no identity, so it cannot anchor anything."""
    with pytest.raises(study_api.HTTPException) as error:
        await study_api.plan_fragment(
            study_api.FragmentRequest(
                **MEDIA,
                lines=window(),
                cue=study_api.SubtitleCue(start_ms=1000, end_ms=3000, text="   "),
            ),
            "tester",
        )

    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_a_fragment_from_a_line_the_client_did_not_send_still_resolves(storage):
    """The requested cue joins the window, so a short window is not an error."""
    fragment = await study_api.plan_fragment(
        study_api.FragmentRequest(**MEDIA, lines=window()[:1], cue=cue(3)), "tester"
    )

    assert fragment.start_ms < CUES[3]["start_ms"]


# ---------------------------------------------------------------------------
# Comprehension
# ---------------------------------------------------------------------------


def a_check(line_id="line-1") -> ComprehensionCheck:
    return ComprehensionCheck(
        check_id="check-abcdefghijklmnop",
        kind="next_line",
        line_id=line_id,
        question="subtitle_check_next_line",
        anchor=MediaAnchor(
            media_key=MEDIA["media_key"], start_ms=5400, end_ms=7400, line_text=CUES[2]["text"]
        ),
        options=(CUES[3]["text"], CUES[0]["text"], CUES[1]["text"]),
        expected_answer=CUES[3]["text"],
    )


@pytest.mark.asyncio
async def test_a_check_never_ships_its_expected_answer(storage, monkeypatch):
    check = a_check()
    monkeypatch.setattr(
        study_api,
        "build_subtitle_study_services",
        lambda: (Builder(check), Checker(ComprehensionResult("correct"))),
    )

    created = await study_api.create_check(
        study_api.QuestionRequest(**MEDIA, lines=window(), cue=cue(2)), "tester"
    )

    assert created.options == list(check.options)
    assert not hasattr(created, "expected_answer")


@pytest.mark.asyncio
async def test_a_check_belongs_to_the_user_who_asked_for_it(storage, monkeypatch):
    check = a_check()
    monkeypatch.setattr(
        study_api,
        "build_subtitle_study_services",
        lambda: (Builder(check), Checker(ComprehensionResult("correct", "Верно"))),
    )
    created = await study_api.create_check(
        study_api.QuestionRequest(**MEDIA, lines=window(), cue=cue(2)), "tester"
    )

    with pytest.raises(study_api.HTTPException) as error:
        await study_api.check_answer(
            study_api.CheckAnswerRequest(check_id=created.check_id, answer="x"), "someone-else"
        )
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_a_failed_check_lowers_the_scaffolding_for_the_session(storage, monkeypatch):
    session = await study_api.start_session(study_api.StartSessionRequest(**MEDIA), "tester")
    await study_api.set_display(
        session.session_id,
        study_api.DisplayRequest(
            display=study_api.DisplayModel(show_original=False, show_translation=False)
        ),
        "tester",
    )
    monkeypatch.setattr(
        study_api,
        "build_subtitle_study_services",
        lambda: (
            Builder(a_check()),
            Checker(ComprehensionResult("incorrect", "Не совсем", CUES[3]["text"])),
        ),
    )
    created = await study_api.create_check(
        study_api.QuestionRequest(
            **MEDIA, lines=window(), cue=cue(2), session_id=session.session_id
        ),
        "tester",
    )

    result = await study_api.check_answer(
        study_api.CheckAnswerRequest(
            check_id=created.check_id, answer="wrong", session_id=session.session_id
        ),
        "tester",
    )

    assert result.passed is False
    assert result.expected_answer == CUES[3]["text"]
    assert result.display is not None
    assert result.display.reveal_on_tap is True


@pytest.mark.asyncio
async def test_a_check_cannot_be_answered_twice(storage, monkeypatch):
    monkeypatch.setattr(
        study_api,
        "build_subtitle_study_services",
        lambda: (Builder(a_check()), Checker(ComprehensionResult("correct"))),
    )
    created = await study_api.create_check(
        study_api.QuestionRequest(**MEDIA, lines=window(), cue=cue(2)), "tester"
    )
    await study_api.check_answer(
        study_api.CheckAnswerRequest(check_id=created.check_id, answer=CUES[3]["text"]),
        "tester",
    )

    with pytest.raises(study_api.HTTPException) as error:
        await study_api.check_answer(
            study_api.CheckAnswerRequest(check_id=created.check_id, answer=CUES[3]["text"]),
            "tester",
        )
    assert error.value.status_code == 404


# ---------------------------------------------------------------------------
# Saving words with a timecode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_saved_word_keeps_the_video_and_the_timecode(storage):
    session = await study_api.start_session(study_api.StartSessionRequest(**MEDIA), "tester")

    saved = await study_api.save_word(
        study_api.SaveWordRequest(
            **MEDIA,
            term="came across",
            translation="наткнулся",
            cue=cue(0),
            session_id=session.session_id,
        ),
        "tester",
    )

    assert saved.anchor.start_ms == CUES[0]["start_ms"]
    assert saved.anchor.end_ms == CUES[0]["end_ms"]
    assert saved.anchor.line_text == CUES[0]["text"]
    # The video id lives in the query, so a media URL keeps it; the tracking
    # parameter does not survive.
    assert saved.anchor.media_url == "https://www.youtube.com/watch?v=abc123"
    stored = storage.lexicon.find(saved.item_id)
    assert stored.latest_media.start_ms == CUES[0]["start_ms"]
    assert stored.latest_context == CUES[0]["text"]


@pytest.mark.asyncio
async def test_two_meanings_of_one_spelling_stay_two_cards(storage):
    await study_api.save_word(
        study_api.SaveWordRequest(**MEDIA, term="figure", translation="фигура", cue=cue(0)),
        "tester",
    )
    second = await study_api.save_word(
        study_api.SaveWordRequest(**MEDIA, term="figure", translation="цифра", cue=cue(1)),
        "tester",
    )

    items = [item for item in storage.lexicon.all() if item.term == "figure"]
    assert len(items) == 2
    assert second.item_id != items[0].item_id


@pytest.mark.asyncio
async def test_the_same_sense_at_two_timecodes_is_two_encounters(storage):
    first = await study_api.save_word(
        study_api.SaveWordRequest(**MEDIA, term="found", translation="нашёл", cue=cue(1)),
        "tester",
    )
    second = await study_api.save_word(
        study_api.SaveWordRequest(**MEDIA, term="found", translation="нашёл", cue=cue(2)),
        "tester",
    )

    assert first.item_id == second.item_id
    assert second.encounter_count == 2


@pytest.mark.asyncio
async def test_known_senses_are_offered_before_a_new_one_is_created(storage, monkeypatch):
    storage.lexicon.append(
        LexicalItem("bank-finance", "bank", "en", "банк", status="learning")
    )
    monkeypatch.setattr(study_api, "build_dictionary_enrichment", lambda: Dictionary())

    senses = await study_api.word_senses(
        study_api.SensesRequest(**MEDIA, term="bank", cue=cue(0)), "tester"
    )

    assert [sense.translation for sense in senses.known_senses] == ["банк"]
    assert senses.needs_disambiguation is True
    assert senses.suggestion is not None


# ---------------------------------------------------------------------------
# Cloze
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_cloze_is_built_from_the_real_line(storage):
    exercise = await study_api.build_cloze(
        study_api.ClozeRequest(**MEDIA, cue=cue(0), surface="came across"), "tester"
    )

    assert exercise.prompt == "I ___ an old photograph yesterday."
    assert exercise.answer == "came across"
    assert exercise.anchor.start_ms == CUES[0]["start_ms"]


@pytest.mark.asyncio
async def test_an_ambiguous_cloze_is_refused_rather_than_shown(storage):
    with pytest.raises(study_api.HTTPException) as error:
        await study_api.build_cloze(
            study_api.ClozeRequest(
                **MEDIA,
                cue=study_api.SubtitleCue(start_ms=0, end_ms=2000, text="Come across now"),
                surface="come across now",
            ),
            "tester",
        )

    assert error.value.status_code == 422
