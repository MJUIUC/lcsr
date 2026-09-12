"""The daily-load rule, exhaustively.

Four rules decide how many new problems a day offers: the curriculum's load, the
foundations keep-alive, the per-tier overrides, and the total cap. They compose
in an order that matters, and getting it wrong does not raise -- it hands you a
day with a tier silently at zero, and a tier at zero never gets worked. Diff
review does not catch that, so it gets a truth table.
"""

import itertools
import json

import pytest

from lcsr import settings as cfg
from lcsr import store
from lcsr.settings import COUNTED, Settings, allowance, daily_quota

WEEKS = range(1, 17)
REMAINING = (0, 1, 3, 42)          # foundations left: none, one, exactly the cap, many


# --------------------------------------------------------------- the defaults

def test_default_settings_reproduce_the_curriculum_exactly():
    """A fresh install must behave as it did before settings existed."""
    for wk in WEEKS:
        q = daily_quota(wk, 0, Settings())
        assert q == allowance(wk), wk


@pytest.mark.parametrize("wk,left", list(itertools.product(WEEKS, REMAINING)))
def test_foundations_stay_alive_while_any_remain(wk, left):
    """One tier's progress must never zero another's.

    intake_week() comes from CORE progress and allowance() zeroes foundations
    from week 4, so without this, finishing weeks 1-3's core strands every
    remaining foundation. This is the regression that bit twice.
    """
    q = daily_quota(wk, left, Settings())
    if left:
        assert q["foundations"] > 0, (wk, left)
    else:
        assert q["foundations"] == allowance(wk)["foundations"]


# ------------------------------------------------------------- the overrides

@pytest.mark.parametrize("wk,n", list(itertools.product(WEEKS, range(0, 6))))
def test_a_per_tier_override_wins_outright(wk, n):
    for tier in COUNTED:
        q = daily_quota(wk, 42, Settings(**{tier: n}))
        assert q[tier] == n, (wk, tier, n)


@pytest.mark.parametrize("wk", WEEKS)
def test_zero_is_an_instruction_and_none_is_not(wk):
    """0 means stop issuing the tier; None means follow the curriculum.

    Collapsing them would make "pause foundations" indistinguishable from "use
    the default", and the default is nonzero in weeks 1-3.
    """
    assert daily_quota(wk, 42, Settings(foundations=0))["foundations"] == 0
    assert daily_quota(wk, 42, Settings(foundations=None))["foundations"] > 0


@pytest.mark.parametrize("wk", WEEKS)
def test_an_override_beats_the_keep_alive_too(wk):
    assert daily_quota(wk, 42, Settings(foundations=1))["foundations"] == 1


# -------------------------------------------------------------- the total cap

GRID = list(itertools.product(WEEKS, REMAINING, range(0, 9)))


@pytest.mark.parametrize("wk,left,total", GRID)
def test_the_cap_is_never_exceeded(wk, left, total):
    q = daily_quota(wk, left, Settings(daily_total=total))
    assert sum(q[t] for t in COUNTED) <= total, (wk, left, total, q)


@pytest.mark.parametrize("wk,left,total", GRID)
def test_nothing_is_ever_negative(wk, left, total):
    q = daily_quota(wk, left, Settings(daily_total=total))
    assert all(q[t] >= 0 for t in q), (wk, left, total, q)


@pytest.mark.parametrize("wk,left,total", GRID)
def test_the_cap_only_ever_removes(wk, left, total):
    """A cap must not inflate a day that was already under it."""
    base = daily_quota(wk, left, Settings())
    capped = daily_quota(wk, left, Settings(daily_total=total))
    assert all(capped[t] <= base[t] for t in COUNTED), (wk, left, total)


@pytest.mark.parametrize("wk,left", list(itertools.product(WEEKS, REMAINING)))
def test_a_generous_cap_changes_nothing(wk, left):
    base = daily_quota(wk, left, Settings())
    assert daily_quota(wk, left, Settings(daily_total=99)) == base


@pytest.mark.parametrize("wk,left", list(itertools.product(WEEKS, REMAINING)))
def test_core_is_the_last_thing_cut(wk, left):
    """The curriculum's own rule: cut Reps and Stretch before you cut Core."""
    base = daily_quota(wk, left, Settings())
    for total in range(0, sum(base[t] for t in COUNTED) + 1):
        q = daily_quota(wk, left, Settings(daily_total=total))
        # core is only reduced once reps and foundations are already at zero
        if q["core"] < base["core"]:
            assert q["reps"] == 0 and q["foundations"] == 0, (wk, left, total, q)


@pytest.mark.parametrize("wk,left", list(itertools.product(WEEKS, REMAINING)))
def test_reps_are_cut_before_foundations(wk, left):
    base = daily_quota(wk, left, Settings())
    for total in range(0, sum(base[t] for t in COUNTED) + 1):
        q = daily_quota(wk, left, Settings(daily_total=total))
        if q["foundations"] < base["foundations"]:
            assert q["reps"] == 0, (wk, left, total, q)


def test_a_zero_total_issues_no_new_problems():
    for wk in WEEKS:
        q = daily_quota(wk, 42, Settings(daily_total=0))
        assert sum(q[t] for t in COUNTED) == 0


# ------------------------------------------------------- overrides plus a cap

@pytest.mark.parametrize("wk,left,total", GRID)
def test_an_override_under_the_cap_survives_it(wk, left, total):
    """The cap trims; it must not raise a tier the user pinned lower."""
    q = daily_quota(wk, left, Settings(core=1, daily_total=total))
    assert q["core"] <= 1, (wk, left, total, q)


def test_custom_never_counts_toward_the_total():
    """Your own additions are yours; target_today has always excluded them."""
    q = daily_quota(1, 0, Settings(daily_total=0))
    assert q["custom"] == allowance(1)["custom"]


# ------------------------------------------------------------- the file layer

def test_validation_rejects_what_would_corrupt_a_day():
    for bad in (-1, 51, 1.5, True, "many"):
        with pytest.raises(ValueError):
            cfg.from_dict({"core": bad})


def test_blank_and_none_both_mean_follow_the_curriculum():
    assert cfg.from_dict({"core": None}).core is None
    assert cfg.from_dict({"core": ""}).core is None
    assert cfg.from_dict({}).is_default()


def test_round_trip_through_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    assert cfg.load().is_default()
    cfg.update(core=4, daily_total=6)
    assert cfg.load() == Settings(core=4, daily_total=6)
    cfg.update(core=None)                       # clearing one override
    assert cfg.load() == Settings(daily_total=6)
    cfg.reset()
    assert cfg.load().is_default()


def test_a_corrupt_settings_file_falls_back_instead_of_breaking(tmp_path, monkeypatch):
    """Settings are a preference, not a record. A hand-edited file that no longer
    parses must not take down every read path the way a corrupt log rightly does."""
    monkeypatch.setattr(store, "HOME", tmp_path)
    p = tmp_path / "settings.json"
    p.write_text("{not json", encoding="utf-8")
    assert cfg.load().is_default()
    p.write_text(json.dumps({"core": -5}), encoding="utf-8")
    assert cfg.load().is_default()


def test_update_rejects_an_unknown_key(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    with pytest.raises(ValueError):
        cfg.update(stretch=3)
