"""Regressions for defects found by the multi-agent audit.

Each test names the failure it prevents. These are the cases that were reachable
by ordinary use and silent when they went wrong.
"""

import json
import threading
from datetime import date, timedelta

import pytest

from lcsr import curriculum as cur
from lcsr import store
from lcsr.plan import foundations_left, intake_week, todays_plan
from lcsr.store import append, entries, make_entry, raw_entries, replay

TODAY = date.today()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(store, "LOG", tmp_path / "log.jsonl")
    monkeypatch.setattr(cur, "CUSTOM", tmp_path / "custom.json")
    cur._packaged.cache_clear()


# --- log integrity ------------------------------------------------------

@pytest.mark.parametrize("ch", [" ", " ", "", "\v", "\f", "\x1c"])
def test_line_separators_in_a_note_do_not_break_the_log(ch):
    """str.splitlines() breaks on all of these; append() only ever writes "\\n".

    A note pasted from Word (which emits U+2028 for a soft line break) was
    written as one record and read back as two unparseable halves, permanently
    bricking every read path -- and the error named a line number that was not
    the real boundary, so the suggested repair was misleading too.
    """
    append(make_entry(1, "solved", TODAY, note=f"monotonic{ch}stack"))
    rows = raw_entries()
    assert len(rows) == 1
    assert rows[0]["note"] == f"monotonic{ch}stack"
    assert replay()[1].done


def test_amend_preserves_fields_it_was_not_asked_to_change():
    append(make_entry(1, "stuck", TODAY, mistake="invariant",
                      approach_min=7.5, note="missed the reset"))
    store.amend(1, "stuck", mistake="edge-case")
    row = entries()[-1]
    assert row["mistake"] == "edge-case"      # changed
    assert row["approach_min"] == 7.5         # preserved
    assert row["note"] == "missed the reset"  # preserved


def test_ordering_uses_the_instant_not_the_timestamp_string():
    """ts carries a UTC offset, and comparing those as text puts a post-DST
    01:30+01:00 after 02:00+02:00 although it happened 30 minutes earlier. A
    retraction cancels whatever sorts last, so this made undo cancel the wrong
    record.

    Dated in the past on a real EU fall-back night: an undo is stamped with the
    current instant, so cancelling an attempt dated in the FUTURE would match
    nothing. That is unreachable in practice -- future-dated attempts are
    rejected at both the CLI and the API.
    """
    append({"ts": "2025-10-26T02:00:00+02:00", "date": "2025-10-26",
            "id": 1, "outcome": "stuck", "mistake": None,
            "approach_min": None, "note": "first"})
    append({"ts": "2025-10-26T01:30:00+01:00", "date": "2025-10-26",
            "id": 1, "outcome": "solved", "mistake": None,
            "approach_min": None, "note": "second"})
    assert [r["note"] for r in entries()] == ["first", "second"]
    store.undo(1)
    assert [r["note"] for r in entries()] == ["first"]   # cancelled the later one


# --- scheduling ---------------------------------------------------------

def test_core_progress_does_not_strand_foundations():
    """intake_week() is derived from CORE progress and allowance() zeroes
    foundations from week 4, so finishing weeks 1-3's core stranded all 42
    remaining foundations -- the calendar bug again, by another route."""
    done = {p["id"] for p in cur.problems().values()
            if p["tier"] == "core" and p["week"] and p["week"] <= 3}
    for pid in done:
        append(make_entry(pid, "solved", TODAY - timedelta(days=1)))
    assert intake_week(done) >= 4
    assert foundations_left(done) > 0
    plan = todays_plan()
    assert any("Found" in s["title"] for s in plan["sections"]), \
        "foundations became unreachable"


def test_reps_pool_is_not_starved_when_running_ahead():
    """The reps allowance and the reps pool must be scoped by the same week.

    They used to disagree -- the allowance came from progress and the pool from
    the calendar -- so anyone moving faster than 2 core/day got an allowance with
    nothing to draw from. Now there is only one week and it cannot disagree.
    """
    for p in cur.problems().values():
        if p["tier"] == "core" and p["week"] and p["week"] <= 5:
            append(make_entry(p["id"], "solved", TODAY))
    plan = todays_plan()
    assert plan["week"] >= 6            # progress, on day one
    reps = [s for s in plan["sections"] if s["title"].startswith("Reps")]
    assert reps and reps[0]["problems"]


def test_a_date_before_the_first_attempt_never_reports_day_zero():
    append(make_entry(1, "solved", TODAY))
    assert todays_plan(TODAY - timedelta(days=5))["day"] >= 1


# --- data ---------------------------------------------------------------

def test_urls_match_leetcodes_real_slugs():
    """The curriculum abbreviates titles ("Maximum Depth" for "Maximum Depth of
    Binary Tree"), so deriving a slug from the title produced 404s for 28 of the
    322 problems -- invisible until you clicked one."""
    fq = cur.frequent_index()
    for pid in sorted(set(cur.problems()) & set(fq)):
        assert cur.url(pid) == cur.leetcode_url(fq[pid]["slug"]), f"id {pid}"


def test_every_curriculum_problem_has_a_known_slug():
    missing = [p for p in cur.problems() if str(p) not in cur._slugs()]
    assert not missing, f"no authoritative slug for {missing}"


# --- concurrency --------------------------------------------------------

def test_concurrent_appends_do_not_interleave():
    """Threaded server: two handlers writing at once must not tear a line."""
    def writer(base):
        for i in range(40):
            append(make_entry(1 + base + i, "solved", TODAY, note="x" * 200))

    threads = [threading.Thread(target=writer, args=(b,)) for b in (0, 500)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for line in store.LOG.read_text(encoding="utf-8").split("\n"):
        if line.strip():
            json.loads(line)                 # every line must parse on its own
    assert len(raw_entries()) == 80


def test_atomic_write_never_leaves_a_partial_file():
    cur.add(1768, "Merge Strings Alternately")
    assert json.loads(cur.CUSTOM.read_text(encoding="utf-8"))
    assert not list(cur.CUSTOM.parent.glob("*.tmp")), "temp file left behind"
