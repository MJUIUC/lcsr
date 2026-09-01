"""Edge cases around missed days: carry-forward, backlog caps, schedule drift.

The scenarios here are the ones the daily path never exercises -- they only
appear after you stop using the tool for a while, which is exactly when a
silently wrong queue does the most damage.
"""

from datetime import date, timedelta

import pytest

from lcsr import curriculum as cur
from lcsr import store
from lcsr.plan import (BACKLOG_PAUSE, MAX_DUE_SHOWN, allowance, intake_week,
                       todays_plan)
from lcsr.store import append, make_entry

TODAY = date.today()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(store, "LOG", tmp_path / "log.jsonl")
    monkeypatch.setattr(cur, "CUSTOM", tmp_path / "custom.json")
    cur._packaged.cache_clear()


def log(pid, outcome, on):
    append(make_entry(pid, outcome, on))


def core_ids(n):
    return [p["id"] for p in sorted(cur.problems().values(), key=lambda p: p["order"])
            if p["tier"] == "core"][:n]


def ids(sections):
    return [p["id"] for s in sections for p in s["problems"]]


# --- carry-forward ------------------------------------------------------

def test_a_missed_resolve_stays_due_and_ages():
    log(1, "stuck", TODAY - timedelta(days=10))     # was due 7 days ago
    p = todays_plan()
    assert [q["id"] for q in p["due"]] == [1]
    assert p["due"][0]["days_late"] == 7


def test_new_problems_do_not_stack_when_days_are_missed():
    """Missing three days must not produce a quadruple-size day: the intake is
    per-day, and a skipped day is skipped, not banked."""
    log(1, "solved", TODAY - timedelta(days=3))
    p = todays_plan()
    assert len(ids(p["sections"])) <= p["target_today"]


def test_most_overdue_comes_first():
    for i, pid in enumerate(core_ids(4)):
        log(pid, "stuck", TODAY - timedelta(days=20 - i))
    lateness = [q["days_late"] for q in todays_plan()["due"]]
    assert lateness == sorted(lateness, reverse=True)


# --- the backlog cap ----------------------------------------------------

def test_due_list_is_capped():
    for i, pid in enumerate(core_ids(30)):
        log(pid, "stuck", TODAY - timedelta(days=25) + timedelta(days=i // 5))
    p = todays_plan()
    assert p["backlog"] == 30
    assert len(p["due"]) == MAX_DUE_SHOWN
    assert p["due_hidden"] == 30 - MAX_DUE_SHOWN


def test_backlog_pauses_new_problems():
    for pid in core_ids(BACKLOG_PAUSE):
        log(pid, "stuck", TODAY - timedelta(days=5))
    p = todays_plan()
    assert p["paused"] is True
    assert p["sections"] == [] and p["ahead"] == []
    assert p["caught_up"] is False, "a paused day is not a finished day"


def test_below_the_threshold_nothing_is_paused():
    for pid in core_ids(BACKLOG_PAUSE - 1):
        log(pid, "stuck", TODAY - timedelta(days=5))
    p = todays_plan()
    assert p["paused"] is False and p["sections"]


def test_clearing_the_backlog_resumes_new_problems():
    stuck = core_ids(BACKLOG_PAUSE)
    for pid in stuck:
        log(pid, "stuck", TODAY - timedelta(days=5))
    assert todays_plan()["paused"]
    for pid in stuck[:3]:
        log(pid, "solved", TODAY)              # clear three
    p = todays_plan()
    assert p["paused"] is False and p["sections"]


# --- schedule drift -----------------------------------------------------

def test_falling_behind_does_not_skip_foundations():
    """The original bug: allowance() keyed off the CALENDAR week, so after five
    weeks away it returned foundations=0 and all 42 became unreachable forever."""
    for i, pid in enumerate(core_ids(4)):
        log(pid, "solved", TODAY - timedelta(days=40) + timedelta(days=i))
    p = todays_plan()
    assert p["week"] > p["intake_week"], "expected the calendar to be ahead"
    assert p["drift_weeks"] > 0
    assert allowance(p["intake_week"])["foundations"] > 0
    assert any("Found" in s["title"] for s in p["sections"])


def test_intake_week_tracks_progress_not_elapsed_time():
    assert intake_week(set()) == 1
    done = {p["id"] for p in cur.problems().values()
            if p["tier"] == "core" and p["week"] and p["week"] <= 3}
    assert intake_week(done) == 4


def test_running_ahead_reports_no_drift():
    for i, pid in enumerate(core_ids(9)):
        log(pid, "solved", TODAY)
    assert todays_plan()["drift_weeks"] <= 0


# --- malformed input ----------------------------------------------------

def test_corrupt_log_line_names_itself(tmp_path):
    store.LOG.write_text(
        '{"ts":"x","date":"2026-09-01","id":1,"outcome":"solved"}\n{bad}\n',
        encoding="utf-8")
    with pytest.raises(ValueError, match=r"log\.jsonl:2 is not valid JSON"):
        store.raw_entries()
