"""The 18-week curriculum, plus any problems you add yourself.

Packaged problems come from the PDF and are read-only. Your own additions live
in ~/.lcsr/custom.json and are merged on top, so adding problems never means
editing packaged data or re-running the parser -- and an `lcsr` upgrade that
ships a new curriculum will not clobber them.
"""

import json
from functools import cache
from pathlib import Path

from .store import HOME

DATA = Path(__file__).parent / "data"
CUSTOM = HOME / "custom.json"

TIERS = ("foundations", "core", "reps", "stretch", "custom")


@cache
def _packaged() -> list[dict]:
    return json.loads((DATA / "problems.json").read_text(encoding="utf-8"))


@cache
def cues() -> list[dict]:
    return json.loads((DATA / "cues.json").read_text(encoding="utf-8"))


def custom() -> list[dict]:
    """Not cached: the UI adds problems mid-session and must see them at once."""
    if not CUSTOM.exists():
        return []
    return json.loads(CUSTOM.read_text(encoding="utf-8"))


def problems() -> dict[int, dict]:
    """Packaged first, then custom -- a custom entry with a packaged id wins,
    which is how you retag or re-week a problem without touching the PDF data."""
    return {p["id"]: p for p in [*_packaged(), *custom()]}


def add(pid: int, title: str, *, tier: str = "custom", week: int | None = None,
        block: str = "Added", cue: str | None = None, hard: bool = False,
        url_override: str | None = None) -> dict:
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {TIERS}")
    rows = custom()
    rows = [r for r in rows if r["id"] != pid]          # replace, don't duplicate
    entry = {
        "id": int(pid), "title": title.strip(), "hard": bool(hard),
        "immediately_after_prev": False, "tier": tier, "week": week,
        "block": block, "cue": cue, "role": tier,
        # sort after everything packaged; ties broken by id
        "order": 10_000 + int(pid),
        "url": url_override,
    }
    rows.append(entry)
    HOME.mkdir(parents=True, exist_ok=True)
    CUSTOM.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    return entry


def get(pid: int) -> dict:
    try:
        return problems()[pid]
    except KeyError:
        raise KeyError(f"{pid} is not in the curriculum -- add it with `lcsr add`") from None


def url(pid: int) -> str:
    p = get(pid)
    if p.get("url"):
        return p["url"]
    slug = "".join(c if c.isalnum() or c.isspace() or c == "-" else "" for c in p["title"].lower())
    return "https://leetcode.com/problems/" + "-".join(slug.split()) + "/"
