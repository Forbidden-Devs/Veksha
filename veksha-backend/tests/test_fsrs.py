"""
FSRS scheduler + review-log integration tests.

Run either way (no test framework required):
    python tests/test_fsrs.py
    pytest tests/
"""
import os
import sys
import tempfile
import time

# Isolated runtime-file directory; the PostgreSQL test URL comes from conftest.
os.environ["VEKSHA_DATA_DIR"] = tempfile.mkdtemp(prefix="veksha-test-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
import fsrs  # noqa: E402
from models import Patch, Word  # noqa: E402
from storage import UserStorage  # noqa: E402

USER = "fsrs_test_user"


def test_init_state_matches_published_weights():
    s = fsrs.init_state(fsrs.GOOD)
    assert abs(s.stability - 3.7145) < 1e-6
    assert 1 <= s.difficulty <= 10


def test_interval_at_default_retention_equals_stability():
    assert abs(fsrs.interval_days(10, 0.9) - 10) < 1e-9


def test_intervals_grow_on_good_and_shrink_on_again():
    st = fsrs.init_state(fsrs.GOOD)
    stabilities = []
    for _ in range(5):
        st = fsrs.review(st, fsrs.GOOD, fsrs.interval_days(st.stability, 0.9))
        stabilities.append(st.stability)
    assert all(b > a for a, b in zip(stabilities, stabilities[1:]))

    lapsed = fsrs.review(st, fsrs.AGAIN, fsrs.interval_days(st.stability, 0.9))
    assert lapsed.stability < st.stability
    assert lapsed.difficulty > st.difficulty


def test_hard_grows_less_than_good():
    base = fsrs.init_state(fsrs.GOOD)
    hard = fsrs.review(base, fsrs.HARD, 3.7)
    good = fsrs.review(base, fsrs.GOOD, 3.7)
    assert hard.stability < good.stability


def test_retrievability():
    assert abs(fsrs.retrievability(3.7145, 3.7145) - 0.9) < 1e-9
    assert fsrs.retrievability(30, 3.7145) < 0.7


def test_review_flow_and_log():
    db.create_user(USER)
    u = UserStorage(username=USER)
    u.apply_kb_changes([Patch(type="add_word", value="hazelnut", counter=0, known=False)])
    w = u.find_word("hazelnut")
    assert w.stability == 0.0 and w.counter == 0
    assert w.added_at > 0

    u.apply_review_result(w, "correct", task_type="translation")
    assert w.stability > 0 and w.counter == 1
    assert w.next_review > time.time()

    # Five days pass, then an incorrect answer.
    w.last_review -= 5 * 86400
    w.next_review -= 5 * 86400
    u.apply_review_result(w, "incorrect", task_type="translation")
    assert w.lapses == 1

    # Garbage outcome is not a review.
    u.apply_review_result(w, "garbage")
    assert w.counter == 2

    rows = db.review_log_recent(USER)
    assert len(rows) == 2
    assert rows[0]["outcome"] == "incorrect" and rows[0]["rating"] == fsrs.AGAIN
    assert rows[1]["retrievability"] is None          # first review
    assert 0 < rows[0]["retrievability"] < 1          # second review
    assert abs(rows[0]["elapsed_days"] - 5) < 0.1
    assert len(db.review_log_recent(USER, word="hazelnut")) == 2

    # Overdue words stay due and only get flagged delayed.
    w.next_review = time.time() - 10 * 86400
    assert u.due_count() == 1
    flagged = u.apply_overdue_decay()
    assert w.delayed and len(flagged) == 1

    # Word (de)serialization keeps the FSRS fields.
    w2 = Word.from_dict(w.to_dict())
    assert (w2.stability, w2.lapses, w2.last_review) == (w.stability, w.lapses, w.last_review)
    assert w2.added_at == w.added_at


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted({k: v for k, v in globals().items() if k.startswith("test_")}.items()):
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError:
            failed += 1
            import traceback
            print(f"FAIL {name}")
            traceback.print_exc()
    sys.exit(1 if failed else 0)
