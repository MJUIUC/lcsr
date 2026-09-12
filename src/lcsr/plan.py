"""What to solve today, and the curriculum's three metrics.

Shared by the CLI and the web UI. Both front-ends must agree on what "due"
means, so the rule lives here once rather than being reimplemented per surface.
"""

from collections import Counter
from datetime import date, timedelta

from . import curriculum as cur
from . import settings as cfg
from .schedule import SOLVED
from .settings import allowance          # re-exported: part of plan's surface
from .store import (current_entries, current_sprint, entries, raw_entries,
                    replay, skipped_ids, skipped_on, stream)


def day_one() -> date | None:
    """Day 1 of the pass in progress, not of the log.

    After starting a second pass, "day 47" of a finished run is not a useful
    thing to print above a week-1 queue.
    """
    rows = current_entries()
    return date.fromisoformat(rows[0]["date"]) if rows else None


# --- neglect handling -------------------------------------------------------
# Re-solves surfaced in one day. They carry forward indefinitely when missed, so
# without a cap a fortnight away returns a wall of fifty and the day reads as
# hopeless. Most-overdue first; the rest stay due and surface as these clear.
MAX_DUE_SHOWN = 8

# When this many re-solves are outstanding, new problems stop being issued. The
# curriculum's own rule when the cold re-solve rate misses is "you are moving too
# fast -- cut Reps and Stretch before you cut Core, and raise the number of
# spaced re-solves". Piling new material on top of an unworked backlog is the
# fastest way to make that number worse.
BACKLOG_PAUSE = 12


def foundations_left(attempted: set[int]) -> int:
    return sum(1 for p in cur.problems().values()
               if p["tier"] == "foundations" and p["id"] not in attempted)


def intake_week(attempted: set[int], skipped: set[int] | None = None) -> int:
    """The week whose material you are actually on, from progress not calendar.

    This is the ONLY notion of week. An earlier version also had a calendar week
    (elapsed days over seven) and the two disagreed constantly: the calendar drove
    the labels while progress drove the content, so a fast start reported "running
    ahead of schedule" forever and a long absence reported week 6 while zeroing
    the foundations allowance -- stranding 42 unattempted problems, because
    elapsed weeks only ever advance.

    Progress cannot disagree with progress. Elapsed time is still reported, as
    idle_days and pace, where it is descriptive rather than prescriptive.
    """
    core = sorted((p for p in cur.problems().values() if p["tier"] == "core"),
                  key=lambda p: p["order"])
    # A problem you set aside must not freeze the week. Without this, skipping
    # one core problem pins intake_week() to its week forever and the daily mix
    # never advances again.
    done = attempted | (skipped or set())
    nxt = next((p for p in core if p["id"] not in done), None)
    return max(1, nxt["week"] or 1) if nxt else 16


def last_activity() -> date | None:
    rows = current_entries()
    return date.fromisoformat(rows[-1]["date"]) if rows else None


def pace(on: date, window: int = 14) -> dict:
    """New problems started per day over a trailing window.

    Replaces the calendar-week comparison. "Week" now means where you are in the
    material, so there is no schedule to be ahead of or behind -- what actually
    matters is the rate, and the rate is measurable.
    """
    first_seen: dict[int, str] = {}
    for r in current_entries():
        first_seen.setdefault(r["id"], r["date"])
    start = (on - timedelta(days=window - 1)).isoformat()
    started = sum(1 for d in first_seen.values() if start <= d <= on.isoformat())
    d1 = day_one()
    # Divide by days actually elapsed, or a four-day-old log reads as 14 days slow.
    elapsed = min(window, (on - d1).days + 1) if d1 else window
    return {"per_day": (started / elapsed) if elapsed else 0.0,
            "started": started, "window_days": elapsed}


def projection(on: date, attempted: set[int], per_day: float,
               skipped: set[int] | None = None) -> dict:
    """When the curriculum finishes at the observed rate.

    Counts the tiers the curriculum treats as required -- stretch is explicitly
    optional and custom additions are yours, so neither belongs in a completion
    estimate.
    """
    # Problems you have set aside are not on the path to finishing, so counting
    # them would keep promising a date for work you have said you are not doing.
    done = attempted | (skipped or set())
    remaining = sum(1 for p in cur.problems().values()
                    if p["tier"] in ("foundations", "core", "reps")
                    and p["id"] not in done)
    if per_day <= 0:
        return {"remaining": remaining, "days_left": None, "finish": None}
    days_left = int(remaining / per_day + 0.999)
    return {"remaining": remaining, "days_left": days_left,
            "finish": (on + timedelta(days=days_left)).isoformat()}


def _started_on(first_seen: dict[int, str], day: date,
                also: set[int] | None = None) -> Counter:
    """New problems whose FIRST attempt fell on `day`, by tier.

    `also` are problems set aside that day. They count against the day's intake
    too: a skip takes a problem off the queue, and if it did not consume the
    slot it vacated, the queue would refill and skipping would be punished with
    a replacement problem.
    """
    probs = cur.problems()
    got = Counter(probs[pid]["tier"] for pid, d in first_seen.items()
                  if d == day.isoformat() and pid in probs)
    for pid in (also or ()):
        if pid in probs:
            got[probs[pid]["tier"]] += 1
    return got


def todays_plan(on: date | None = None, today: date | None = None) -> dict:
    """`today` is the CALLER's calendar day, not the process's.

    The hosted function runs in UTC, where date.today() is nobody's today. The
    browser supplies its own local day so "is this a preview of a future date"
    is answered in the user's timezone rather than the server's.
    """
    today = today or date.today()
    on = on or today
    states = replay()
    rows = current_entries()
    attempted = set(states)
    skipped = skipped_ids()
    # Set aside TODAY, specifically.
    #
    # GOTCHA: skipping must never hand you more work than you already had.
    # intake_week() treats a skipped problem as passed, so setting aside the last
    # core problem of a week advanced the week mid-day; week 3 starts reps, so a
    # rep appeared out of nowhere, and the freed core slot refilled from the new
    # week. Skipping the last item of the day produced two new ones.
    #
    # So today's skips do not move the week. They still come off the queue, they
    # still consume the slot they vacated, and the week advances tomorrow.
    skipped_today = skipped_on(on)
    sprint = current_sprint()
    # ONE notion of week: where you are in the material. The calendar week was a
    # second, competing one -- it drove the label while progress drove the
    # content, so finishing week 1's seven core problems in two days reported
    # "running ahead of schedule" indefinitely. There is no schedule to be ahead
    # of; there is a sequence and a rate.
    wk = intake_week(attempted, skipped - skipped_today)

    prefs = cfg.load()

    def quota_for(week: int) -> dict:
        """The curriculum's load, the foundations keep-alive, and your overrides.

        All four rules are composed by settings.daily_quota(), which has the
        truth table. Recomputed per call rather than cached because
        foundations_left() shrinks as the day is worked.
        """
        return cfg.daily_quota(week, foundations_left(attempted), prefs, sprint)
    is_future = on > today

    first_seen: dict[int, str] = {}
    for r in rows:
        first_seen.setdefault(r["id"], r["date"])

    if is_future:
        # A previewed day sits behind every day between now and then, each of
        # which consumes its own intake. Without this offset every future day
        # shows the same list -- day+2 repeats day+1 forever.
        skip: Counter = Counter()
        skip.update({t: max(0, n - _started_on(first_seen, today, skipped_on(today)).get(t, 0))
                     for t, n in quota_for(wk).items()})
        # Every day between now and then consumes a full intake, and nothing in
        # that quota varies by day, so this is a multiplication rather than a
        # loop. It used to iterate once per calendar day with `on` taken straight
        # from a request, which made a date a few years out cost minutes of CPU.
        whole_days = max(0, (on - today).days - 1)
        if whole_days:
            skip.update({t: n * whole_days for t, n in quota_for(wk).items()})
        quota = quota_for(wk)
        remaining = dict(quota)
        started_today = Counter()
        # Only re-solves falling due on that exact day: anything due earlier is
        # assumed cleared on its own day, so carrying it forward would be wrong.
        due_states = [s for s in states.values()
                      if s.due and s.due == on and s.pid not in skipped]
    else:
        skip = Counter()
        quota = quota_for(wk)
        started_today = _started_on(first_seen, on, skipped_today)
        remaining = {t: max(0, n - started_today.get(t, 0)) for t, n in quota.items()}
        due_states = [s for s in states.values()
                      if s.due and s.due <= on and s.pid not in skipped]

    # Most overdue first: a re-solve 30 days late has decayed furthest and is the
    # one the schedule is most wrong about.
    due_sorted = sorted(due_states, key=lambda s: (s.due, s.pid))
    backlog = len(due_sorted)
    due = [
        {**cur.loggable(s.pid), "due": s.due.isoformat(),
         "days_late": (on - s.due).days, "box": s.box, "attempts": s.attempts}
        for s in due_sorted[:MAX_DUE_SHOWN]
    ]
    due_hidden = max(0, backlog - MAX_DUE_SHOWN)
    pc = pace(on)
    # Past the threshold, new material is withheld rather than stacked on top.
    paused = backlog >= BACKLOG_PAUSE and not is_future

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
                 if p["id"] not in attempted and p["id"] not in skipped
                 and p["tier"] == tier and wanted(p)]
        rows_.sort(key=lambda p: (p["week"] or 0, p["order"]))
        return rows_

    def core_title(got):
        """Name the section after the weeks actually drawn.

        Core is drawn in document order, so a day can straddle two blocks. The
        label just says which -- no judgement about pace attached, because the
        week IS the progress and cannot disagree with it.
        """
        weeks = sorted({p["week"] for p in got if p["week"]})
        if not weeks:
            return "Core"
        if len(weeks) == 1:
            return f"Week {weeks[0]} core"
        return f"Core, weeks {weeks[0]} to {weeks[-1]}"

    def build(limit_by):
        out = []
        for title, tier, week in (
            ("Foundations", "foundations", None),
            (None, "core", None),
            ("Reps, interleaved across weeks 1 to %d" % wk, "reps", "<="),
            ("Added", "custom", None),
        ):
            n = limit_by(tier)
            if n <= 0:
                continue
            off = skip.get(tier, 0)
            got = [p for p in pool(tier, week) if p["id"] not in taken][off:off + n]
            taken.update(p["id"] for p in got)
            if got:
                out.append({"title": title or core_title(got), "problems": got})
        return out

    taken: set[int] = set()
    sections = [] if paused else build(lambda t: remaining.get(t, 0))
    # The next batch, offered behind a toggle once the day's intake is met, so
    # working ahead is a deliberate choice rather than an endlessly refilling list.
    ahead = [] if (is_future or paused) else build(lambda t: quota.get(t, 0))

    # Count and target over the SAME tiers, or the header reads "6/5" for a day
    # that is not actually over quota. custom is excluded from both.
    counted = {t: n for t, n in started_today.items() if t != "custom"}
    done_today = sum(counted.values())
    target_today = sum(quota.values()) - quota.get("custom", 0)

    return {
        "date": on.isoformat(),
        "week": wk,
        "block": next((p["block"] for p in cur.problems().values()
                       if p["week"] == wk and p["tier"] == "core"), ""),
        # A date before the first attempt would otherwise report day 0 or negative.
        "day": max(1, (on - day_one()).days + 1) if day_one() else 1,
        "due": due,
        "due_hidden": due_hidden,
        "backlog": backlog,
        "paused": paused,
        "pause_at": BACKLOG_PAUSE,
        "pace": pc,
        "projection": projection(on, attempted, pc["per_day"], skipped),
        "idle_days": (on - last_activity()).days if last_activity() else 0,
        "sections": sections,
        "ahead": ahead,
        "done_today": done_today,
        "target_today": target_today,
        "resolves_today": sum(1 for r in rows if r["date"] == on.isoformat()
                              and first_seen.get(r["id"]) != on.isoformat()),
        "caught_up": (not sections and not due) and not is_future and not paused,
        "sprint": sprint,
        "skipped_count": len(skipped),
        "load": cfg.describe(wk, foundations_left(attempted), prefs, sprint),
        "metrics": metrics(on),
    }


def metrics(on: date | None = None) -> dict:
    """The three the curriculum names. 'Problems completed' is deliberately absent."""
    all_rows = current_entries()
    if not all_rows:
        return {"attempted": 0, "total": len(cur.problems()),
                "sprint": current_sprint(), "lifetime_attempts": len(entries())}
    # Scope to the curriculum. The log also carries attempts at frequent-only
    # problems, and folding those in would inflate "attempted" past the total and
    # quietly move the cold re-solve rate -- the metric the curriculum says
    # predicts performance.
    curric = cur.problems()
    rows = [r for r in all_rows if r["id"] in curric]
    if not rows:
        return {"attempted": 0, "total": len(curric),
                "sprint": current_sprint(), "lifetime_attempts": len(entries())}
    states = {k: v for k, v in replay(all_rows).items() if k in curric}

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
        "day": max(1, ((on or date.today()) - day_one()).days + 1),
        "week": intake_week(set(replay()), skipped_ids()),
        # Scoped to the pass in progress, like everything else here. The lifetime
        # figure is kept alongside so starting a new pass never looks like
        # losing the work.
        "sprint": current_sprint(),
        "lifetime_attempts": len(entries()),
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
    skipped = skipped_ids()
    allp = sorted(cur.problems().values(), key=lambda p: p["order"])

    def deco(p):
        return {**p, "url": cur.url(p["id"]),
                "state": {**state_of(states, p["id"]),
                          "skipped": p["id"] in skipped}}

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
        "subtitle": "weeks 1-3 · prerequisite fluency, not curriculum",
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
        "key": "consolidation", "title": "Weeks 17-18 · Consolidation",
        "subtitle": "no new problems · random draw across all sixteen blocks, "
                    "the failed-problem queue, two timed mocks per week",
        "progress": {"done": 0, "total": 0}, "blocks": [], "note": True,
    })

    stretch = [deco(p) for p in allp if p["tier"] == "stretch"]
    groups.append({
        "key": "stretch", "title": "Tier 3 · Stretch",
        "subtitle": "weeks 12-18 · only for a hard bar · cut this first",
        "progress": progress(stretch),
        "blocks": [{"title": "", "problems": stretch}],
    })

    # A tier of its own. They stay listed in their own week as well, with a
    # badge: removing them would quietly shrink that week's totals, and the
    # curriculum's counts are the one thing this tool does not rewrite.
    aside = [deco(p) for p in allp if p["id"] in skipped]
    if aside:
        groups.append({
            "key": "skipped", "title": "Tier 4 · Set aside",
            "subtitle": "not offered until you bring them back · "
                        "never counted as attempts",
            "progress": progress(aside),
            "blocks": [{"title": "", "problems": aside}],
        })

    extra = [deco(p) for p in allp if p["tier"] == "custom"]
    if extra:
        groups.append({
            "key": "added", "title": "Added", "subtitle": "your own problems",
            "progress": progress(extra),
            "blocks": [{"title": "", "problems": extra}],
        })

    return {"groups": groups, "overall": progress([deco(p) for p in allp])}


def _url_for(pid: int, probs: dict, freq: dict) -> str | None:
    """url_of() against already-built maps, so it is not rebuilt per row."""
    if pid in probs:
        return cur.url(pid)
    fq = freq.get(pid)
    return cur.leetcode_url(fq["slug"]) if fq else None


def history_view() -> dict:
    """Every attempt, newest day first."""
    rows = entries()
    # Resolved once. loggable() and url_of() each rebuild the merged problem dict,
    # so calling them per entry made this O(entries x problems): a long log spent
    # seconds rebuilding the same 324-entry mapping thousands of times.
    probs = cur.problems()
    freq = cur.frequent_index()
    days: dict[str, list] = {}
    for r in rows:
        p = probs.get(r["id"])
        if p is None:
            fq = freq.get(r["id"])
            p = ({**fq, "tier": "frequent", "week": None} if fq
                 else {"title": f"#{r['id']}", "hard": False, "tier": "?", "week": None})
        days.setdefault(r["date"], []).append({
            "id": r["id"], "title": p["title"], "hard": p.get("hard", False),
            "tier": p.get("tier"), "week": p.get("week"),
            "url": (_url_for(r["id"], probs, freq) if p.get("tier") != "?" else None),
            "outcome": r["outcome"], "mistake": r.get("mistake"),
            "note": r.get("note"), "ts": r.get("ts"), "can_undo": False,
        })
    # Only the most recent surviving attempt at a problem can be undone --
    # retraction cancels the latest, so offering it on an older row would
    # silently remove a different attempt than the one you clicked. And only
    # within the pass in progress: undo() refuses to reach into a finished one,
    # so offering the button there would just produce an error.
    undoable = {(r["id"], r.get("ts")) for r in current_entries()}
    latest: dict[int, dict] = {}
    for d in sorted(days):
        for e in days[d]:
            if (e["id"], e.get("ts")) in undoable:
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
    return {"days": out, "total": len(rows), "sprint": current_sprint(),
            # Rendered as a divider between passes, so a run that starts over
            # does not read as one long undifferentiated log.
            "sprints": [{"n": r["sprint"], "date": r["date"]}
                        for r in raw_entries() if "sprint" in r]}


# --- export -----------------------------------------------------------------

def export_table() -> tuple[list[str], list[list]]:
    """One row per curriculum problem, one column group per attempt.

    Deliberately the WHOLE log, every pass, not the current one: this is the
    thing you keep when you stop using the tool, and a pass boundary is a column
    rather than a filter. Problems never attempted are included too, because
    "what have I not touched" is most of the question being asked.
    """
    rows_by_pid: dict[int, list[dict]] = {}
    sprint_at: dict[str, int] = {}
    n = 1
    for r in stream():
        if "sprint" in r:
            n = r["sprint"]
            continue
        rows_by_pid.setdefault(r["id"], []).append({**r, "sprint": n})

    states = replay()
    # Capped. The header gets a column group per attempt at the most-attempted
    # problem, so a log with one problem attempted 17,000 times produced a 30 MB
    # CSV from a 1 MB request. Nothing real reaches 200 attempts at one problem.
    MAX_ATTEMPT_COLUMNS = 200
    widest = min(max((len(v) for v in rows_by_pid.values()), default=0),
                 MAX_ATTEMPT_COLUMNS)

    head = ["id", "title", "tier", "week", "block", "hard", "url",
            "status", "attempts", "box", "due", "first_attempt", "last_attempt"]
    for i in range(1, widest + 1):
        head += [f"attempt_{i}_date", f"attempt_{i}_outcome",
                 f"attempt_{i}_mistake", f"attempt_{i}_pass", f"attempt_{i}_note"]

    out = []
    for p in sorted(cur.problems().values(), key=lambda x: x["order"]):
        pid = p["id"]
        att = rows_by_pid.get(pid, [])
        st = states.get(pid)
        row = [
            pid, p["title"], p["tier"], p["week"] or "", p["block"],
            "yes" if p.get("hard") else "no", cur.url(pid),
            ("done" if st.done else "learning") if st else "new",
            len(att),
            "" if not st or st.box is None else st.box,
            st.due.isoformat() if st and st.due else "",
            att[0]["date"] if att else "",
            att[-1]["date"] if att else "",
        ]
        for a in att[:widest]:
            row += [a["date"], a["outcome"], a.get("mistake") or "",
                    a["sprint"], (a.get("note") or "").replace("\n", " ")]
        row += [""] * (len(head) - len(row))
        out.append(row)
    return head, out


def export_csv() -> str:
    import csv
    import io
    head, rows = export_table()
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(head)
    w.writerows(rows)
    return buf.getvalue()


def frequent_view() -> dict:
    """The frequently-asked pool, annotated against the curriculum and the log.

    Kept separate from the curriculum on purpose. The only crossing point is
    read-only: each problem says whether it is already in the curriculum and
    whether you have logged it, so a draw can skip what you have covered.
    """
    data = cur.frequent()
    curric = cur.problems()
    states = replay()

    rows = []
    for r in data["problems"]:
        pid = r["id"]
        in_cur = curric.get(pid)
        st = states.get(pid)
        rows.append({
            **r,
            "url": cur.leetcode_url(r["slug"]),
            "in_curriculum": bool(in_cur),
            "curriculum": ({"tier": in_cur["tier"], "week": in_cur["week"],
                            "block": in_cur["block"]} if in_cur else None),
            "attempted": st is not None,
            "solved": bool(st and st.done),
            "due": st.due.isoformat() if st and st.due else None,
            "attempts": st.attempts if st else 0,
        })

    return {
        "labels": data["labels"],
        "problems": rows,
        "stats": {
            "total": len(rows),
            "in_curriculum": sum(r["in_curriculum"] for r in rows),
            "only_here": sum(not r["in_curriculum"] for r in rows),
            "solved": sum(r["solved"] for r in rows),
            "paid": sum(r["paid"] for r in rows),
            "by_count": dict(sorted(Counter(r["count"] for r in rows).items())),
            "by_difficulty": dict(Counter(r["difficulty"] for r in rows)),
            "attempted": sum(r["attempted"] for r in rows),
            "due": sum(bool(r["due"]) for r in rows),
        },
    }
