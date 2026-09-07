"""The +3/+10/+30 ladder, checked over whole SEQUENCES rather than single steps.

test_schedule.py pins advance() one transition at a time. That is necessary and
not sufficient: the behaviour a user actually experiences is the composition of
those transitions through replay(), carrying a date each time. A single-step
table can be perfectly right while the fold over it is wrong.

So this file states the rule a second, independent way -- as "consecutive solves
since the last failure" rather than as a box number -- and asserts the two agree
for every outcome sequence up to length 8 (510 of them). If either formulation is
edited into disagreement with the other, this fails.
"""

from datetime import date, timedelta
from itertools import product

import pytest

from lcsr import curriculum as cur
from lcsr import store
from lcsr.store import append, make_entry, replay

START = date(2026, 9, 1)

# The ladder, restated: once a problem has failed, it takes three consecutive
# cold solves to clear, at 3, 10 and 30 days. Any failure resets the streak.
INTERVALS = [3, 10, 30]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(store, "LOG", tmp_path / "log.jsonl")
    monkeypatch.setattr(cur, "CUSTOM", tmp_path / "custom.json")
    cur._packaged.cache_clear()


def reference(seq):
    """Independent model: track the solve streak, not a box index.

    Returns (done, due_in_days) after the final attempt, or (True, None) once the
    problem has cleared. A problem that has cleared is fresh again, so a later
    failure re-enters the ladder at the bottom -- which is what re-opening with
    --again does.
    """
    entered = False          # has this problem ever failed?
    streak = 0               # consecutive solves since the last failure
    done = False
    due = None
    for outcome in seq:
        if outcome == "stuck":
            entered, streak, done = True, 0, False
            due = INTERVALS[0]
        elif not entered:
            done, due = True, None          # solved cold, first try
        else:
            streak += 1
            if streak >= len(INTERVALS):
                entered, streak, done, due = False, 0, True, None
            else:
                done, due = False, INTERVALS[streak]
    return done, due


def sequences(max_len=8):
    for n in range(1, max_len + 1):
        yield from product(("solved", "stuck"), repeat=n)


def seq_id(seq):
    # "solved" and "stuck" both start with s, so spell them apart
    return "".join("S" if o == "solved" else "x" for o in seq)


@pytest.mark.parametrize("seq", list(sequences(8)), ids=seq_id)
def test_ladder_matches_an_independent_model(seq):
    """Every outcome sequence up to length 8, each attempt made exactly on time."""
    day = START
    last = START
    for outcome in seq:
        append(make_entry(1, outcome, day))
        last = day                           # the day THIS attempt was made
        st = replay()[1]
        if st.due:
            day = st.due                     # the next one happens when due
    st = replay()[1]
    want_done, want_due = reference(seq)
    assert st.done == want_done, f"{seq_id(seq)}: done"
    if want_due is None:
        assert st.due is None, f"{seq_id(seq)}: expected no re-solve"
    else:
        assert st.due == last + timedelta(days=want_due), f"{seq_id(seq)}: interval"


def test_three_consecutive_solves_are_required_to_clear():
    """The headline property: one lucky re-solve does not retire a problem."""
    for n, expect_done in ((1, False), (2, False), (3, True)):
        store.LOG.unlink(missing_ok=True)
        day = START
        append(make_entry(1, "stuck", day))
        for _ in range(n):
            day = replay()[1].due
            append(make_entry(1, "solved", day))
        assert replay()[1].done is expect_done, f"{n} solves after a failure"


def test_any_failure_resets_to_the_bottom():
    """Failing at the +30 step goes back to +3, not back to +10."""
    day = START
    last = START
    for outcome in ("stuck", "solved", "solved"):
        append(make_entry(1, outcome, day))
        last, day = day, replay()[1].due
    assert replay()[1].box == 2
    assert day == last + timedelta(days=30)    # sitting at the +30 step
    append(make_entry(1, "stuck", day))
    st = replay()[1]
    assert st.box == 0 and st.due == day + timedelta(days=3)


def test_repeated_failures_never_lengthen_the_interval():
    """stuck -> stuck -> stuck ... must stay at +3 forever, never drift outward."""
    day = START
    for _ in range(12):
        append(make_entry(1, "stuck", day))
        st = replay()[1]
        assert st.box == 0
        assert st.due == day + timedelta(days=3)
        day = st.due


def test_interval_counts_from_the_attempt_not_from_the_due_date():
    """A re-solve done late must schedule from when you actually did it.

    Otherwise a problem left for a fortnight would come due again immediately,
    stacking a backlog on top of a backlog.
    """
    append(make_entry(1, "stuck", START))
    assert replay()[1].due == START + timedelta(days=3)
    late = START + timedelta(days=20)          # 17 days overdue
    append(make_entry(1, "solved", late))
    assert replay()[1].due == late + timedelta(days=10)


def test_clearing_then_reopening_starts_the_ladder_over():
    """--again on a cleared problem must not resume at +30."""
    day = START
    for outcome in ("stuck", "solved", "solved", "solved"):
        append(make_entry(1, outcome, day))
        st = replay()[1]
        day = st.due or day + timedelta(days=1)
    assert replay()[1].done
    append(make_entry(1, "stuck", day))
    st = replay()[1]
    assert st.box == 0 and st.due == day + timedelta(days=3)


def test_undo_rewinds_one_rung_exactly():
    day = START
    append(make_entry(1, "stuck", day))
    day = replay()[1].due
    append(make_entry(1, "solved", day))
    assert replay()[1].box == 1
    store.undo(1)
    st = replay()[1]
    assert st.box == 0 and st.due == START + timedelta(days=3)


def test_amend_recomputes_the_rung_from_the_original_date():
    """Correcting solved -> stuck must reschedule from the attempt's own date."""
    append(make_entry(1, "stuck", START))
    day = replay()[1].due
    append(make_entry(1, "solved", day))
    assert replay()[1].due == day + timedelta(days=10)
    store.amend(1, "stuck")
    st = replay()[1]
    assert st.box == 0
    assert st.due == day + timedelta(days=3), "rescheduled from today instead of the attempt"
