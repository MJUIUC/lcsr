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


def state_of(states: dict, pid: int) -> dict:
    """One problem's status, in the shape the UI wants.

    'learning' means it is in the +3/+10/+30 ladder -- attempted and not yet
    cleared. It is deliberately distinct from 'new': a problem you failed once
    and a problem you have never opened are not the same thing to look at.
    """
    st = states.get(pid)
    if st is None:
        return {"status": "new", "attempts": 0}
    return {
        "status": "done" if st.done else "learning",
        "attempts": st.attempts,
        "box": st.box,
        "due": st.due.isoformat() if st.due else None,
        "last": st.last.isoformat() if st.last else None,
        "outcomes": st.outcomes,
    }


def curriculum_view() -> dict:
    """Every problem in the curriculum, grouped the way the PDF groups them."""
    states = replay()
    allp = sorted(cur.problems().values(), key=lambda p: p["order"])

    def deco(p):
        return {**p, "url": cur.url(p["id"]), "state": state_of(states, p["id"])}

    def progress(rows):
        done = sum(1 for r in rows if r["state"]["status"] == "done")
        return {"done": done, "total": len(rows)}

    groups = []

    found = [deco(p) for p in allp if p["tier"] == "foundations"]
    blocks = {}
    for p in found:
        blocks.setdefault(p["block"], []).append(p)
    groups.append({
        "key": "foundations", "title": "Tier 0 · Foundations",
        "subtitle": "weeks 1–3 · prerequisite fluency, not curriculum",
        "progress": progress(found),
        "blocks": [{"title": k, "problems": v} for k, v in blocks.items()],
    })

    for wk in range(1, 17):
        rows = [deco(p) for p in allp if p["week"] == wk and p["tier"] in ("core", "reps")]
        if not rows:
            continue
        groups.append({
            "key": f"week-{wk}", "week": wk, "title": rows[0]["block"],
            "subtitle": rows[0].get("cue") or "",
            "progress": progress(rows),
            "blocks": [{"title": role.upper(),
                        "problems": [r for r in rows if r["role"] == role]}
                       for role in ("core", "reps")
                       if any(r["role"] == role for r in rows)],
        })

    groups.append({
        "key": "consolidation", "title": "Weeks 17–18 · Consolidation",
        "subtitle": "no new problems · random draw across all sixteen blocks, "
                    "the failed-problem queue, two timed mocks per week",
        "progress": {"done": 0, "total": 0}, "blocks": [], "note": True,
    })

    stretch = [deco(p) for p in allp if p["tier"] == "stretch"]
    groups.append({
        "key": "stretch", "title": "Tier 3 · Stretch",
        "subtitle": "weeks 12–18 · only for a hard bar · cut this first",
        "progress": progress(stretch),
        "blocks": [{"title": "", "problems": stretch}],
    })

    extra = [deco(p) for p in allp if p["tier"] == "custom"]
    if extra:
        groups.append({
            "key": "added", "title": "Added", "subtitle": "your own problems",
            "progress": progress(extra),
            "blocks": [{"title": "", "problems": extra}],
        })

    return {"groups": groups, "overall": progress([deco(p) for p in allp])}


def history_view() -> dict:
    """Every attempt, newest day first."""
    rows = entries()
    days: dict[str, list] = {}
    for r in rows:
        p = cur.problems().get(r["id"], {"title": f"#{r['id']}", "hard": False,
                                         "tier": "?", "week": None})
        days.setdefault(r["date"], []).append({
            "id": r["id"], "title": p["title"], "hard": p.get("hard", False),
            "tier": p.get("tier"), "week": p.get("week"),
            "url": cur.url(r["id"]) if r["id"] in cur.problems() else None,
            "outcome": r["outcome"], "mistake": r.get("mistake"),
            "note": r.get("note"), "ts": r.get("ts"),
        })
    out = []
    for d in sorted(days, reverse=True):
        es = days[d]
        out.append({
            "date": d, "entries": es,
            "solved": sum(1 for e in es if e["outcome"] == SOLVED),
            "stuck": sum(1 for e in es if e["outcome"] != SOLVED),
        })
    return {"days": out, "total": len(rows)}
