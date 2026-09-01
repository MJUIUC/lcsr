"""Append-only attempt log, plus the projection of it into schedule state.

log.jsonl is the only record. Everything else -- due dates, boxes, the three
metrics -- is recomputed from it by replay(). Nothing is stored twice, so
nothing can drift out of sync, and the scheduling rule can be changed later
without invalidating the history.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from .schedule import advance

HOME = Path(os.environ.get("LCSR_HOME", Path.home() / ".lcsr"))
LOG = HOME / "log.jsonl"

MISTAKES = ("off-by-one", "invariant", "edge-case", "no-pattern")


@dataclass
class ProblemState:
    pid: int
    attempts: int = 0
    box: int | None = None
    done: bool = False
    due: date | None = None
    last: date | None = None
    outcomes: list[str] = field(default_factory=list)


def append(entry: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def entries() -> list[dict]:
    if not LOG.exists():
        return []
    rows = [json.loads(ln) for ln in LOG.read_text(encoding="utf-8").splitlines() if ln.strip()]
    # Entries can be logged out of order (backfilling yesterday after today),
    # and replay is order-dependent -- sort by the attempt date, not by
    # insertion, or a backfill would be folded in as if it happened last.
    return sorted(rows, key=lambda r: (r["date"], r.get("ts", "")))


def replay(rows: list[dict] | None = None) -> dict[int, ProblemState]:
    rows = entries() if rows is None else rows
    states: dict[int, ProblemState] = {}
    for r in rows:
        st = states.setdefault(r["id"], ProblemState(pid=r["id"]))
        nxt = advance(st.box, r["outcome"])
        d = date.fromisoformat(r["date"])
        st.attempts += 1
        st.box, st.done = nxt.box, nxt.done
        st.due = None if nxt.due_in_days is None else d + timedelta(days=nxt.due_in_days)
        st.last = d
        st.outcomes.append(r["outcome"])
    return states


def make_entry(pid: int, outcome: str, on: date, mistake: str | None = None,
               approach_min: float | None = None, note: str | None = None) -> dict:
    return {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "date": on.isoformat(),
        "id": pid,
        "outcome": outcome,
        "mistake": mistake,
        "approach_min": approach_min,
        "note": note,
    }
