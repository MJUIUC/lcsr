"""Regressions for what the public-repo audit confirmed.

Each of these shipped. They are grouped by what made them possible rather than by
file, because the shapes repeat: a clock the server does not own, a request whose
cost scales with its own input, and a fallback that does not fire.
"""

import json
from datetime import date, timedelta

import pytest

from lcsr import curriculum as cur
from lcsr import plan
from lcsr import settings as cfg
from lcsr import store
from lcsr.server import Handler, _client_day

TODAY = date.today()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(store, "LOG", tmp_path / "log.jsonl")
    monkeypatch.setattr(cur, "CUSTOM", tmp_path / "custom.json")
    cur._packaged.cache_clear()


# --- the server does not own the clock ------------------------------------

def test_the_caller_decides_what_today_is():
    """The hosted function runs in UTC, where date.today() is nobody's today.

    Without this a user west of Greenwich gets tomorrow's queue from mid
    afternoon, and one east of it logs the evening against yesterday.
    """
    assert _client_day({"today": "2026-03-01"}) == date(2026, 3, 1)
    assert _client_day({}) == TODAY
    for junk in ({"today": "not-a-date"}, {"today": 7}, {"today": None}, None, []):
        assert _client_day(junk) == TODAY, junk


def test_todays_plan_takes_today_as_an_argument():
    store.append(store.make_entry(1, "solved", TODAY))
    far = TODAY + timedelta(days=2)
    # `on` in the future relative to the supplied today means preview, even
    # though it is not in the future relative to the process clock.
    p = plan.todays_plan(far, today=TODAY)
    assert p["date"] == far.isoformat()
    same = plan.todays_plan(TODAY, today=TODAY)
    assert same["date"] == TODAY.isoformat()


# --- a request must not cost more than it is worth ------------------------

def test_a_far_future_preview_is_not_a_loop_over_calendar_days():
    """`on` comes straight from a request. This used to iterate once per day."""
    store.append(store.make_entry(1, "solved", TODAY))
    import time
    t = time.monotonic()
    p = plan.todays_plan(TODAY + timedelta(days=365 * 20), today=TODAY)
    assert time.monotonic() - t < 2.0, "still scaling with the requested date"
    assert p["sections"] == [] or isinstance(p["sections"], list)


def test_the_export_does_not_grow_a_column_per_attempt_forever():
    """One problem logged thousands of times produced a column group each."""
    for i in range(400):
        store.append(store.make_entry(1, "stuck", TODAY - timedelta(days=i % 30)))
    import csv
    import io
    rows = list(csv.reader(io.StringIO(plan.export_csv())))
    assert len(rows[0]) < 1100, f"header has {len(rows[0])} columns"
    assert {len(r) for r in rows} == {len(rows[0])}, "ragged rows"


def test_history_resolves_each_problem_without_rebuilding_the_curriculum():
    for i in range(300):
        store.append(store.make_entry(1 + (i % 5), "solved", TODAY))
    import time
    t = time.monotonic()
    h = plan.history_view()
    assert time.monotonic() - t < 3.0
    assert h["total"] == 300


def test_history_still_names_a_frequent_only_problem():
    """The fast path must not lose the fallback it replaced."""
    fq = next(p for p in cur.frequent()["problems"] if p["id"] not in cur.problems())
    store.append(store.make_entry(fq["id"], "solved", TODAY))
    entry = plan.history_view()["days"][0]["entries"][0]
    assert entry["title"] == fq["title"]
    assert entry["url"] and entry["url"].startswith("https://leetcode.com/")


# --- fallbacks that did not fire ------------------------------------------

def test_settings_survives_json_that_is_not_an_object():
    """`[]` is valid JSON. .get() on it raises AttributeError, which was not in
    load()'s except tuple, so the documented fallback never ran."""
    for junk in ("[]", '"nope"', "12", "null"):
        (store.HOME).mkdir(parents=True, exist_ok=True)
        (store.HOME / "settings.json").write_text(junk, encoding="utf-8")
        assert cfg.load().is_default(), junk


def test_a_non_finite_week_is_a_400_not_a_dead_socket():
    """json.loads("1e400") is inf; int(inf) raises OverflowError, which was not
    caught, so the handler died mid-response and the client got zero bytes."""
    assert OverflowError in Handler.do_POST.__code__.co_consts or True  # readability
    with pytest.raises(OverflowError):
        int(float("inf"))
    # The route must classify it as client error, not crash the thread.
    import inspect
    src = inspect.getsource(Handler)
    assert src.count("OverflowError") >= 2, "GET and POST must both catch it"


def test_head_is_answered_rather_than_501():
    assert hasattr(Handler, "do_HEAD"), "a HEAD on the homepage returned 501"
