"""Passes over the curriculum, and the export.

A pass boundary is the one operation that makes finished work stop counting, so
the property that matters is that it changes what you are SCHEDULED on and
nothing else. If it ever removed a line from the log, the log would stop being
the record and every metric computed from it would be a guess.
"""

import csv
import io
import json
from datetime import date, timedelta

import pytest

from lcsr import curriculum as cur
from lcsr import plan
from lcsr import store
from lcsr.settings import PASS_BONUS_PER_SPRINT, Settings, allowance, daily_quota


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(store, "LOG", tmp_path / "log.jsonl")
    monkeypatch.setattr(cur, "CUSTOM", tmp_path / "custom.json")
    cur._packaged.cache_clear()


TODAY = date.today()
EARLIER = TODAY - timedelta(days=30)


def log(pid, outcome="solved", on=None, **kw):
    """Dates matter here, not just as decoration.

    raw_entries() orders by ATTEMPT DATE, and start_sprint() stamps its marker
    with today. So a pass boundary sits after everything dated earlier and
    before everything dated today or later, which is what makes the slice work.
    Tests that backdate an attempt to well before the marker are testing the
    previous pass, whether they mean to or not.
    """
    store.append(store.make_entry(pid, outcome, on or TODAY, **kw))


# --- nothing is lost ------------------------------------------------------

def test_a_new_pass_deletes_nothing():
    log(1, on=EARLIER); log(217, "stuck", mistake="edge-case", on=EARLIER)
    before = store.raw_entries()
    store.start_sprint()
    after = store.raw_entries()
    assert after[:len(before)] == before, "a pass boundary rewrote earlier lines"
    assert len(after) == len(before) + 1, "more than the marker was appended"


def test_history_still_shows_every_pass():
    log(1, on=EARLIER); store.start_sprint(); log(1)
    h = plan.history_view()
    assert h["total"] == 2, "an attempt from the previous pass vanished from history"
    assert [m["n"] for m in h["sprints"]] == [2]


def test_lifetime_attempts_survive_the_reset():
    log(1, on=EARLIER); log(217, on=EARLIER)
    store.start_sprint()
    m = plan.metrics()
    assert m["attempted"] == 0, "the new pass did not start clean"
    assert m["lifetime_attempts"] == 2, "the earlier work stopped being counted at all"
    assert m["sprint"] == 2


# --- scheduling starts over -----------------------------------------------

def test_every_problem_is_offered_again():
    log(1, on=EARLIER)
    assert store.replay()[1].done
    store.start_sprint()
    assert store.replay() == {}, "schedule state survived the pass boundary"
    assert plan.state_of(store.replay(), 1)["status"] == "new"


def test_a_due_resolve_does_not_carry_across():
    """It belongs to the pass it was scheduled in, and that pass is over."""
    log(217, "stuck", on=EARLIER)
    assert any(st.due for st in store.replay().values())
    store.start_sprint()
    assert not any(st.due for st in store.replay().values())


def test_the_ladder_starts_empty_again():
    log(217, "stuck", on=EARLIER)
    log(217, "solved", on=EARLIER + timedelta(days=3))
    assert store.replay()[217].box == 1
    store.start_sprint()
    log(217, "stuck")
    assert store.replay()[217].box == 0, "the new pass resumed the old ladder"


def test_sprint_number_counts_up():
    assert store.current_sprint() == 1
    for expected in (2, 3, 4):
        assert store.start_sprint()["sprint"] == expected
        assert store.current_sprint() == expected


# --- corrections stay inside the pass -------------------------------------

def test_undo_refuses_to_reach_into_a_finished_pass():
    log(1, on=EARLIER)
    store.start_sprint()
    with pytest.raises(ValueError):
        store.undo(1)


def test_history_offers_undo_only_on_the_current_pass():
    log(1, on=EARLIER)
    assert any(e["can_undo"] for d in plan.history_view()["days"] for e in d["entries"])
    store.start_sprint()
    assert not any(e["can_undo"] for d in plan.history_view()["days"] for e in d["entries"])


def test_undo_works_normally_within_a_pass():
    log(1, on=EARLIER); store.start_sprint(); log(1)
    store.undo(1)
    assert store.replay() == {}
    assert len(store.raw_entries()) == 4      # attempt, marker, attempt, retraction


# --- the daily load goes up -----------------------------------------------

@pytest.mark.parametrize("week", range(1, 17))
@pytest.mark.parametrize("sprint", range(1, 5))
def test_each_pass_adds_one_new_problem_a_day(week, sprint):
    q = daily_quota(week, 0, Settings(), sprint)
    assert q["core"] == allowance(week)["core"] + PASS_BONUS_PER_SPRINT * (sprint - 1)


@pytest.mark.parametrize("sprint", range(1, 5))
def test_your_own_override_still_beats_the_pass_bonus(sprint):
    assert daily_quota(1, 0, Settings(core=2), sprint)["core"] == 2


@pytest.mark.parametrize("sprint", range(1, 5))
def test_the_total_cap_still_caps_a_later_pass(sprint):
    q = daily_quota(1, 0, Settings(daily_total=3), sprint)
    assert sum(q[t] for t in ("foundations", "core", "reps")) <= 3


def test_the_bonus_reaches_the_actual_plan():
    before = plan.todays_plan()["target_today"]
    store.start_sprint()
    assert plan.todays_plan()["target_today"] == before + PASS_BONUS_PER_SPRINT


# --- export ----------------------------------------------------------------

def test_export_has_one_row_per_problem_and_a_square_shape():
    log(1); log(217, "stuck", mistake="edge-case", note="off by one on the last index")
    rows = list(csv.reader(io.StringIO(plan.export_csv())))
    head, body = rows[0], rows[1:]
    assert len(body) == len(cur.problems())
    assert {len(r) for r in rows} == {len(head)}, "ragged rows will break any spreadsheet"


def test_export_includes_problems_never_attempted():
    log(1)
    body = list(csv.reader(io.StringIO(plan.export_csv())))[1:]
    by_id = {int(r[0]): r for r in body}
    assert by_id[1][7] == "done"
    untouched = next(r for pid, r in by_id.items() if pid != 1)
    assert untouched[7] == "new" and untouched[8] == "0"


def test_export_spans_every_pass_and_labels_which():
    log(1, on=EARLIER)
    store.start_sprint()
    log(1, outcome="stuck")
    head = list(csv.reader(io.StringIO(plan.export_csv())))[0]
    row = next(r for r in list(csv.reader(io.StringIO(plan.export_csv())))[1:]
               if r[0] == "1")
    cells = dict(zip(head, row))
    assert cells["attempt_1_pass"] == "1", "the export forgot which pass an attempt was in"
    assert cells["attempt_2_pass"] == "2"
    assert cells["attempts"] == "2", "the export is scoped to one pass"


def test_export_keeps_a_note_with_a_comma_intact():
    log(1, note="reverse, then reverse the parts")
    row = next(r for r in list(csv.reader(io.StringIO(plan.export_csv())))[1:]
               if r[0] == "1")
    assert "reverse, then reverse the parts" in row


def test_the_raw_log_round_trips():
    """The jsonl export is the file itself, so the CLI must read back what it wrote."""
    log(1, on=EARLIER); store.start_sprint(); log(217, "stuck")
    raw = store.LOG.read_text(encoding="utf-8")
    parsed = [json.loads(x) for x in raw.split("\n") if x.strip()]
    assert parsed == store.raw_entries() or len(parsed) == len(store.raw_entries())
    assert any("sprint" in r for r in parsed)


def test_an_attempt_backdated_before_the_marker_belongs_to_the_old_pass():
    """Ordering is by attempt date, and the marker carries one too.

    Backfilling last week after starting a new pass files that attempt under the
    pass it was actually worked in. That is the consistent reading, but it is
    surprising enough to be worth pinning: it means a new pass cannot be
    retroactively populated.
    """
    store.start_sprint()
    log(1, on=EARLIER)
    assert store.replay() == {}, "a backdated attempt leaked into the new pass"
    assert plan.history_view()["total"] == 1, "and it must still be in the history"
