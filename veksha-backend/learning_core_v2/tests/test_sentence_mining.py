from __future__ import annotations

from dataclasses import replace

import pytest

from learning_core_v2.sentence_mining import (
    BuildSentenceMiningCard,
    CollocationDraft,
    ExampleDraft,
    SentenceMiningDraft,
    SentenceMiningRequest,
)


REQUEST = SentenceMiningRequest(
    term="make",
    known_translation="делать",
    context="I make coffee every morning.",
    learning_language="en",
    native_language="ru",
    learner_cefr="A2",
    stretch_cefr="B1",
    learner_example_count=1,
    stretch_example_count=1,
)


class StubProvider:
    def __init__(self, draft: SentenceMiningDraft) -> None:
        self.draft = draft
        self.requests = []

    async def build_sentence_mining_card(self, request):
        self.requests.append(request)
        return self.draft


def complete_draft() -> SentenceMiningDraft:
    return SentenceMiningDraft(
        examples=(
            ExampleDraft(" I make coffee. ", " Я готовлю кофе. ", "a2"),
            ExampleDraft("We made a decision.", "Мы приняли решение.", "B1"),
        ),
        mnemonic=" Make sounds like мейк. ",
        collocations=(
            CollocationDraft("make a decision", "принять решение"),
            CollocationDraft("make progress", "добиваться прогресса"),
            CollocationDraft("make sure", "убедиться"),
        ),
    )


@pytest.mark.asyncio
async def test_builds_ordered_level_aware_card():
    provider = StubProvider(complete_draft())

    card = await BuildSentenceMiningCard(provider).execute(REQUEST)

    assert [example.level for example in card.examples] == ["A2", "B1"]
    assert [example.is_higher for example in card.examples] == [False, True]
    assert card.examples[0].sentence == "I make coffee."
    assert card.mnemonic == "Make sounds like мейк."
    assert len(card.collocations) == 3


@pytest.mark.asyncio
async def test_deduplicates_and_rejects_wrong_level_examples():
    draft = complete_draft()
    provider = StubProvider(
        SentenceMiningDraft(
            examples=(
                ExampleDraft("Wrong level.", "Не тот уровень.", "C2"),
                draft.examples[0],
                ExampleDraft("I MAKE COFFEE.", "Дубликат.", "A2"),
                draft.examples[1],
            ),
            mnemonic=draft.mnemonic,
            collocations=draft.collocations,
        )
    )

    card = await BuildSentenceMiningCard(provider).execute(REQUEST)

    assert [example.sentence for example in card.examples] == [
        "I make coffee.",
        "We made a decision.",
    ]


@pytest.mark.asyncio
async def test_same_cefr_band_combines_both_example_quotas():
    request = replace(REQUEST, learner_cefr="C2", stretch_cefr="C2")
    draft = complete_draft()
    provider = StubProvider(
        SentenceMiningDraft(
            examples=(
                ExampleDraft("First C2 example.", "Первый пример.", "C2"),
                ExampleDraft("Second C2 example.", "Второй пример.", "C2"),
            ),
            mnemonic=draft.mnemonic,
            collocations=draft.collocations,
        )
    )

    card = await BuildSentenceMiningCard(provider).execute(request)

    assert len(card.examples) == 2
    assert all(not example.is_higher for example in card.examples)


@pytest.mark.asyncio
async def test_incomplete_card_is_rejected():
    draft = complete_draft()
    provider = StubProvider(
        SentenceMiningDraft(
            examples=draft.examples[:1],
            mnemonic=draft.mnemonic,
            collocations=draft.collocations[:2],
        )
    )

    with pytest.raises(ValueError, match="incomplete examples"):
        await BuildSentenceMiningCard(provider).execute(REQUEST)


@pytest.mark.asyncio
async def test_card_requires_mnemonic_and_three_collocations():
    draft = complete_draft()
    no_mnemonic = StubProvider(
        SentenceMiningDraft(draft.examples, " ", draft.collocations)
    )
    too_few_collocations = StubProvider(
        SentenceMiningDraft(draft.examples, draft.mnemonic, draft.collocations[:2])
    )

    with pytest.raises(ValueError, match="empty mnemonic"):
        await BuildSentenceMiningCard(no_mnemonic).execute(REQUEST)
    with pytest.raises(ValueError, match="too few collocations"):
        await BuildSentenceMiningCard(too_few_collocations).execute(REQUEST)


@pytest.mark.asyncio
async def test_invalid_request_is_rejected_before_provider():
    provider = StubProvider(complete_draft())
    invalid = SentenceMiningRequest(
        term=" ",
        known_translation="",
        context="",
        learning_language="en",
        native_language="ru",
        learner_cefr="A2",
        stretch_cefr="B1",
        learner_example_count=1,
        stretch_example_count=1,
    )

    with pytest.raises(ValueError):
        await BuildSentenceMiningCard(provider).execute(invalid)

    assert provider.requests == []
