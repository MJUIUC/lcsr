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
    assert c["overall"]["total"] == 315


def test_history_is_newest_day_first(client):
    client("/api/log", {"id": 1, "outcome": "solved", "date": "2026-08-30"})
    client("/api/log", {"id": 217, "outcome": "solved", "date": "2026-09-01"})
    _, h = client("/api/history")
    assert [d["date"] for d in h["days"]] == ["2026-09-01", "2026-08-30"]


def test_curriculum_covers_every_problem(client):
    _, c = client("/api/curriculum")
    seen = {p["id"] for g in c["groups"] for b in g["blocks"] for p in b["problems"]}
    assert len(seen) == 314
