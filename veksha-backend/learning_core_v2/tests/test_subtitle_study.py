import pytest

from learning_core_v2.subtitle_study import (
    BuildComprehensionCheck,
    BuildLineCloze,
    BuildSubtitleTimeline,
    CheckComprehensionAnswer,
    ComprehensionPolicy,
    ComprehensionResult,
    CueDraft,
    PlanFragment,
    ScaffoldLadder,
    SubtitleAnswerEvaluation,
    SubtitleDisplay,
    SubtitleQuestionDraft,
    SubtitleStudySession,
    TrackSubtitleSession,
    context_for,
    subtitle_line_id,
    summarize,
)


MEDIA = "youtube:abc123:en:manual"

DIALOGUE = (
    CueDraft(1000, 3000, "I came across an old photograph yesterday."),
    CueDraft(3200, 5200, "Really? Where did you find it?"),
    CueDraft(5400, 7400, "In my grandmother's attic, behind a mirror."),
    CueDraft(7600, 9600, "That sounds like a proper treasure hunt."),
    CueDraft(9800, 11800, "It was, and it took the whole afternoon."),
)


def timeline():
    return BuildSubtitleTimeline().execute(MEDIA, DIALOGUE)


class Provider:
    def __init__(self, question="Why did the speaker say that?", outcome="correct"):
        self.question = question
        self.outcome = outcome
        self.requests = []

    async def create_subtitle_question(self, request):
        self.requests.append(request)
        return SubtitleQuestionDraft(self.question, "Because they found a photograph.")

    async def evaluate_subtitle_answer(self, request):
        self.requests.append(request)
        return SubtitleAnswerEvaluation(self.outcome, "Хорошо")


class Identifiers:
    def __init__(self):
        self.count = 0

    def new(self):
        self.count += 1
        return f"check-{self.count}"


# ---------------------------------------------------------------------------
# Line identity
# ---------------------------------------------------------------------------


def test_line_ids_survive_caption_timing_jitter():
    lines = timeline()
    text = DIALOGUE[0].text

    assert subtitle_line_id(MEDIA, 1049, text) == lines[0].line_id
    assert subtitle_line_id(MEDIA, 1000, text) == lines[0].line_id


def test_line_ids_separate_tracks_and_adjacent_cues():
    lines = timeline()

    assert len({line.line_id for line in lines}) == len(lines)
    assert subtitle_line_id("youtube:abc123:en:asr", 1000, DIALOGUE[0].text) != lines[0].line_id


def test_timeline_orders_and_deduplicates_cues():
    lines = BuildSubtitleTimeline().execute(
        MEDIA,
        [
            CueDraft(5000, 6000, "Second line here."),
            CueDraft(1000, 2000, "First line here."),
            CueDraft(1000, 2000, "First   line here."),
            CueDraft(2500, 3000, "   "),
        ],
    )

    assert [line.text for line in lines] == ["First line here.", "Second line here."]
    assert [line.index for line in lines] == [0, 1]


# ---------------------------------------------------------------------------
# Display and scaffolding
# ---------------------------------------------------------------------------


def test_texts_are_hidden_independently():
    display = SubtitleDisplay()

    assert display.mode == "dual"
    assert display.with_mode("original").mode == "original"
    assert display.with_mode("translation").mode == "translation"
    assert display.with_mode("hidden").mode == "hidden"
    assert display.with_mode("reveal_on_tap").mode == "reveal_on_tap"


def test_auto_pause_survives_a_display_change():
    display = SubtitleDisplay().with_auto_pause(True).with_mode("hidden")

    assert display.auto_pause is True


def test_scaffolding_is_removed_one_rung_at_a_time_and_restored_at_once():
    ladder = ScaffoldLadder(promote_after_clean_lines=3)

    promoted = ladder.adjust(SubtitleDisplay(), clean_lines=3, recent_errors=0)
    assert promoted.mode == "original"

    demoted = ladder.adjust(promoted, clean_lines=99, recent_errors=1)
    assert demoted.mode == "dual"


def test_translation_only_is_a_choice_not_a_rung():
    ladder = ScaffoldLadder(promote_after_clean_lines=1)
    display = SubtitleDisplay().with_mode("translation")

    assert ladder.adjust(display, clean_lines=50, recent_errors=0).mode == "translation"


# ---------------------------------------------------------------------------
# Fragment replay
# ---------------------------------------------------------------------------


def test_padding_never_swallows_a_neighbouring_line():
    lines = timeline()
    context = context_for(lines, lines[1].line_id)

    loop = PlanFragment(lead_in_ms=3000, lead_out_ms=3000).execute(context)

    assert loop.start_ms >= lines[0].start_ms
    assert loop.end_ms <= lines[2].end_ms


def test_padding_is_clamped_to_the_media_bounds():
    lines = timeline()
    context = context_for(lines, lines[0].line_id)

    loop = PlanFragment(lead_in_ms=2000, lead_out_ms=2000).execute(
        context, media_duration_ms=4000
    )

    assert loop.start_ms == 0
    assert loop.end_ms == 4000


def test_returning_after_an_error_starts_at_the_line_that_set_it_up():
    lines = timeline()
    context = context_for(lines, lines[2].line_id)

    loop = PlanFragment().execute(context, include_previous_line=True)

    assert loop.start_ms == lines[1].start_ms


def test_loop_and_slow_motion_are_bounded():
    lines = timeline()
    context = context_for(lines, lines[0].line_id)

    endless = PlanFragment().execute(context, repeats=0, playback_rate=0.5)
    assert endless.looping is True
    assert endless.playback_rate == 0.5

    with pytest.raises(ValueError):
        PlanFragment().execute(context, playback_rate=0.1)
    with pytest.raises(ValueError):
        PlanFragment().execute(context, repeats=999)


# ---------------------------------------------------------------------------
# Comprehension checks
# ---------------------------------------------------------------------------


def test_checks_are_only_offered_when_the_material_supports_them():
    lines = timeline()
    middle = ComprehensionPolicy().feasible(context_for(lines, lines[2].line_id))
    first = ComprehensionPolicy().feasible(context_for(lines, lines[0].line_id, before=0, after=0))

    assert "next_line" in middle
    assert "next_line" not in first
    assert "expression_meaning" not in middle


def test_check_rotation_is_deterministic():
    lines = timeline()
    context = context_for(lines, lines[2].line_id)
    policy = ComprehensionPolicy()

    picks = [policy.select(context, checks_done=index) for index in range(4)]

    assert picks == [policy.select(context, checks_done=index) for index in range(4)]
    assert len(set(picks)) > 1


@pytest.mark.asyncio
async def test_grounded_checks_never_reach_the_provider():
    lines = timeline()
    context = context_for(lines, lines[2].line_id)
    provider = Provider()
    builder = BuildComprehensionCheck(provider, Identifiers())

    check = await builder.execute(
        context,
        "next_line",
        anchor=context.line.anchor(MEDIA),
        learner_cefr="B1",
        learning_language="en",
        native_language="ru",
    )

    assert provider.requests == []
    assert check.expected_answer == lines[3].text
    # Every distractor is a line that was really spoken in this video.
    assert set(check.options) <= {line.text for line in lines}


@pytest.mark.asyncio
async def test_which_word_options_come_from_the_dialogue():
    lines = timeline()
    context = context_for(lines, lines[2].line_id)
    check = await BuildComprehensionCheck(Provider(), Identifiers()).execute(
        context,
        "which_word",
        anchor=context.line.anchor(MEDIA),
        learner_cefr="B1",
        learning_language="en",
        native_language="ru",
    )

    spoken = set(context.line.words)
    neighbouring = {word for line in context.neighbours for word in line.words}
    assert check.expected_answer in spoken
    # Exactly one option was spoken in this line; every distractor is a real
    # word from the surrounding dialogue rather than an invented one.
    assert [option for option in check.options if option in spoken] == [check.expected_answer]
    assert all(
        option in neighbouring for option in check.options if option != check.expected_answer
    )


@pytest.mark.asyncio
async def test_choice_answers_are_graded_without_the_provider():
    lines = timeline()
    context = context_for(lines, lines[2].line_id)
    provider = Provider()
    check = await BuildComprehensionCheck(provider, Identifiers()).execute(
        context,
        "next_line",
        anchor=context.line.anchor(MEDIA),
        learner_cefr="B1",
        learning_language="en",
        native_language="ru",
    )

    result = await CheckComprehensionAnswer(provider).execute(
        check,
        check.expected_answer,
        transcript=context.transcript(),
        learner_cefr="B1",
        learning_language="en",
        native_language="ru",
    )

    assert result.outcome == "correct"
    assert provider.requests == []


@pytest.mark.asyncio
async def test_an_empty_answer_is_not_an_answer():
    lines = timeline()
    context = context_for(lines, lines[2].line_id)
    provider = Provider()
    check = await BuildComprehensionCheck(provider, Identifiers()).execute(
        context,
        "why_said",
        anchor=context.line.anchor(MEDIA),
        learner_cefr="B1",
        learning_language="en",
        native_language="ru",
    )
    provider.requests.clear()

    result = await CheckComprehensionAnswer(provider).execute(
        check,
        "   ",
        transcript=context.transcript(),
        learner_cefr="B1",
        learning_language="en",
        native_language="ru",
    )

    assert result.outcome == "garbage"
    assert provider.requests == []


@pytest.mark.asyncio
async def test_an_expression_check_requires_an_expression():
    lines = timeline()
    context = context_for(lines, lines[0].line_id)

    with pytest.raises(ValueError):
        await BuildComprehensionCheck(Provider(), Identifiers()).execute(
            context,
            "expression_meaning",
            anchor=context.line.anchor(MEDIA),
            learner_cefr="B1",
            learning_language="en",
            native_language="ru",
        )


# ---------------------------------------------------------------------------
# Cloze
# ---------------------------------------------------------------------------


def test_cloze_hides_the_form_that_was_actually_spoken():
    line = timeline()[0]

    exercise = BuildLineCloze().execute(line, "came across", anchor=line.anchor(MEDIA))

    assert exercise.prompt == "I ___ an old photograph yesterday."
    assert exercise.answer == "came across"
    assert exercise.first_letter == "c"
    assert exercise.blank_count == 1


def test_cloze_hides_every_occurrence_of_the_target():
    line = BuildSubtitleTimeline().execute(
        MEDIA, [CueDraft(0, 2000, "You said photograph, and I said photograph too.")]
    )[0]

    exercise = BuildLineCloze().execute(line, "photograph", anchor=line.anchor(MEDIA))

    assert exercise.prompt.count("___") == 2
    assert "photograph" not in exercise.prompt


def test_cloze_matching_is_case_insensitive_but_the_answer_keeps_its_casing():
    line = BuildSubtitleTimeline().execute(
        MEDIA, [CueDraft(0, 2000, "Photograph albums were everywhere in that attic.")]
    )[0]

    exercise = BuildLineCloze().execute(line, "photograph", anchor=line.anchor(MEDIA))

    assert exercise.answer == "Photograph"


def test_cloze_refuses_a_target_that_is_not_in_the_line():
    line = timeline()[0]

    with pytest.raises(ValueError):
        BuildLineCloze().execute(line, "stumbled upon", anchor=line.anchor(MEDIA))


def test_cloze_refuses_to_leave_an_unanswerable_puzzle():
    line = BuildSubtitleTimeline().execute(
        MEDIA, [CueDraft(0, 2000, "Come across the bridge now")]
    )[0]

    with pytest.raises(ValueError):
        BuildLineCloze().execute(line, "come across the bridge", anchor=line.anchor(MEDIA))


def test_cloze_refuses_a_target_too_short_to_answer():
    line = timeline()[0]

    with pytest.raises(ValueError):
        BuildLineCloze().execute(line, "I", anchor=line.anchor(MEDIA))


def test_cloze_keeps_the_link_to_the_source_video():
    line = timeline()[0]

    exercise = BuildLineCloze().execute(
        line, "came across", anchor=line.anchor(MEDIA, "https://example.test/watch", "en")
    )

    assert exercise.anchor.start_ms == line.start_ms
    assert exercise.anchor.end_ms == line.end_ms
    assert exercise.anchor.media_url == "https://example.test/watch"


# ---------------------------------------------------------------------------
# Session progress
# ---------------------------------------------------------------------------


def session():
    return SubtitleStudySession(session_id="s1", media_key=MEDIA, started_at=1.0)


def test_watching_the_same_line_twice_is_not_progress():
    lines = timeline()
    tracker = TrackSubtitleSession()

    state = tracker.watched(session(), lines[0], now=2.0)
    state = tracker.watched(state, lines[0], now=3.0)

    assert state.lines_watched == 1
    assert state.cursor_line_id == lines[0].line_id
    assert state.cursor_ms == lines[0].start_ms


def test_repeated_fragments_accumulate_a_difficulty_signal():
    lines = timeline()
    tracker = TrackSubtitleSession()

    state = tracker.replayed(
        session(), lines[1].line_id, start_ms=lines[1].start_ms, now=2.0
    )
    state = tracker.replayed(
        state, lines[1].line_id, start_ms=lines[1].start_ms, slowed=True, now=3.0
    )

    stat = state.stat(lines[1].line_id)
    assert (stat.replays, stat.slowed) == (2, 1)
    assert stat.difficulty > 0
    assert stat.start_ms == lines[1].start_ms


def test_a_failed_check_lowers_the_scaffolding_and_resets_the_streak():
    lines = timeline()
    tracker = TrackSubtitleSession()
    state = session()
    state = tracker.displayed(state, SubtitleDisplay().with_mode("hidden"), now=2.0)

    state = tracker.checked(
        state, lines[0].line_id, ComprehensionResult("incorrect"), now=3.0
    )

    assert state.display.mode == "reveal_on_tap"
    assert state.clean_streak == 0
    assert (state.checks_asked, state.checks_passed) == (1, 0)
    assert state.lines_since_check == 0


def test_scaffolding_comes_off_after_a_run_of_clean_lines():
    tracker = TrackSubtitleSession(ScaffoldLadder(promote_after_clean_lines=3))
    lines = BuildSubtitleTimeline().execute(
        MEDIA, [CueDraft(i * 2000, i * 2000 + 1500, f"Line number {i}.") for i in range(4)]
    )
    state = session()
    for line in lines[:3]:
        state = tracker.watched(state, line, now=2.0)

    state = tracker.checked(
        state, lines[2].line_id, ComprehensionResult("correct"), now=3.0
    )

    assert state.display.mode == "original"
    # The next rung has to be earned again from zero.
    assert state.clean_streak == 0


def test_a_replayed_line_does_not_count_towards_removing_scaffolding():
    tracker = TrackSubtitleSession(ScaffoldLadder(promote_after_clean_lines=2))
    lines = timeline()
    state = session()
    state = tracker.replayed(state, lines[1].line_id, start_ms=lines[1].start_ms, now=2.0)
    state = tracker.watched(state, lines[1], now=3.0)
    state = tracker.watched(state, lines[2], now=4.0)

    state = tracker.checked(
        state, lines[2].line_id, ComprehensionResult("correct"), now=5.0
    )

    assert state.display.mode == "dual"


def test_a_passed_check_counts_and_clears_the_interval():
    lines = timeline()
    tracker = TrackSubtitleSession()
    state = tracker.watched(session(), lines[0], now=2.0)

    state = tracker.checked(
        state, lines[0].line_id, ComprehensionResult("vague"), now=3.0
    )

    assert (state.checks_asked, state.checks_passed) == (1, 1)
    assert state.lines_since_check == 0


def test_saved_items_are_recorded_once_per_sense():
    lines = timeline()
    tracker = TrackSubtitleSession()

    state = tracker.saved(session(), lines[0].line_id, "item-1", now=2.0)
    state = tracker.saved(state, lines[0].line_id, "item-1", now=3.0)

    assert state.saved_item_ids == ("item-1",)
    assert state.stat(lines[0].line_id).saves == 2


def test_a_session_resumes_on_the_line_it_stopped_on():
    lines = timeline()
    tracker = TrackSubtitleSession()

    state = tracker.watched(session(), lines[0], now=2.0)
    state = tracker.watched(state, lines[1], now=3.0)

    assert state.cursor_line_id == lines[1].line_id
    assert state.cursor_ms == lines[1].start_ms
    assert state.open is True
    assert tracker.closed(state, now=4.0).open is False


def test_the_summary_ranks_the_fragments_that_resisted():
    lines = timeline()
    tracker = TrackSubtitleSession()
    state = session()
    state = tracker.replayed(state, lines[0].line_id, start_ms=lines[0].start_ms, now=2.0)
    for _ in range(3):
        state = tracker.replayed(state, lines[2].line_id, start_ms=lines[2].start_ms, now=3.0)
    state = tracker.checked(state, lines[2].line_id, ComprehensionResult("correct"), now=4.0)

    summary = summarize(state)

    assert summary.hardest[0].line_id == lines[2].line_id
    assert summary.checks_asked == 1
    assert summary.accuracy == 1.0


def test_tracked_lines_are_bounded():
    tracker = TrackSubtitleSession(maximum_tracked_lines=2)
    state = session()
    for index in range(5):
        state = tracker.replayed(state, f"line-{index}", now=float(index))

    assert [stat.line_id for stat in state.stats] == ["line-3", "line-4"]
