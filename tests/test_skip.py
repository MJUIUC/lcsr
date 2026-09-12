"""Setting a problem aside.

The whole risk here is that "I am not doing this one" leaks into the record of
what you did. A skip that counted as an attempt would quietly improve the cold
re-solve rate by letting you decline the hard ones, and that is the single
number the curriculum says predicts anything.
"""

from datetime import date, timedelta

import pytest

from lcsr import curriculum as cur
from lcsr import plan
from lcsr import store

TODAY = date.today()
HARD = 42          # Trapping Rain Water, week 1 core, hard


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(store, "LOG", tmp_path / "log.jsonl")
    monkeypatch.setattr(cur, "CUSTOM", tmp_path / "custom.json")
    cur._packaged.cache_clear()


def ids(sections):
    return [p["id"] for s in sections for p in s["problems"]]


# --- a skip is not an attempt ---------------------------------------------

def test_a_skip_never_becomes_an_attempt():
    store.set_skipped(HARD)
    assert store.entries() == [], "a skip reached the attempt log"
    assert store.replay() == {}, "a skip reached the schedule state"
    assert plan.metrics()["attempted"] == 0


def test_a_skip_cannot_flatter_the_cold_resolve_rate():
    """Decline every failure and the rate must not move."""
    store.append(store.make_entry(1, "stuck", TODAY - timedelta(days=3)))
    store.append(store.make_entry(1, "solved", TODAY))
    before = plan.metrics()["resolve_rate"]
    for pid in (42, 76, 4):
        store.set_skipped(pid)
    assert plan.metrics()["resolve_rate"] == before
    assert plan.metrics()["mistakes"] == {}


def test_skips_do_not_show_up_as_history():
    store.set_skipped(HARD)
    assert plan.history_view()["total"] == 0


# --- it comes off the queue, and comes back -------------------------------

def test_a_skipped_problem_stops_being_offered():
    before = ids(plan.todays_plan()["sections"])
    assert before, "nothing offered, test is vacuous"
    target = before[0]
    store.set_skipped(target)
    assert target not in ids(plan.todays_plan()["sections"])


def test_bringing_it_back_puts_it_on_the_queue_again():
    target = ids(plan.todays_plan()["sections"])[0]
    store.set_skipped(target)
    store.set_skipped(target, False)
    assert target in ids(plan.todays_plan()["sections"])
    assert store.skipped_ids() == set()


def test_a_skipped_problem_that_is_due_stops_being_due():
    store.append(store.make_entry(HARD, "stuck", TODAY - timedelta(days=4)))
    assert any(d["id"] == HARD for d in plan.todays_plan()["due"])
    store.set_skipped(HARD)
    assert not any(d["id"] == HARD for d in plan.todays_plan()["due"])


def test_set_aside_problems_get_their_own_curriculum_tier():
    store.set_skipped(HARD)
    groups = {g["key"]: g for g in plan.curriculum_view()["groups"]}
    assert "skipped" in groups, "no Tier 4 group"
    rows = [p for b in groups["skipped"]["blocks"] for p in b["problems"]]
    assert [p["id"] for p in rows] == [HARD]
    assert rows[0]["title"] and rows[0]["hard"] is True


def test_the_tier_disappears_when_nothing_is_set_aside():
    keys = {g["key"] for g in plan.curriculum_view()["groups"]}
    assert "skipped" not in keys


def test_a_set_aside_problem_stays_listed_in_its_own_week():
    """Removing it would shrink that week's totals, and the curriculum's counts
    are the one thing this tool does not rewrite."""
    before = {g["key"]: g["progress"]["total"] for g in plan.curriculum_view()["groups"]}
    store.set_skipped(HARD)
    after = {g["key"]: g["progress"]["total"] for g in plan.curriculum_view()["groups"]}
    for key, total in before.items():
        assert after[key] == total, key
    week = next(g for g in plan.curriculum_view()["groups"] if g["key"] == "week-1")
    row = next(p for b in week["blocks"] for p in b["problems"] if p["id"] == HARD)
    assert row["state"]["skipped"] is True, "the week does not mark it set aside"


def test_the_plan_still_reports_how_many_are_set_aside():
    store.set_skipped(HARD)
    assert plan.todays_plan()["skipped_count"] == 1


# --- it must not stall the schedule ---------------------------------------

def test_skipping_a_core_problem_does_not_freeze_the_week():
    """intake_week() is the next unattempted core problem. Without counting
    skips it would pin to the declined one and the mix would never advance."""
    core = sorted((p for p in cur.problems().values() if p["tier"] == "core"),
                  key=lambda p: p["order"])
    first = core[0]["id"]
    start = plan.intake_week(set(), set())
    for p in core:
        if p["week"] == core[0]["week"]:
            store.set_skipped(p["id"])
    assert plan.intake_week(set(), store.skipped_ids()) > start
    assert first in store.skipped_ids()


def test_the_projection_does_not_promise_work_you_declined():
    store.append(store.make_entry(1, "solved", TODAY))
    before = plan.todays_plan()["projection"]["remaining"]
    for pid in (42, 76, 4):
        store.set_skipped(pid)
    assert plan.todays_plan()["projection"]["remaining"] == before - 3


# --- passes ----------------------------------------------------------------

def test_a_new_pass_offers_the_skipped_ones_again():
    """A pass puts everything back on offer, and that has to include what you
    declined last time round."""
    store.set_skipped(HARD)
    assert store.skipped_ids() == {HARD}
    store.start_sprint()
    assert store.skipped_ids() == set()


def test_the_log_keeps_both_sides_of_a_change_of_mind():
    store.set_skipped(HARD)
    store.set_skipped(HARD, False)
    marks = [r for r in store.raw_entries() if "skip" in r]
    assert [m["skip"] for m in marks] == [True, False]
    assert store.skipped_ids() == set()


# --- skipping must never hand you more work -------------------------------

def worked_queue():
    """Solve everything today offers except the last item; return that item."""
    todo = ids(plan.todays_plan()["sections"])
    for pid in todo[:-1]:
        store.append(store.make_entry(pid, "solved", TODAY))
    return todo[-1]


def test_skipping_the_last_problem_of_the_day_conjures_nothing():
    """The reported bug: setting aside the final item produced a week-3 core and
    a rep out of nowhere, because the skip advanced the week mid-day (week 3 is
    where reps begin) and the freed slot refilled from the new week."""
    last = worked_queue()
    store.set_skipped(last)
    assert ids(plan.todays_plan()["sections"]) == [], "the skip handed out more work"


def test_a_skip_consumes_the_slot_it_vacated():
    """Otherwise the queue refills and skipping is punished with a replacement."""
    before = plan.todays_plan()
    target = ids(before["sections"])[0]
    store.set_skipped(target)
    after = plan.todays_plan()
    assert after["done_today"] == before["done_today"] + 1
    assert len(ids(after["sections"])) == len(ids(before["sections"])) - 1


def test_todays_skip_does_not_move_the_week_until_tomorrow():
    core = sorted((p for p in cur.problems().values() if p["tier"] == "core"),
                  key=lambda p: p["order"])
    wk = plan.todays_plan()["week"]
    for p in core:
        if p["week"] == wk:
            store.set_skipped(p["id"])
    assert plan.todays_plan()["week"] == wk, "the week jumped on the day of the skip"
    # Dated yesterday, the same skips do advance it.
    assert plan.intake_week(set(), store.skipped_ids()) > wk


def test_a_skip_never_adds_a_tier_that_was_not_being_issued():
    """Week 1 and 2 issue no reps. A skip must not tip the week into 3 and start
    them, which is exactly how the phantom rep appeared."""
    p = plan.todays_plan()
    if p["week"] > 2:
        pytest.skip("only meaningful before reps begin")
    reps_before = [s for s in p["sections"] if "Rep" in s["title"]]
    assert not reps_before
    store.set_skipped(worked_queue())
    assert not [s for s in plan.todays_plan()["sections"] if "Rep" in s["title"]]
