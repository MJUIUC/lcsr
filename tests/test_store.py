"""Replay is order-dependent, so these cover the ways ordering can go wrong."""

from datetime import date, timedelta

import pytest

from lcsr import curriculum as cur
from lcsr import store
from lcsr.store import append, make_entry, replay

DAY = date(2026, 9, 1)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Point every path at a tmp dir; these tests must never touch ~/.lcsr."""
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(store, "LOG", tmp_path / "log.jsonl")
    monkeypatch.setattr(cur, "CUSTOM", tmp_path / "custom.json")
    cur._packaged.cache_clear()
    yield


def log(pid, outcome, on):
    append(make_entry(pid, outcome, on))


def test_solved_cold_never_returns():
    log(1, "solved", DAY)
    st = replay()[1]
    assert st.done and st.due is None


def test_full_ladder():
    log(1, "stuck", DAY)
    assert replay()[1].due == DAY + timedelta(days=3)
    log(1, "solved", DAY + timedelta(days=3))
    assert replay()[1].due == DAY + timedelta(days=13)   # +10
    log(1, "solved", DAY + timedelta(days=13))
    assert replay()[1].due == DAY + timedelta(days=43)   # +30
    log(1, "solved", DAY + timedelta(days=43))
    assert replay()[1].done


def test_failure_midway_resets_to_bottom():
    log(1, "stuck", DAY)
    log(1, "solved", DAY + timedelta(days=3))            # box 1
    log(1, "stuck", DAY + timedelta(days=13))
    st = replay()[1]
    assert st.box == 0 and st.due == DAY + timedelta(days=16)


def test_backfill_is_folded_in_date_order():
    """Logging today first and yesterday second must give the same result as
    logging them in order -- replay sorts by attempt date, not insertion."""
    log(1, "solved", DAY)                 # the re-solve, entered first
    log(1, "stuck", DAY - timedelta(days=1))   # the original failure, backfilled
    st = replay()[1]
    # stuck (box 0) then solved -> box 1, due 10 days after the SOLVE date
    assert st.box == 1
    assert st.due == DAY + timedelta(days=10)


def test_custom_problem_merges_and_overrides():
    cur.add(1768, "Merge Strings Alternately", block="Warmup")
    assert cur.get(1768)["title"] == "Merge Strings Alternately"
    assert cur.url(1768) == "https://leetcode.com/problems/merge-strings-alternately/"
    cur.add(1768, "Renamed")                       # replaces, does not duplicate
    assert len(cur.custom()) == 1
    assert cur.get(1768)["title"] == "Renamed"


def test_custom_can_override_a_packaged_problem():
    cur.add(1, "Two Sum", week=4, block="Moved")
    assert cur.get(1)["week"] == 4
    assert len(cur.problems()) == 314          # override, not an extra row


def test_unknown_id_is_rejected():
    with pytest.raises(KeyError, match="not in the curriculum"):
        cur.get(999999)
