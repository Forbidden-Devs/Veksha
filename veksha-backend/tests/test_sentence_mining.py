"""Sentence Mining response sanitising tests (no network calls)."""
import os
import sys
import tempfile

os.environ["VEKSHA_DATA_DIR"] = tempfile.mkdtemp(prefix="veksha-test-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm.sentence_mining import _normalise_card  # noqa: E402


def test_normalise_card_limits_and_marks_higher_examples():
    card = _normalise_card({
        "examples": [
            {"sentence": "I make coffee.", "translation": "Я готовлю кофе.", "level": "A2"},
            {"sentence": "We made a decision.", "translation": "Мы приняли решение.", "level": "B1"},
            {"sentence": "Ignored.", "translation": "", "level": "C2"},
        ],
        "mnemonic": "A useful memory",
        "collocations": [{"text": "make a decision", "translation": "принять решение"}],
    }, "A2", "B1", 1, 1)
    assert len(card["examples"]) == 2
    assert card["examples"][0]["is_higher"] is False
    assert card["examples"][1]["is_higher"] is True
    assert card["collocations"][0]["text"] == "make a decision"


if __name__ == "__main__":
    test_normalise_card_limits_and_marks_higher_examples()
    print("PASS Sentence Mining response validation")
