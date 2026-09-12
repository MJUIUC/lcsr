"""The 18-week curriculum, plus any problems you add yourself.

Packaged problems come from the PDF and are read-only. Your own additions live
in ~/.lcsr/custom.json and are merged on top, so adding problems never means
editing packaged data or re-running the parser -- and an `lcsr` upgrade that
ships a new curriculum will not clobber them.
"""

import json
from functools import cache
from pathlib import Path

from . import store
from .store import HOME, LOCK

DATA = Path(__file__).parent / "data"
CUSTOM = HOME / "custom.json"

TIERS = ("foundations", "core", "reps", "stretch", "custom")


@cache
def _packaged() -> list[dict]:
    """The PDF's 314, then our additions to the curriculum itself.

    Two files for the same reason the cue table has two: problems.json is
    regenerated from the PDF by tools/parse_curriculum.py and must not be
    hand-edited, and that script asserts the tier counts against the figures the
    document states for itself. problems_extra.json is ours and survives
    regeneration. Neither is user state -- that is custom.json.
    """
    base = json.loads((DATA / "problems.json").read_text(encoding="utf-8"))
    extra = json.loads((DATA / "problems_extra.json").read_text(encoding="utf-8"))
    return [*base, *extra]


@cache
def cues() -> list[dict]:
    """The PDF's 20 rows, then added contrasts for the confusable pairs.

    Kept in two files so provenance stays clear: cues.json is regenerated from
    the PDF by tools/parse_curriculum.py and must not be hand-edited, while
    cues_extra.json is ours and survives regeneration.
    """
    base = json.loads((DATA / "cues.json").read_text(encoding="utf-8"))
    for c in base:
        c.setdefault("group", "From the curriculum")
        c["source"] = "curriculum"
    extra = json.loads((DATA / "cues_extra.json").read_text(encoding="utf-8"))
    for c in extra:
        c["source"] = "added"
    return [*base, *extra]


def custom() -> list[dict]:
    """Not cached: the UI adds problems mid-session and must see them at once."""
    return store.backend().read_custom()


def problems() -> dict[int, dict]:
    """Packaged first, then custom -- a custom entry with a packaged id wins,
    which is how you retag or re-week a problem without touching the PDF data."""
    return {p["id"]: p for p in [*_packaged(), *custom()]}


def add(pid: int, title: str, *, tier: str = "custom", week: int | None = None,
        block: str = "Added", cue: str | None = None, hard: bool = False,
        url_override: str | None = None, order: float | None = None) -> dict:
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {TIERS}")
    # Serialized and atomic: /api/add is served from a thread pool, so two
    # concurrent adds would both read the old file and the second would overwrite
    # the first, and a reader could catch the file mid-truncation.
    with LOCK:
        rows = [r for r in custom() if r["id"] != pid]   # replace, don't duplicate
        entry = {
            "id": int(pid), "title": title.strip(), "hard": bool(hard),
            "immediately_after_prev": False, "tier": tier, "week": week,
            "block": block, "cue": cue, "role": tier,
            # Default: sort after everything packaged, ties broken by id. An explicit
            # order slots a problem into its real place in the sequence instead --
            # fractional values sit between two packaged problems without renumbering
            # them, which matters because the curriculum is "never reordered" and a
            # base exemplar added after its own hard variant would teach backwards.
            "order": 10_000 + int(pid) if order is None else float(order),
            "url": url_override,
        }
        rows.append(entry)
        store.backend().write_custom(rows)
    return entry


def get(pid: int) -> dict:
    try:
        return problems()[pid]
    except KeyError:
        raise KeyError(f"{pid} is not in the curriculum -- add it with `lcsr add`") from None


@cache
def _slugs() -> dict[str, str]:
    """LeetCode id -> real titleSlug, pulled from leetcode.com by tools/build_slugs.py.

    Deriving the slug from the title does not work: the curriculum abbreviates
    ("Maximum Depth" for "Maximum Depth of Binary Tree", "Level Order Traversal"
    for "Binary Tree Level Order Traversal"), which produced 404 links for 28 of
    the 322 problems -- silently, since a 404 only shows up in the browser.
    """
    return json.loads((DATA / "slugs.json").read_text(encoding="utf-8"))


def url(pid: int) -> str:
    p = get(pid)
    if p.get("url"):
        return p["url"]
    slug = _slugs().get(str(pid))
    if slug:
        return leetcode_url(slug)
    # Last resort for a problem added locally and never resolved upstream.
    guess = "".join(c if c.isalnum() or c.isspace() or c == "-" else "" for c in p["title"].lower())
    return leetcode_url("-".join(guess.split()))


@cache
def frequent() -> dict:
    """The frequently-asked pool, merged from four public lists.

    Built by tools/build_frequent.py and deduplicated there by LeetCode frontend
    id. Deliberately NOT merged into problems(): these are a browsing and draw
    surface, and folding them in would change the curriculum's totals and its
    metrics. Overlap with the curriculum is reported per problem instead.
    """
    return json.loads((DATA / "frequent.json").read_text(encoding="utf-8"))


def leetcode_url(slug: str) -> str:
    return f"https://leetcode.com/problems/{slug}/"


@cache
def frequent_index() -> dict[int, dict]:
    return {p["id"]: p for p in frequent()["problems"]}


def loggable(pid: int) -> dict:
    """Resolve a problem from the curriculum OR the frequently-asked pool.

    Attempts are recorded against both sets from one log, because 227 of the 363
    frequent problems ARE curriculum problems and solving one is a single event.
    What stays separate is the accounting: metrics() scopes itself to curriculum
    ids, so logging a frequent-only problem never moves the curriculum's numbers.
    """
    hit = problems().get(pid)
    if hit:
        return hit
    fq = frequent_index().get(pid)
    if fq:
        return {**fq, "tier": "frequent", "week": None,
                "block": "Frequently asked", "role": "frequent",
                "immediately_after_prev": False, "cue": None, "order": 20_000 + pid}
    raise KeyError(f"{pid} is not in the curriculum or the frequent list")


def url_of(pid: int) -> str:
    if pid in problems():
        return url(pid)
    fq = frequent_index().get(pid)
    if fq:
        return leetcode_url(fq["slug"])
    raise KeyError(f"{pid} is not in the curriculum or the frequent list")
