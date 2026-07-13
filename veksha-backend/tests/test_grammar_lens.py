"""Grammar Lens response sanitising tests (no network calls)."""
import os
import sys
import tempfile

os.environ["VEKSHA_DATA_DIR"] = tempfile.mkdtemp(prefix="veksha-test-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm.grammar_lens import _normalise_segments  # noqa: E402


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


if __name__ == "__main__":
    test_segments_keep_exact_source_order_and_valid_roles()
    test_segments_drop_unknown_missing_and_out_of_order_spans()
    print("PASS Grammar Lens segment validation")
