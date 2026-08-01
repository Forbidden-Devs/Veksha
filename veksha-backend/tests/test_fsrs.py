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
from dataclasses import replace

# Isolated runtime-file directory; the PostgreSQL test URL comes from conftest.
os.environ["VEKSHA_DATA_DIR"] = tempfile.mkdtemp(prefix="veksha-test-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
import fsrs  # noqa: E402
from models import Patch  # noqa: E402
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
    item = u.find_lexical_item_by_term("hazelnut")
    assert item.schedule.stability == 0.0 and item.schedule.review_count == 0
    assert item.schedule.added_at > 0

    item = u.apply_review_result(item, "correct", task_type="translation")
    assert item.schedule.stability > 0 and item.schedule.review_count == 1
    assert item.schedule.next_review_at > time.time()

    # Five days pass, then an incorrect answer.
    item = replace(
        item,
        schedule=replace(
            item.schedule,
            last_review_at=item.schedule.last_review_at - 5 * 86400,
            next_review_at=item.schedule.next_review_at - 5 * 86400,
        ),
    )
    u.replace_lexical_item(item)
    item = u.apply_review_result(item, "incorrect", task_type="translation")
    assert item.schedule.lapses == 1

    # Garbage outcome is not a review.
    item = u.apply_review_result(item, "garbage")
    assert item.schedule.review_count == 2

    rows = db.review_log_recent(USER)
    assert len(rows) == 2
    assert rows[0]["outcome"] == "incorrect" and rows[0]["rating"] == fsrs.AGAIN
    assert rows[1]["retrievability"] is None          # first review
    assert 0 < rows[0]["retrievability"] < 1          # second review
    assert abs(rows[0]["elapsed_days"] - 5) < 0.1
    assert len(db.review_log_recent(USER, word="hazelnut")) == 2
    assert len(db.review_log_recent(USER, lexical_item_id=item.item_id)) == 2

    # Overdue words stay due and only get flagged delayed.
    item = replace(
        item,
        schedule=replace(
            item.schedule, next_review_at=time.time() - 10 * 86400
        ),
    )
    u.replace_lexical_item(item)
    assert u.due_count() == 1
    flagged = u.apply_overdue_decay()
    assert flagged[0].schedule.delayed and len(flagged) == 1


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
