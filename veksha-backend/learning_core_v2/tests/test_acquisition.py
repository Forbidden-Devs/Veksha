import pytest

from learning_core_v2.acquisition import (
    DecideVocabulary,
    LexicalItem,
    lexical_item_id,
    SuggestVocabulary,
    VocabularyEncounter,
    VocabularyProposal,
)


def proposal(**overrides):
    values = {
        "term": "come across",
        "language": "en",
        "translation": "случайно найти",
        "transcription": "/kʌm əˈkrɒs/",
        "context": "She came across an old photograph.",
        "source_url": "https://example.test/story",
    }
    values.update(overrides)
    return VocabularyProposal(**values)


def test_creates_a_suggestion_with_its_first_encounter():
    result = SuggestVocabulary().execute(
        (), proposal(), observed_at=123.0
    )

    assert result[0].status == "suggested"
    assert result[0].encounters == (
        VocabularyEncounter(
            "She came across an old photograph.",
            "https://example.test/story",
            123.0,
        ),
    )


def test_repeated_sense_adds_an_encounter_without_a_duplicate_item():
    service = SuggestVocabulary()
    first = service.execute((), proposal(), observed_at=1.0)

    result = service.execute(
        first,
        proposal(context="I came across this phrase again."),
        observed_at=2.0,
    )

    assert len(result) == 1
    assert [item.context for item in result[0].encounters] == [
        "She came across an old photograph.",
        "I came across this phrase again.",
    ]


def test_same_form_with_another_meaning_stays_a_separate_sense():
    service = SuggestVocabulary()
    first = service.execute((), proposal(), observed_at=1.0)

    result = service.execute(
        first,
        proposal(translation="встретить случайно"),
        observed_at=2.0,
    )

    assert [item.item_id for item in result] == [
        lexical_item_id("come across", "en", "случайно найти"),
        lexical_item_id("come across", "en", "встретить случайно"),
    ]


def test_sense_identifier_is_stable_but_changes_with_meaning():
    first = lexical_item_id(" Bank ", "EN_us", "  БАНК ")
    repeated = lexical_item_id("bank", "en-us", "банк")
    another_sense = lexical_item_id("bank", "en-us", "берег")

    assert first == repeated
    assert another_sense != first


@pytest.mark.parametrize(
    ("decision", "status"),
    [("learn", "learning"), ("known", "known"), ("ignore", "ignored")],
)
def test_decision_is_an_explicit_one_way_transition(decision, status):
    item = LexicalItem("item-1", "word", "en", "слово")

    decided = DecideVocabulary().execute(item, decision)

    assert decided.status == status
    with pytest.raises(ValueError):
        DecideVocabulary().execute(decided, decision)


def test_invalid_proposal_is_rejected():
    with pytest.raises(ValueError):
        SuggestVocabulary().execute(
            (), proposal(translation=" "), observed_at=1.0
        )


def test_source_url_drops_query_parameters_and_fragments():
    result = SuggestVocabulary().execute(
        (),
        proposal(source_url="https://example.test/story?token=secret#selection"),
        observed_at=1.0,
    )

    assert result[0].encounters[0].source_url == "https://example.test/story"
