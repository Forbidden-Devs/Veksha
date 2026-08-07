"""A session and its saved words have to survive a reload to be resumable."""

from learning_core_v2.acquisition import (
    SuggestVocabulary,
    VocabularyProposal,
)
from learning_core_v2.subtitle_study import (
    ComprehensionResult,
    MediaAnchor,
    SubtitleDisplay,
    SubtitleLine,
    SubtitleStudySession,
    TrackSubtitleSession,
)
from repositories.lexicon import LexiconRepository
from repositories.subtitle_sessions import (
    MAX_STORED_SESSIONS,
    SubtitleSessionRepository,
)


MEDIA = "youtube:abc123:en:manual"


def a_line() -> SubtitleLine:
    return SubtitleLine(
        line_id="11111111-1111-5111-9111-111111111111",
        index=4,
        start_ms=5400,
        end_ms=7400,
        text="In my grandmother's attic, behind a mirror.",
    )


def test_a_session_round_trips_through_the_document():
    tracker = TrackSubtitleSession()
    line = a_line()
    session = SubtitleStudySession(
        session_id="s1",
        media_key=MEDIA,
        media_url="https://www.youtube.com/watch?v=abc123",
        media_title="A conversation",
        display=SubtitleDisplay().with_mode("hidden").with_auto_pause(True),
        check_interval=7,
        started_at=100.0,
    )
    session = tracker.watched(session, line, now=101.0)
    session = tracker.replayed(
        session, line.line_id, start_ms=line.start_ms, slowed=True, now=102.0
    )
    session = tracker.checked(
        session, line.line_id, ComprehensionResult("incorrect"), start_ms=line.start_ms, now=103.0
    )
    session = tracker.saved(session, line.line_id, "item-1", start_ms=line.start_ms, now=104.0)

    repository = SubtitleSessionRepository()
    repository.save(session)
    reloaded = SubtitleSessionRepository.from_document(repository.to_document()).find("s1")

    assert reloaded == session
    assert reloaded.cursor_ms == line.start_ms
    assert reloaded.display.auto_pause is True
    assert reloaded.check_interval == 7
    assert reloaded.stat(line.line_id).start_ms == line.start_ms
    assert reloaded.saved_item_ids == ("item-1",)


def test_only_the_open_session_for_a_video_is_resumed():
    tracker = TrackSubtitleSession()
    repository = SubtitleSessionRepository()
    closed = tracker.closed(
        SubtitleStudySession(session_id="old", media_key=MEDIA, updated_at=1.0), now=2.0
    )
    open_session = SubtitleStudySession(session_id="new", media_key=MEDIA, updated_at=3.0)
    other_video = SubtitleStudySession(session_id="other", media_key="youtube:zzz:en:manual")
    repository.save(closed)
    repository.save(open_session)
    repository.save(other_video)

    assert repository.open_for_media(MEDIA).session_id == "new"
    assert repository.open_for_media("youtube:nope:en:manual") is None


def test_stored_sessions_are_bounded():
    repository = SubtitleSessionRepository()
    for index in range(MAX_STORED_SESSIONS + 5):
        repository.save(SubtitleStudySession(session_id=f"s{index}", media_key=MEDIA))

    assert len(repository) == MAX_STORED_SESSIONS
    assert repository.find("s0") is None
    assert repository.find(f"s{MAX_STORED_SESSIONS + 4}") is not None


def test_a_saved_word_keeps_its_timecode_across_a_reload():
    anchor = MediaAnchor(
        media_key=MEDIA,
        media_url="https://www.youtube.com/watch?v=abc123",
        start_ms=1000,
        end_ms=3000,
        line_text="I came across an old photograph yesterday.",
        line_translation="Я наткнулся на старую фотографию вчера.",
        language="en",
        speaker="Anna",
    )
    items = SuggestVocabulary().execute(
        (),
        VocabularyProposal(
            term="came across",
            language="en",
            translation="наткнулся",
            context=anchor.line_text,
            media=anchor,
        ),
        observed_at=10.0,
    )
    repository = LexiconRepository("tester", items)

    reloaded, _ = LexiconRepository.from_document(
        "tester", {"lexical_items": repository.to_document()}
    )
    stored = reloaded.all()[0]

    assert stored.latest_media == anchor
    assert stored.latest_media.speaker == "Anna"


def test_a_word_saved_from_a_page_stores_no_timecode():
    items = SuggestVocabulary().execute(
        (),
        VocabularyProposal(
            term="photograph",
            language="en",
            translation="фотография",
            context="An old photograph.",
            source_url="https://example.test/article?utm_source=x",
        ),
        observed_at=10.0,
    )
    document = LexiconRepository("tester", items).to_document()

    assert "media" not in document[0]["encounters"][0]
    reloaded, _ = LexiconRepository.from_document("tester", {"lexical_items": document})
    assert reloaded.all()[0].latest_media is None
