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
    assert len(cur.problems()) == 322          # override, not an extra row


def test_unknown_id_is_rejected():
    with pytest.raises(KeyError, match="not in the curriculum"):
        cur.get(999999)


def test_cues_merge_curriculum_and_added():
    from lcsr.curriculum import cues
    cues.cache_clear()
    rows = cues()
    assert len(rows) == 43                       # 20 from the PDF + 23 added
    assert all(c.get("group") for c in rows)     # every row is grouped
    assert {c["source"] for c in rows} == {"curriculum", "added"}
    # added rows must explain the discrimination, that is their whole point
    assert all(c.get("because") for c in rows if c["source"] == "added")


def test_undo_restores_the_previous_state():
    log(1, "stuck", DAY)
    assert replay()[1].due == DAY + timedelta(days=3)
    store.undo(1)
    assert 1 not in replay()          # back to never attempted


def test_undo_only_cancels_the_latest_attempt():
    log(1, "stuck", DAY)
    log(1, "solved", DAY + timedelta(days=3))
    store.undo(1)                      # cancels the solve, not the failure
    st = replay()[1]
    assert st.attempts == 1 and st.box == 0
    assert st.due == DAY + timedelta(days=3)


def test_undo_is_append_only():
    """The retraction is added; the original line is never rewritten."""
    log(1, "stuck", DAY)
    store.undo(1)
    raw = store.raw_entries()
    assert len(raw) == 2
    assert raw[0]["outcome"] == "stuck" and raw[1]["undo"] is True
    assert store.entries() == []


def test_undo_twice_walks_back_two_attempts():
    log(1, "stuck", DAY)
    log(1, "solved", DAY + timedelta(days=3))
    store.undo(1)
    store.undo(1)
    assert 1 not in replay()


def test_undo_with_nothing_logged_is_rejected():
    with pytest.raises(ValueError, match="no logged attempt"):
        store.undo(1)


def test_undo_frees_the_daily_quota_again():
    from lcsr.plan import todays_plan
    log(1, "solved", date.today())
    before = todays_plan()["done_today"]
    store.undo(1)
    assert todays_plan()["done_today"] == before - 1
