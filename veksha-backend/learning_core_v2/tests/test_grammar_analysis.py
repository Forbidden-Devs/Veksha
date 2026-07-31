import pytest

from learning_core_v2.grammar_analysis import (
    AnalyzeGrammar,
    GrammarAnalysisDraft,
    GrammarAnalysisRequest,
    GrammarAnnotationDraft,
    GrammarSegmentDraft,
)


pytestmark = pytest.mark.asyncio


class Provider:
    def __init__(self, draft):
        self.draft = draft
        self.requests = []

    async def analyze_grammar(self, request):
        self.requests.append(request)
        return self.draft


async def test_segments_keep_exact_source_order_and_valid_roles():
    text = "The cat sat on the mat yesterday."
    provider = Provider(
        GrammarAnalysisDraft(
            segments=(
                GrammarSegmentDraft("The cat", "subject", "who"),
                GrammarSegmentDraft("sat", "verb", "action"),
                GrammarSegmentDraft("on the mat", "place", "where"),
                GrammarSegmentDraft("yesterday", "time", "when"),
            )
        )
    )
    result = await AnalyzeGrammar(provider).execute(
        GrammarAnalysisRequest(text, "ru", "b1")
    )
    assert [item.role for item in result.segments] == [
        "subject",
        "verb",
        "place",
        "time",
    ]


async def test_segments_drop_unknown_missing_and_out_of_order_spans():
    text = "Birds sing and children listen."
    provider = Provider(
        GrammarAnalysisDraft(
            segments=(
                GrammarSegmentDraft("sing", "verb"),
                GrammarSegmentDraft("Birds", "subject"),
                GrammarSegmentDraft("missing", "object"),
                GrammarSegmentDraft("children", "invented"),
            )
        )
    )
    result = await AnalyzeGrammar(provider).execute(
        GrammarAnalysisRequest(text, "ru", "b1")
    )
    assert [(item.text, item.role) for item in result.segments] == [("sing", "verb")]


async def test_annotations_allow_overlaps_and_keep_source_order():
    text = "If she had finished, she would have called."
    provider = Provider(
        GrammarAnalysisDraft(
            annotations=(
                GrammarAnnotationDraft(
                    "would have called", "mood_modality", "conditional perfect"
                ),
                GrammarAnnotationDraft(
                    "If she had finished", "clause_link", "third conditional"
                ),
                GrammarAnnotationDraft("had finished", "tense_aspect", "past perfect"),
            )
        )
    )
    result = await AnalyzeGrammar(provider).execute(
        GrammarAnalysisRequest(text, "ru", "b1")
    )
    assert [item.text for item in result.annotations] == [
        "If she had finished",
        "had finished",
        "would have called",
    ]


async def test_annotations_drop_unknown_missing_and_duplicates():
    text = "The report was written yesterday."
    provider = Provider(
        GrammarAnalysisDraft(
            annotations=(
                GrammarAnnotationDraft(
                    "was written", "voice", "passive", "focus on result"
                ),
                GrammarAnnotationDraft("was written", "voice", "passive"),
                GrammarAnnotationDraft("missing", "voice", "passive"),
                GrammarAnnotationDraft("yesterday", "invented", "unknown"),
            )
        )
    )
    result = await AnalyzeGrammar(provider).execute(
        GrammarAnalysisRequest(text, "ru", "b1")
    )
    assert len(result.annotations) == 1
    assert result.annotations[0].explanation == "focus on result"


async def test_blank_text_skips_provider():
    provider = Provider(GrammarAnalysisDraft())
    result = await AnalyzeGrammar(provider).execute(
        GrammarAnalysisRequest("  ", "ru", "b1")
    )
    assert result.annotations == ()
    assert provider.requests == []
