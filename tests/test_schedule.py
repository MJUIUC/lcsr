"""Exhaustive truth table for advance(). All 8 reachable (box, outcome) pairs.

Written out as literal expected values rather than recomputed from LADDER, so a
typo in LADDER fails the test instead of propagating into it.
"""
import pytest

from lcsr.schedule import EDITORIAL, LADDER, NOTE, SOLVED, STUCK, Next, advance

# (box, outcome) -> (done, box, due_in_days)
TABLE = {
    (None, SOLVED): (True, None, None),   # solved cold first try -> never returns
    (None, STUCK): (False, 0, 3),         # first failure enters the ladder
    (0, SOLVED): (False, 1, 10),
    (0, STUCK): (False, 0, 3),
    (1, SOLVED): (False, 2, 30),
    (1, STUCK): (False, 0, 3),            # failing resets, does not resume
    (2, SOLVED): (True, None, None),      # cleared +3/+10/+30
    (2, STUCK): (False, 0, 3),
    # editorial: same box, same done, no due date change
    (None, EDITORIAL): (True, None, None),
    (0, EDITORIAL): (False, 0, None),
    (1, EDITORIAL): (False, 1, None),
    (2, EDITORIAL): (False, 2, None),
    # note: same as editorial, no scheduling effect
    (None, NOTE): (True, None, None),
    (0, NOTE): (False, 0, None),
    (1, NOTE): (False, 1, None),
    (2, NOTE): (False, 2, None),
}


@pytest.mark.parametrize(("key", "expected"), sorted(TABLE.items(), key=repr))
def test_truth_table(key, expected):
    box, outcome = key
    assert advance(box, outcome) == Next(*expected)


def test_table_is_exhaustive():
    boxes = [None, *LADDER]
    from lcsr.schedule import OUTCOMES
    assert set(TABLE) == {(b, o) for b in boxes for o in OUTCOMES}


def test_failure_always_resets_to_bottom():
    for box in [None, *LADDER]:
        assert advance(box, STUCK) == Next(False, 0, 3)


def test_rejects_unknown_outcome():
    with pytest.raises(ValueError, match="unknown outcome"):
        advance(0, "partial")
