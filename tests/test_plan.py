"""Today's queue must respect what was already done today.

The original bug: the queue filtered only on "never attempted", so logging the
day's problems immediately served the next batch and the list never emptied.
"""

from datetime import date, timedelta

import pytest

from lcsr import curriculum as cur
from lcsr import store
from lcsr.plan import allowance, todays_plan
from lcsr.store import append, make_entry

TODAY = date.today()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(store, "LOG", tmp_path / "log.jsonl")
    monkeypatch.setattr(cur, "CUSTOM", tmp_path / "custom.json")
    cur._packaged.cache_clear()


def log(pid, outcome="solved", on=None):
    append(make_entry(pid, outcome, on or TODAY))


def ids(sections):
    return [p["id"] for s in sections for p in s["problems"]]


def test_empty_log_offers_the_first_day():
    p = todays_plan()
    assert p["done_today"] == 0 and not p["caught_up"]
    assert p["target_today"] == 5           # week 1: 3 foundations + 2 core
    assert len(ids(p["sections"])) == 5


def test_queue_shrinks_as_the_day_is_logged():
    before = len(ids(todays_plan()["sections"]))
    log(1)
    after = len(ids(todays_plan()["sections"]))
    assert after == before - 1


def test_meeting_the_target_empties_the_queue():
    for pid in (1, 217, 242, 643, 1456):     # 3 foundations + 2 core
        log(pid)
    p = todays_plan()
    assert p["done_today"] == 5
    assert p["caught_up"] and p["sections"] == []


def test_work_ahead_is_offered_but_separate():
    for pid in (1, 217, 242, 643, 1456):
        log(pid)
    p = todays_plan()
    assert p["sections"] == []               # not mixed into today
    assert ids(p["ahead"])                   # but available on request


def test_yesterdays_work_does_not_count_toward_today():
    for pid in (1, 217, 242, 643, 1456):
        log(pid, on=TODAY - timedelta(days=1))
    p = todays_plan()
    assert p["done_today"] == 0 and not p["caught_up"]
    assert len(ids(p["sections"])) == 5


def test_resolves_do_not_consume_the_new_problem_quota():
    """A due re-solve is mandatory and additional; it must not displace new work."""
    log(1, "stuck", TODAY - timedelta(days=3))
    log(1, "solved", TODAY)                  # the re-solve, today
    p = todays_plan()
    assert p["resolves_today"] == 1
    assert p["done_today"] == 0              # re-solve is not new intake
    assert len(ids(p["sections"])) == 5


def test_due_resolve_blocks_caught_up():
    log(1, "stuck", TODAY - timedelta(days=3))   # due today
    for pid in (217, 242, 49, 643, 1456):
        log(pid)
    p = todays_plan()
    assert p["due"] and not p["caught_up"]


def test_allowance_matches_the_documented_load():
    """PDF: ~4-5/day weeks 1-3, ~3/day weeks 4-11, ~3-4/day weeks 12-16."""
    def total(w):
        a = allowance(w)
        return sum(a.values()) - a["custom"]
    assert total(1) == 5 and total(2) == 5
    assert total(3) == 6
    assert all(total(w) == 3 for w in range(4, 12))
    assert all(total(w) == 4 for w in range(12, 17))


def test_reps_interleave_back_across_earlier_weeks():
    """Reps must not be massed into their own week -- week 1's reps have to stay
    reachable in week 5, or they are stranded forever."""
    log(1, on=TODAY - timedelta(days=29))    # puts us in week 5
    p = todays_plan()
    assert p["week"] == 5
    reps = [s for s in p["sections"] if s["title"].startswith("Reps")]
    assert reps, "no reps section in week 5"
    assert any(q["week"] < 5 for q in reps[0]["problems"]), "reps did not reach back"
