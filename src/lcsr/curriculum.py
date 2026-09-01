"""Read-only access to the 18-week curriculum extracted from the PDF."""

import json
from functools import cache
from pathlib import Path

DATA = Path(__file__).parent / "data"


@cache
def problems() -> dict[int, dict]:
    raw = json.loads((DATA / "problems.json").read_text(encoding="utf-8"))
    return {p["id"]: p for p in raw}


@cache
def cues() -> list[dict]:
    return json.loads((DATA / "cues.json").read_text(encoding="utf-8"))


def get(pid: int) -> dict:
    try:
        return problems()[pid]
    except KeyError:
        raise KeyError(f"{pid} is not in the curriculum") from None


def url(pid: int) -> str:
    slug = get(pid)["title"].lower()
    slug = "".join(c if c.isalnum() or c.isspace() or c == "-" else "" for c in slug)
    return "https://leetcode.com/problems/" + "-".join(slug.split())
