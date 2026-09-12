"""Server tests against a real ThreadingHTTPServer on an ephemeral port."""

import json
import threading
import urllib.error
import urllib.request
from datetime import date, timedelta
from functools import partial
from http.server import ThreadingHTTPServer

import pytest

from lcsr import curriculum as cur
from lcsr import server as srv
from lcsr import store

# 314 from the PDF + 8 added to the curriculum in problems_extra.json. Explicit
# rather than computed, so silently dropping a problem fails here.
TOTAL = 324


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(store, "LOG", tmp_path / "log.jsonl")
    monkeypatch.setattr(cur, "CUSTOM", tmp_path / "custom.json")
    cur._packaged.cache_clear()

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(srv.Handler))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def call(path, body=None):
        req = urllib.request.Request(
            base + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def raw(path):
        """The export routes serve csv and ndjson, which `call` would fail to parse."""
        try:
            with urllib.request.urlopen(base + path) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    call.raw = raw
    yield call
    httpd.shutdown()


def test_index_and_endpoints_serve(client):
    for path in ("/api/plan", "/api/curriculum", "/api/history", "/api/cues"):
        code, _ = client(path)
        assert code == 200, path


def test_log_solved_schedules_nothing(client):
    code, r = client("/api/log", {"id": 1, "outcome": "solved"})
    assert code == 200 and r["done"] and r["due"] is None


def test_log_stuck_schedules_three_days(client):
    code, r = client("/api/log", {"id": 1, "outcome": "stuck"})
    assert code == 200 and not r["done"]
    assert r["due"] == (date.today() + timedelta(days=3)).isoformat()


def test_mistake_is_dropped_when_solved(client):
    """The UI's log panel keeps a selected chip visible while you press
    'Log as solved'. A mistake class on a success is meaningless and would
    pollute the histogram, so the server drops it rather than trusting the UI."""
    client("/api/log", {"id": 1, "outcome": "solved", "mistake": "invariant"})
    _, hist = client("/api/history")
    assert hist["days"][0]["entries"][0]["mistake"] is None


def test_mistake_is_kept_when_stuck(client):
    client("/api/log", {"id": 1, "outcome": "stuck", "mistake": "invariant"})
    _, hist = client("/api/history")
    assert hist["days"][0]["entries"][0]["mistake"] == "invariant"


def test_bad_mistake_rejected(client):
    code, r = client("/api/log", {"id": 1, "outcome": "stuck", "mistake": "bogus"})
    assert code == 400 and "mistake must be one of" in r["error"]


def test_unknown_problem_rejected(client):
    code, r = client("/api/log", {"id": 999999, "outcome": "solved"})
    assert code == 400 and "not in the curriculum" in r["error"]


def test_add_requires_title(client):
    code, r = client("/api/add", {"id": 1768, "title": "  "})
    assert code == 400 and "title is required" in r["error"]


def test_added_problem_appears_in_curriculum(client):
    client("/api/add", {"id": 1768, "title": "Merge Strings Alternately"})
    _, c = client("/api/curriculum")
    added = [g for g in c["groups"] if g["key"] == "added"]
    assert added and added[0]["blocks"][0]["problems"][0]["id"] == 1768
    assert c["overall"]["total"] == TOTAL + 1


def test_history_is_newest_day_first(client):
    client("/api/log", {"id": 1, "outcome": "solved", "date": "2026-08-30"})
    client("/api/log", {"id": 217, "outcome": "solved", "date": "2026-09-01"})
    _, h = client("/api/history")
    assert [d["date"] for d in h["days"]] == ["2026-09-01", "2026-08-30"]


def test_curriculum_covers_every_problem(client):
    _, c = client("/api/curriculum")
    seen = {p["id"] for g in c["groups"] for b in g["blocks"] for p in b["problems"]}
    assert len(seen) == TOTAL


def test_cannot_log_an_already_solved_problem(client):
    client("/api/log", {"id": 1, "outcome": "solved"})
    code, r = client("/api/log", {"id": 1, "outcome": "solved"})
    assert code == 400 and "already solved" in r["error"]


def test_again_reopens_a_solved_problem(client):
    client("/api/log", {"id": 1, "outcome": "solved"})
    code, r = client("/api/log", {"id": 1, "outcome": "stuck", "again": True})
    assert code == 200 and r["due"] is not None


def test_a_problem_still_in_the_ladder_can_be_logged(client):
    """Guard must block only cleared problems, never one mid-ladder."""
    client("/api/log", {"id": 1, "outcome": "stuck"})
    code, _ = client("/api/log", {"id": 1, "outcome": "solved"})
    assert code == 200


def test_plan_accepts_a_future_date(client):
    when = (date.today() + timedelta(days=120)).isoformat()
    code, p = client(f"/api/plan?date={when}")
    assert code == 200 and p["date"] == when and p["is_today"] is False
    # Only the preview branch produces these: a past date is not_today as well,
    # so asserting is_today alone tested nothing after the pinned day passed.
    assert p["ahead"] == [] and p["caught_up"] is False


def test_export_jsonl_returns_the_actual_log(client):
    """This route had no test, and an edit that emptied it survived a green run.

    It read a module-level LOG bound at import, which no fixture could redirect,
    so any test written against it would have read the developer's own log rather
    than the temporary one. It reads store.LOG at call time now.
    """
    client("/api/log", {"id": 1, "outcome": "solved"})
    code, raw = client.raw("/api/export.jsonl")
    assert code == 200
    lines = [ln for ln in raw.decode().split("\n") if ln.strip()]
    assert lines, "the raw-log export handed back an empty file"
    assert [json.loads(ln)["id"] for ln in lines] == [1]


def test_export_csv_has_a_row_for_every_problem(client):
    client("/api/log", {"id": 1, "outcome": "solved"})
    code, raw = client.raw("/api/export.csv")
    assert code == 200
    rows = raw.decode().splitlines()
    assert len(rows) == TOTAL + 1
    assert rows[0].startswith("id,title,")


def test_plan_rejects_a_bad_date(client):
    code, r = client("/api/plan?date=nonsense")
    assert code == 400 and "YYYY-MM-DD" in r["error"]


def test_undo_endpoint_reverts(client):
    client("/api/log", {"id": 1, "outcome": "stuck"})
    code, r = client("/api/undo", {"id": 1})
    assert code == 200 and r["undone"] == "stuck" and r["status"] == "new"
    _, h = client("/api/history")
    assert h["total"] == 0


def test_undo_lets_you_relog_a_solved_problem(client):
    """The guard must not trap you: undo then re-log has to work."""
    client("/api/log", {"id": 1, "outcome": "solved"})
    client("/api/undo", {"id": 1})
    code, _ = client("/api/log", {"id": 1, "outcome": "stuck"})
    assert code == 200


def test_only_the_latest_attempt_is_undoable(client):
    client("/api/log", {"id": 1, "outcome": "stuck", "date": "2026-08-30"})
    client("/api/log", {"id": 1, "outcome": "solved", "date": "2026-09-01"})
    _, h = client("/api/history")
    flags = {(d["date"], e["can_undo"]) for d in h["days"] for e in d["entries"]}
    assert ("2026-09-01", True) in flags and ("2026-08-30", False) in flags


def test_amend_endpoint_flips_a_solved_problem(client):
    client("/api/log", {"id": 1, "outcome": "solved", "date": "2026-08-30"})
    code, r = client("/api/amend", {"id": 1, "outcome": "stuck", "mistake": "invariant"})
    assert code == 200 and r["was"] == "solved" and r["now"] == "stuck"
    assert r["date"] == "2026-08-30"
    assert r["due"] == "2026-09-02"          # +3 from the original date, not today
    _, h = client("/api/history")
    assert h["total"] == 1                   # replaced, not a second attempt
    assert h["days"][0]["entries"][0]["mistake"] == "invariant"


def test_amend_then_the_solved_guard_no_longer_blocks(client):
    client("/api/log", {"id": 1, "outcome": "solved"})
    client("/api/amend", {"id": 1, "outcome": "stuck"})
    code, _ = client("/api/log", {"id": 1, "outcome": "solved"})
    assert code == 200, "re-solve of a now-unsolved problem should be allowed"


def test_amend_rejects_a_bad_mistake(client):
    client("/api/log", {"id": 1, "outcome": "solved"})
    code, r = client("/api/amend", {"id": 1, "outcome": "stuck", "mistake": "nope"})
    assert code == 400 and "mistake must be one of" in r["error"]
