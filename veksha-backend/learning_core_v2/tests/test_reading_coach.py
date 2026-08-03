from learning_core_v2.reading_coach import AssessReading, ReadingToken


def test_finds_high_impact_obstacles_and_projects_the_gain():
    tokens = [
        ReadingToken("the", 50, "A1"),
        ReadingToken("house", 20, "A2"),
        ReadingToken("sustainable", 8, "B2"),
        ReadingToken("procurement", 4, "C1"),
        ReadingToken("retrofit", 6, "C1", "learning"),
    ]

    result = AssessReading(maximum_obstacles=2).execute(tokens, learner_cefr="B1")

    assert [item.term for item in result.obstacles] == ["retrofit", "sustainable"]
    assert result.projected_known_ratio > result.known_ratio
    assert result.verdict == "too_hard"


def test_explicit_knowledge_overrides_frequency_prior():
    result = AssessReading().execute(
        [
            ReadingToken("simple", 5, "A1", "learning"),
            ReadingToken("obscure", 5, "C2", "known"),
        ],
        learner_cefr="B1",
    )

    assert result.known_ratio == 0.5
    assert result.obstacles[0].term == "simple"
    assert result.obstacles[0].reason == "learning"


def test_ignored_terms_affect_coverage_but_are_not_suggested_again():
    result = AssessReading().execute(
        [ReadingToken("ignored", 3, "C1", "ignored")],
        learner_cefr="B1",
    )

    assert result.known_ratio == 0.0
    assert result.obstacles == ()


def test_suggestion_state_is_visible_to_the_coach():
    result = AssessReading().execute(
        [ReadingToken("pending", 3, "B2", "suggested")],
        learner_cefr="B1",
    )

    assert result.obstacles[0].reason == "already_suggested"


def test_empty_sample_returns_a_low_confidence_result():
    result = AssessReading().execute([], learner_cefr="unknown")

    assert result.unique_terms == 0
    assert result.confidence == "low"
