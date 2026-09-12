"""Running without a filesystem.

The deployed build has no writable disk, so the browser holds the log, the
custom problems and the settings and posts them with each request. The property
that makes that safe is parity: the same log must produce the same plan through
either backend, or the deployed site and the CLI are two different tools that
happen to share a name.
"""

import json
from datetime import date, timedelta

import pytest

from lcsr import curriculum as cur
from lcsr import plan
from lcsr import settings as cfg
from lcsr import store

TODAY = date.today()
EARLIER = TODAY - timedelta(days=20)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(store, "LOG", tmp_path / "log.jsonl")
    monkeypatch.setattr(cur, "CUSTOM", tmp_path / "custom.json")
    cur._packaged.cache_clear()


def seed():
    """A log with every kind of record in it: attempts, a retraction, a pass."""
    store.append(store.make_entry(1, "solved", EARLIER))
    store.append(store.make_entry(217, "stuck", EARLIER, "edge-case", note="empty input"))
    store.append(store.make_entry(242, "solved", EARLIER + timedelta(days=1)))
    store.undo(242)
    store.append(store.make_entry(49, "stuck", EARLIER + timedelta(days=2), "invariant"))
    cfg.update(core=3)
    cur.add(9999, "A problem of my own", week=2, cue="mine")


def in_memory(rows, custom, settings):
    return store.MemoryBackend(log=list(rows), custom=list(custom), settings=dict(settings))


# --- parity ---------------------------------------------------------------

def test_the_same_log_gives_the_same_plan_through_either_backend():
    seed()
    from_file = plan.todays_plan()
    rows, custom, settings = (store.raw_entries(), cur.custom(),
                              store.backend().read_settings())

    token = store.use(in_memory(rows, custom, settings))
    try:
        from_memory = plan.todays_plan()
    finally:
        store.release(token)

    assert from_memory == from_file, "the deployed build would schedule a different day"


def test_metrics_and_curriculum_match_too():
    seed()
    file_metrics, file_curric = plan.metrics(), plan.curriculum_view()
    rows, custom, settings = (store.raw_entries(), cur.custom(),
                              store.backend().read_settings())
    token = store.use(in_memory(rows, custom, settings))
    try:
        assert plan.metrics() == file_metrics
        assert plan.curriculum_view() == file_curric
    finally:
        store.release(token)


def test_history_and_export_match():
    seed()
    hist, csv = plan.history_view(), plan.export_csv()
    rows, custom, settings = (store.raw_entries(), cur.custom(),
                              store.backend().read_settings())
    token = store.use(in_memory(rows, custom, settings))
    try:
        assert plan.history_view() == hist
        assert plan.export_csv() == csv
    finally:
        store.release(token)


# --- what a write hands back ----------------------------------------------

def test_a_write_returns_the_records_to_persist():
    mem = in_memory([], [], {})
    token = store.use(mem)
    try:
        store.append(store.make_entry(1, "stuck", TODAY, "off-by-one"))
        patch = mem.patch()
    finally:
        store.release(token)
    assert [r["id"] for r in patch["log_append"]] == [1]
    assert "custom" not in patch and "settings" not in patch


def test_replaying_the_returned_records_reproduces_the_state():
    """The client appends what it is given; that has to be enough."""
    mem = in_memory([], [], {})
    token = store.use(mem)
    try:
        store.append(store.make_entry(217, "stuck", EARLIER))
        store.append(store.make_entry(217, "solved", EARLIER + timedelta(days=3)))
        server_state = store.replay()
        client_log = mem.patch()["log_append"]
    finally:
        store.release(token)

    token = store.use(in_memory(client_log, [], {}))
    try:
        assert store.replay() == server_state
    finally:
        store.release(token)


def test_undo_and_sprint_records_reach_the_client():
    mem = in_memory([], [], {})
    token = store.use(mem)
    try:
        store.append(store.make_entry(1, "solved", TODAY))
        store.undo(1)
        store.start_sprint()
        kinds = mem.patch()["log_append"]
    finally:
        store.release(token)
    assert any(r.get("undo") for r in kinds), "a retraction never reached the browser"
    assert any("sprint" in r for r in kinds), "a pass marker never reached the browser"


def test_custom_and_settings_come_back_whole():
    mem = in_memory([], [], {})
    token = store.use(mem)
    try:
        cur.add(4242, "Added in the browser")
        cfg.update(daily_total=4)
        patch = mem.patch()
    finally:
        store.release(token)
    assert [p["id"] for p in patch["custom"]] == [4242]
    assert patch["settings"]["daily_total"] == 4


# --- the file backend is untouched ----------------------------------------

def test_memory_writes_never_touch_the_disk(tmp_path):
    token = store.use(in_memory([], [], {}))
    try:
        store.append(store.make_entry(1, "solved", TODAY))
        cur.add(5, "nope")
        cfg.update(core=1)
    finally:
        store.release(token)
    assert not store.LOG.exists(), "a stateless write created a file"
    assert not cur.CUSTOM.exists()
    assert not (store.HOME / "settings.json").exists()


def test_the_default_backend_is_still_the_file():
    assert isinstance(store.backend(), store.FileBackend)
    store.append(store.make_entry(1, "solved", TODAY))
    assert store.LOG.exists()
    assert [r["id"] for r in store.raw_entries()] == [1]


def test_a_corrupt_supplied_log_is_rejected_by_name_not_by_500():
    """The same named-line error the file path gives, so a bad client payload is
    a 400 with a reason rather than a stack trace."""
    mem = store.MemoryBackend(log=[])
    mem.read_log = lambda: '{"ok":1}\n{not json\n'
    token = store.use(mem)
    try:
        with pytest.raises(ValueError, match="line 2|:2 "):
            store.raw_entries()
    finally:
        store.release(token)


def test_a_junk_payload_degrades_to_an_empty_log():
    """A client sending nonsense gets a fresh start, not an exception."""
    for junk in (None, [], "nope", {"log": "not-a-list"}, {"log": None}):
        b = store.MemoryBackend.from_payload(junk)
        assert b.log == [] and b.custom == [] and b.settings == {}


def test_two_requests_do_not_see_each_other():
    """Serverless or threaded, one visitor's state must not leak into another's."""
    a = in_memory([store.make_entry(1, "solved", TODAY)], [], {})
    b = in_memory([store.make_entry(217, "solved", TODAY)], [], {})
    t = store.use(a)
    try:
        assert set(store.replay()) == {1}
    finally:
        store.release(t)
    t = store.use(b)
    try:
        assert set(store.replay()) == {217}
    finally:
        store.release(t)
    assert isinstance(store.backend(), store.FileBackend)


# --- the one endpoint that both reads and writes ---------------------------

def test_settings_post_is_a_read_or_a_write_by_payload():
    """`/api/settings` answers both. Routing it by path alone made every save
    look like a read: it returned the old values and stored nothing."""
    from lcsr.server import Handler

    class H(Handler):
        def __init__(self, path):        # no socket; only the routing is under test
            self.path = path

    assert H("/api/settings")._is_read({"state": {}})
    assert not H("/api/settings")._is_read({"state": {}, "core": 3})
    assert not H("/api/settings")._is_read({"reset": True})
    assert H("/api/plan")._is_read({"state": {}, "core": 3})
    assert not H("/api/log")._is_read({"state": {}})
