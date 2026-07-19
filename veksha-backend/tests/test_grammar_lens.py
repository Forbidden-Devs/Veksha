"""Grammar Lens response sanitising tests (no network calls)."""
import os
import sys
import tempfile

os.environ["VEKSHA_DATA_DIR"] = tempfile.mkdtemp(prefix="veksha-test-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm.grammar_lens import _normalise_annotations, _normalise_segments  # noqa: E402


def test_segments_keep_exact_source_order_and_valid_roles():
    text = "The cat sat on the mat yesterday."
    result = _normalise_segments(text, [
        {"text": "The cat", "role": "subject", "explanation": "who"},
        {"text": "sat", "role": "verb", "explanation": "action"},
        {"text": "on the mat", "role": "place", "explanation": "where"},
        {"text": "yesterday", "role": "time", "explanation": "when"},
    ])
    assert [item["role"] for item in result] == ["subject", "verb", "place", "time"]


def test_segments_drop_unknown_missing_and_out_of_order_spans():
    text = "Birds sing and children listen."
    result = _normalise_segments(text, [
        {"text": "sing", "role": "verb"},
        {"text": "Birds", "role": "subject"},  # behind cursor
        {"text": "missing", "role": "object"},
        {"text": "children", "role": "invented"},
    ])
    assert result == [{"text": "sing", "role": "verb", "explanation": ""}]


def test_annotations_allow_overlaps_and_keep_source_order():
    text = "If she had finished, she would have called."
    result = _normalise_annotations(text, [
        {"text": "would have called", "category": "mood_modality", "label": "conditional perfect"},
        {"text": "If she had finished", "category": "clause_link", "label": "third conditional"},
        {"text": "had finished", "category": "tense_aspect", "label": "past perfect"},
    ])
    assert [item["text"] for item in result] == [
        "If she had finished", "had finished", "would have called",
    ]


def test_annotations_drop_unknown_missing_and_duplicates():
    text = "The report was written yesterday."
    result = _normalise_annotations(text, [
        {"text": "was written", "category": "voice", "label": "passive", "explanation": "focus on result"},
        {"text": "was written", "category": "voice", "label": "passive"},
        {"text": "missing", "category": "voice", "label": "passive"},
        {"text": "yesterday", "category": "invented", "label": "unknown"},
    ])
    assert result == [{
        "text": "was written", "category": "voice", "label": "passive", "explanation": "focus on result",
    }]


if __name__ == "__main__":
    test_segments_keep_exact_source_order_and_valid_roles()
    test_segments_drop_unknown_missing_and_out_of_order_spans()
    test_annotations_allow_overlaps_and_keep_source_order()
    test_annotations_drop_unknown_missing_and_duplicates()
    print("PASS Grammar Lens segment validation")
