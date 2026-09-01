"""The frequently-asked pool: deduplication, and separation from the curriculum."""

from collections import Counter

import pytest

from lcsr import curriculum as cur
from lcsr import store
from lcsr.plan import frequent_view

LISTS = {"top150", "lc75", "top100", "striver"}
PUBLISHED = {"top150": 150, "lc75": 75, "top100": 100}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(store, "LOG", tmp_path / "log.jsonl")
    monkeypatch.setattr(cur, "CUSTOM", tmp_path / "custom.json")
    cur._packaged.cache_clear()
    cur.frequent.cache_clear()


@pytest.fixture
def pool():
    return frequent_view()["problems"]


# --- deduplication among the sheets -------------------------------------

def test_every_problem_appears_exactly_once(pool):
    ids = [p["id"] for p in pool]
    assert len(ids) == len(set(ids)), "the same problem is listed twice"


def test_each_problem_names_each_source_at_most_once(pool):
    for p in pool:
        assert len(p["lists"]) == len(set(p["lists"])), p["id"]


def test_list_membership_matches_the_published_sizes(pool):
    """A2Z self-duplicates (some problems sit under two topics), so it is checked
    as a floor; the three LeetCode plans have exact published sizes."""
    counts = Counter(l for p in pool for l in p["lists"])
    for key, n in PUBLISHED.items():
        assert counts[key] == n, f"{key}: {counts[key]} != {n}"
    assert counts["striver"] >= 250


def test_overlap_count_is_consistent_with_membership(pool):
    for p in pool:
        assert p["count"] == len(p["lists"])
        assert 1 <= p["count"] <= 4
        assert set(p["lists"]) <= LISTS


def test_merging_actually_collapsed_duplicates(pool):
    """599 raw entries across four lists; anything near that means the merge
    silently stopped deduplicating."""
    raw = sum(p["count"] for p in pool)
    assert raw > len(pool), "no duplicates collapsed at all"
    assert len(pool) < 400


def test_slugs_are_unique_too(pool):
    slugs = [p["slug"] for p in pool]
    assert len(slugs) == len(set(slugs))


# --- separation from, and cross-reference with, the curriculum ----------

def test_pool_is_not_merged_into_the_curriculum(pool):
    """The curriculum's totals must not move because this list exists."""
    assert len(cur.problems()) == 322
    only_here = [p for p in pool if not p["in_curriculum"]]
    assert only_here, "expected problems that exist only in the frequent pool"
    assert all(p["id"] not in cur.problems() for p in only_here)


def test_curriculum_overlap_is_reported_accurately(pool):
    curric = cur.problems()
    for p in pool:
        assert p["in_curriculum"] == (p["id"] in curric)
        if p["in_curriculum"]:
            assert p["curriculum"]["tier"] == curric[p["id"]]["tier"]
        else:
            assert p["curriculum"] is None


def test_solved_flag_follows_the_log():
    from lcsr.store import append, make_entry
    from datetime import date
    before = {p["id"]: p["solved"] for p in frequent_view()["problems"]}
    target = next(i for i, s in before.items() if not s and i in cur.problems())
    append(make_entry(target, "solved", date.today()))
    after = {p["id"]: p["solved"] for p in frequent_view()["problems"]}
    assert after[target] is True
    assert sum(after.values()) == sum(before.values()) + 1


def test_stats_add_up(pool):
    st = frequent_view()["stats"]
    assert st["total"] == len(pool)
    assert st["in_curriculum"] + st["only_here"] == st["total"]
    assert sum(st["by_count"].values()) == st["total"]
    assert sum(st["by_difficulty"].values()) == st["total"]


def test_urls_are_wellformed(pool):
    for p in pool:
        assert p["url"] == f"https://leetcode.com/problems/{p['slug']}/"


# --- logging a frequent-only problem ------------------------------------

def freq_only_id():
    curric = cur.problems()
    return next(p["id"] for p in frequent_view()["problems"] if p["id"] not in curric)


def test_a_frequent_only_problem_can_be_logged():
    from datetime import date
    from lcsr.store import append, make_entry, replay
    pid = freq_only_id()
    cur.loggable(pid)                      # must resolve, not raise
    append(make_entry(pid, "stuck", date.today()))
    assert replay()[pid].due is not None   # gets the same +3/+10/+30 ladder


def test_logging_a_frequent_only_problem_does_not_move_curriculum_metrics():
    """The whole point of keeping the sets separate."""
    from datetime import date
    from lcsr.plan import metrics
    from lcsr.store import append, make_entry
    append(make_entry(1, "solved", date.today()))          # a curriculum problem
    before = metrics()
    append(make_entry(freq_only_id(), "solved", date.today()))
    after = metrics()
    for k in ("attempted", "total", "first_try", "resolve_rate", "resolve_n"):
        assert after[k] == before[k], f"{k} moved: {before[k]} -> {after[k]}"


def test_solving_a_shared_problem_counts_in_both():
    """227 of the 363 ARE curriculum problems; solving one is a single event and
    must register on both surfaces."""
    from datetime import date
    from lcsr.plan import metrics
    from lcsr.store import append, make_entry
    shared = next(p["id"] for p in frequent_view()["problems"] if p["in_curriculum"])
    append(make_entry(shared, "solved", date.today()))
    assert metrics()["attempted"] == 1
    assert next(p for p in frequent_view()["problems"] if p["id"] == shared)["solved"]


def test_frequent_only_problem_shows_in_history_with_a_title():
    from datetime import date
    from lcsr.plan import history_view
    from lcsr.store import append, make_entry
    pid = freq_only_id()
    append(make_entry(pid, "solved", date.today()))
    e = history_view()["days"][0]["entries"][0]
    assert e["id"] == pid
    assert not e["title"].startswith("#"), "fell back to a bare id"
    assert e["url"] and e["url"].startswith("https://leetcode.com/problems/")


def test_unknown_problem_still_rejected():
    with pytest.raises(KeyError, match="not in the curriculum or the frequent list"):
        cur.loggable(999999)
