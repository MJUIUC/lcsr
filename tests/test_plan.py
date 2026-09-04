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
    reachable once you reach week 5, or they are stranded forever.

    Reaching week 5 means finishing weeks 1-4's core, not merely letting four
    weeks elapse: the daily mix follows progress rather than the calendar, so
    that falling behind slows the schedule instead of skipping material.
    """
    from lcsr import curriculum as c
    for q in c.problems().values():
        if q["tier"] == "core" and q["week"] and q["week"] <= 4:
            log(q["id"])
    p = todays_plan()
    assert p["week"] == 5
    reps = [s for s in p["sections"] if s["title"].startswith("Reps")]
    assert reps, "no reps section at week 5"
    assert any(q["week"] < 5 for q in reps[0]["problems"]), "reps did not reach back"


# --- future-day previews -------------------------------------------------
# Bug this guards: future days ignored the intake of the days in between, so
# every previewed day returned the same problems -- day+2 repeated day+1 forever.

def _preview(n):
    return todays_plan(TODAY + timedelta(days=n))


def test_consecutive_future_days_are_different():
    assert ids(_preview(1)["sections"]) != ids(_preview(2)["sections"])


def test_future_days_never_repeat_a_problem():
    seen = []
    for n in range(1, 8):
        seen += ids(_preview(n)["sections"])
    assert len(seen) == len(set(seen)), "a problem appears on two previewed days"


def test_future_days_continue_where_the_previous_left_off():
    """Day+2 must start after everything day+1 would consume."""
    first, second = ids(_preview(1)["sections"]), ids(_preview(2)["sections"])
    assert set(first).isdisjoint(second)


def test_tomorrow_is_stable_as_today_is_worked_through():
    """Tomorrow sits after today's FULL intake, so ticking today's problems off
    must not shift it -- the same total is consumed by end of day either way.
    Only overshooting today's target pulls tomorrow forward."""
    before = ids(_preview(1)["sections"])
    log(1)
    assert ids(_preview(1)["sections"]) == before
    log(217)
    assert ids(_preview(1)["sections"]) == before


def test_overshooting_today_pulls_tomorrow_forward():
    before = ids(_preview(1)["sections"])
    for pid in (1, 217, 242, 49, 128, 125):   # 6 foundations against a quota of 3
        log(pid)
    assert ids(_preview(1)["sections"]) != before


def test_future_day_shows_only_resolves_falling_due_that_day():
    log(1, "stuck", TODAY)       # due TODAY+3
    assert [q["id"] for q in _preview(3)["due"]] == [1]
    assert _preview(4)["due"] == [], "an earlier due date leaked forward"


def test_future_days_are_never_caught_up_and_offer_no_ahead():
    p = _preview(2)
    assert p["caught_up"] is False
    assert p["ahead"] == []


def test_core_flows_into_the_next_week_when_the_current_one_runs_out():
    """Week 1 has 7 core problems; at 2/day a fast start exhausts it, and the
    queue must continue in document order rather than going empty.

    The label just names the block it drew from. There is no "ahead of schedule"
    any more: week means progress, so it cannot disagree with progress.
    """
    for pid in (643, 1456, 1052, 167, 11, 15, 42):
        log(pid)
    core = [s for s in _preview(1)["sections"] if "ore" in s["title"]]
    assert core, "core section vanished once week 1 was exhausted"
    assert all(q["week"] > 1 for q in core[0]["problems"])
    assert "schedule" not in core[0]["title"]
