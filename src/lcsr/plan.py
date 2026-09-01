"""What to solve today, and the curriculum's three metrics.

Shared by the CLI and the web UI. Both front-ends must agree on what "due"
means, so the rule lives here once rather than being reimplemented per surface.
"""

from collections import Counter
from datetime import date

from . import curriculum as cur
from .schedule import SOLVED
from .store import entries, replay

# Per-day intake of NEW problems, from the load the curriculum states for itself:
# "~4-5/day in weeks 1-3 (the foundations are quick), ~3/day in weeks 4-11,
# ~3-4/day in weeks 12-16, plus the spaced re-solves." Reps start in week 3.
#
# Due re-solves are deliberately NOT counted against this. They are mandatory and
# the curriculum lists them as additional to the daily intake.
def allowance(week: int) -> dict[str, int]:
    if week <= 2:
        return {"foundations": 3, "core": 2, "reps": 0, "custom": 2}
    if week == 3:
        return {"foundations": 3, "core": 2, "reps": 1, "custom": 2}
    if week <= 11:
        return {"foundations": 0, "core": 2, "reps": 1, "custom": 2}
    return {"foundations": 0, "core": 2, "reps": 2, "custom": 2}


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
    rows = entries()
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

    # What today's intake has already used up. Only a problem's FIRST attempt
    # counts: a re-solve is a due review, which is tracked separately and does
    # not eat the day's quota for new material.
    first_seen: dict[int, str] = {}
    for r in rows:
        first_seen.setdefault(r["id"], r["date"])
    started_today: Counter[str] = Counter(
        cur.problems()[pid]["tier"]
        for pid, d in first_seen.items()
        if d == on.isoformat() and pid in cur.problems()
    )

    quota = allowance(wk)
    remaining = {t: max(0, n - started_today.get(t, 0)) for t, n in quota.items()}

    def pool(tier, week=None):
        """week=None means any; week='<=' means every week up to the current one.

        Reps use '<=' on purpose. The curriculum runs them weeks 3-16 and says
        they are "spread across the schedule by the interleave rule, not massed
        into their own week" -- so drawing only from the current week would
        strand weeks 1-2's reps permanently, and would mass each week's reps
        into that week, which is the blocked practice the whole tier exists to
        avoid. Oldest-first, so the backlog drains rather than growing.
        """
        def wanted(p):
            if week is None:
                return True
            if week == "<=":
                return p["week"] is not None and p["week"] <= wk
            return p["week"] == week

        rows_ = [p for p in cur.problems().values()
                 if p["id"] not in attempted and p["tier"] == tier and wanted(p)]
        rows_.sort(key=lambda p: (p["week"] or 0, p["order"]))
        return rows_

    def build(limit_by):
        out = []
        for title, tier, week in (
            ("Foundations", "foundations", None),
            (f"Week {wk} core", "core", wk),
            ("Reps — interleaved across weeks 1–%d" % wk, "reps", "<="),
            ("Added", "custom", None),
        ):
            n = limit_by(tier)
            if n <= 0:
                continue
            got = [p for p in pool(tier, week) if p["id"] not in taken][:n]
            taken.update(p["id"] for p in got)
            if got:
                out.append({"title": title, "problems": got})
        return out

    taken: set[int] = set()
    sections = build(lambda t: remaining.get(t, 0))
    # The next batch, offered behind a toggle once the day's intake is met, so
    # working ahead is a deliberate choice rather than an endlessly refilling list.
    ahead = build(lambda t: quota.get(t, 0))

    done_today = sum(started_today.values())
    target_today = sum(quota.values()) - quota.get("custom", 0)

    return {
        "date": on.isoformat(),
        "week": wk,
        "day": ((on - day_one()).days + 1) if day_one() else 1,
        "due": due,
        "sections": sections,
        "ahead": ahead,
        "done_today": done_today,
        "target_today": target_today,
        "resolves_today": sum(1 for r in rows if r["date"] == on.isoformat()
                              and first_seen.get(r["id"]) != on.isoformat()),
        "caught_up": not sections and not due,
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
            "note": r.get("note"), "ts": r.get("ts"), "can_undo": False,
        })
    # Only the most recent surviving attempt at a problem can be undone --
    # retraction cancels the latest, so offering it on an older row would
    # silently remove a different attempt than the one you clicked.
    latest: dict[int, dict] = {}
    for d in sorted(days):
        for e in days[d]:
            latest[e["id"]] = e
    for e in latest.values():
        e["can_undo"] = True

    out = []
    for d in sorted(days, reverse=True):
        es = days[d]
        out.append({
            "date": d, "entries": es,
            "solved": sum(1 for e in es if e["outcome"] == SOLVED),
            "stuck": sum(1 for e in es if e["outcome"] != SOLVED),
        })
    return {"days": out, "total": len(rows)}
