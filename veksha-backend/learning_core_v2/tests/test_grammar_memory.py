import pytest

from learning_core_v2.grammar_memory import (
    GrammarObservation,
    RememberGrammar,
    SetGrammarStatus,
)


def observation(**overrides):
    values = {
        "language": "en",
        "category": "tense_aspect",
        "label": "Present perfect",
        "explanation": "Links a past event to now.",
        "example": "I have finished the article.",
        "source_url": "https://example.test/story?token=secret#part",
    }
    values.update(overrides)
    return GrammarObservation(**values)


def test_remember_grammar_merges_distinct_grounded_encounters():
    remember = RememberGrammar()
    first = remember.execute([], observation(), item_id="pattern-1", observed_at=10)
    second = remember.execute(
        first,
        observation(example="She has already left."),
        item_id="ignored",
        observed_at=20,
    )

    assert len(second) == 1
    assert second[0].seen_count == 2
    assert len(second[0].encounters) == 2
    assert second[0].encounters[0].source_url == "https://example.test/story"
    assert second[0].last_seen_at == 20


def test_duplicate_page_example_does_not_inflate_memory():
    remember = RememberGrammar()
    first = remember.execute([], observation(), item_id="pattern-1", observed_at=10)
    second = remember.execute(first, observation(), item_id="ignored", observed_at=20)

    assert second[0].seen_count == 1
    assert len(second[0].encounters) == 1


def test_status_can_be_reopened_after_mastery():
    item = RememberGrammar().execute([], observation(), item_id="pattern-1", observed_at=10)[0]
    mastered = SetGrammarStatus().execute(item, "mastered")
    assert mastered.status == "mastered"
    assert SetGrammarStatus().execute(mastered, "learning").status == "learning"


def test_rejects_unrecognised_category():
    with pytest.raises(ValueError, match="category"):
        RememberGrammar().execute(
            [],
            observation(category="invented"),
            item_id="pattern-1",
            observed_at=10,
        )
