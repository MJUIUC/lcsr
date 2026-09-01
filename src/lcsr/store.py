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


def raw_entries() -> list[dict]:
    """Every line in the log, retractions included, in attempt order.

    Entries can be logged out of order (backfilling yesterday after today), and
    replay is order-dependent -- sort by the attempt date, not by insertion, or
    a backfill would be folded in as if it happened last.
    """
    if not LOG.exists():
        return []
    rows = []
    for n, ln in enumerate(LOG.read_text(encoding="utf-8").splitlines(), 1):
        if not ln.strip():
            continue
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError as e:
            # Name the line. Skipping it silently would drop real attempts and
            # quietly change every metric; a raw JSONDecodeError names nothing.
            raise ValueError(
                f"{LOG}:{n} is not valid JSON ({e.msg}). Fix or delete that line."
            ) from None
    return sorted(rows, key=lambda r: (r["date"], r.get("ts", "")))


def entries() -> list[dict]:
    """Attempts that still stand, with retractions applied.

    Undo appends a retraction rather than deleting a line: the file stays
    append-only, so a mis-logged attempt is recoverable and the record of what
    actually happened is never rewritten underneath you. A retraction cancels
    the most recent surviving attempt at that problem.
    """
    alive: list[dict | None] = []
    positions: dict[int, list[int]] = {}
    for r in raw_entries():
        pid = r["id"]
        if r.get("undo"):
            if positions.get(pid):
                alive[positions[pid].pop()] = None
            continue
        positions.setdefault(pid, []).append(len(alive))
        alive.append(r)
    return [r for r in alive if r is not None]


def make_undo(pid: int, on: date) -> dict:
    """Dated to the attempt it cancels, so it sorts directly after it."""
    return {"ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "date": on.isoformat(), "id": pid, "undo": True}


def amend(pid: int, outcome: str, mistake: str | None = None,
          note: str | None = None) -> dict:
    """Replace the most recent attempt's outcome, keeping its original date.

    This is the "I pressed the wrong button" path, which is different from
    logging a fresh attempt: re-logging today would claim you worked the problem
    today, shifting its next due date and consuming today's quota. Implemented as
    a retraction plus a replacement at the same date, so the log stays
    append-only and the correction is visible rather than silent.
    """
    live = [r for r in entries() if r["id"] == pid]
    if not live:
        raise ValueError(f"{pid} has no logged attempt to change")
    last = live[-1]
    on = date.fromisoformat(last["date"])
    append(make_undo(pid, on))
    append(make_entry(pid, outcome, on, mistake, note=note))
    return last


def undo(pid: int) -> dict:
    live = [r for r in entries() if r["id"] == pid]
    if not live:
        raise ValueError(f"{pid} has no logged attempt to undo")
    last = live[-1]
    append(make_undo(pid, date.fromisoformat(last["date"])))
    return last


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
