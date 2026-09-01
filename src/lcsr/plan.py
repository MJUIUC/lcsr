"""What to solve today, and the curriculum's three metrics.

Shared by the CLI and the web UI. Both front-ends must agree on what "due"
means, so the rule lives here once rather than being reimplemented per surface.
"""

from collections import Counter
from datetime import date

from . import curriculum as cur
from .schedule import SOLVED
from .store import entries, replay

# per-day intake, from the curriculum's stated load
DAILY = {"foundations": 3, "core": 2, "reps": 2, "custom": 3, "stretch": 1}


def day_one() -> date | None:
    rows = entries()
    return date.fromisoformat(rows[0]["date"]) if rows else None


def current_week(on: date | None = None) -> int:
    start = day_one()
    if start is None:
        return 1
    return ((on or date.today()) - start).days // 7 + 1


def todays_plan(on: date | None = None) -> dict:
    on = on or date.today()
    states = replay()
    wk = current_week(on)
    attempted = set(states)

    due = [
        {**cur.get(s.pid),
         "due": s.due.isoformat(),
         "days_late": (on - s.due).days,
         "box": s.box,
         "attempts": s.attempts}
        for s in sorted((s for s in states.values() if s.due and s.due <= on),
                        key=lambda s: s.due)
    ]

    def fresh(tier, week=None):
        rows = [p for p in cur.problems().values()
                if p["id"] not in attempted and p["tier"] == tier
                and (week is None or p["week"] == week)]
        rows.sort(key=lambda p: (p["week"] or 0, p["order"]))
        return rows[:DAILY[tier]]

    sections = []
    if wk <= 3:
        sections.append({"title": "Foundations", "problems": fresh("foundations")})
    sections.append({"title": f"Week {wk} core", "problems": fresh("core", wk)})
    sections.append({"title": f"Week {wk} reps", "problems": fresh("reps", wk)})
    # Problems you added yourself are not tied to a week, so they surface here
    # rather than never -- otherwise `lcsr add` would write a row nothing reads.
    sections.append({"title": "Added", "problems": fresh("custom")})

    return {
        "date": on.isoformat(),
        "week": wk,
        "day": ((on - day_one()).days + 1) if day_one() else 1,
        "due": due,
        "sections": [s for s in sections if s["problems"]],
        "metrics": metrics(on),
    }


def metrics(on: date | None = None) -> dict:
    """The three the curriculum names. 'Problems completed' is deliberately absent."""
    rows = entries()
    if not rows:
        return {"attempted": 0, "total": len(cur.problems())}
    states = replay(rows)

    # Cold re-solve rate: of attempts that were NOT the first at that problem,
    # how many were solved. This is the headline metric, target >70%.
    seen: Counter[int] = Counter()
    resolved = attempts = 0
    for r in rows:
        if seen[r["id"]]:
            attempts += 1
            resolved += r["outcome"] == SOLVED
        seen[r["id"]] += 1

    approach = [r["approach_min"] for r in rows if r.get("approach_min")]
    return {
        "attempted": len(states),
        "total": len(cur.problems()),
        "first_try": sum(1 for s in states.values() if s.outcomes[0] == SOLVED),
        "resolve_rate": (resolved / attempts) if attempts else None,
        "resolve_n": attempts,
        "mistakes": dict(Counter(r["mistake"] for r in rows if r.get("mistake"))),
        "approach_avg": (sum(approach) / len(approach)) if approach else None,
        "day": ((on or date.today()) - day_one()).days + 1,
        "week": current_week(on),
    }
