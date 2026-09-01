"""lcsr -- run the 18-week DSA curriculum's daily loop."""

import argparse
import sys
from collections import Counter
from datetime import date, timedelta

from . import curriculum as cur
from .schedule import SOLVED, STUCK
from .store import MISTAKES, append, entries, make_entry, replay

B, D, R, G, Y, X = "\033[1m", "\033[2m", "\033[31m", "\033[32m", "\033[33m", "\033[0m"
if not sys.stdout.isatty():
    B = D = R = G = Y = X = ""


def parse_day(s: str) -> date:
    s = s.strip().lower()
    today = date.today()
    if s in ("today", "t"):
        return today
    if s in ("yesterday", "y"):
        return today - timedelta(days=1)
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise SystemExit(f"bad date {s!r}: use today, yesterday, or YYYY-MM-DD")


def label(pid: int) -> str:
    p = cur.get(pid)
    tag = f"{R}H{X}" if p["hard"] else " "
    return f"{B}{pid:>5}{X} {p['title']:<46}{tag} {D}{p['tier']:<11} W{p['week'] or '-'}{X}"


def day_one() -> date | None:
    rows = entries()
    return date.fromisoformat(rows[0]["date"]) if rows else None


def current_week() -> int:
    start = day_one()
    if start is None:
        return 1
    return (date.today() - start).days // 7 + 1


# ---------------------------------------------------------------- commands

def cmd_log(a):
    on = parse_day(a.date)
    outcome = STUCK if a.stuck else SOLVED
    if a.mistake and outcome == SOLVED:
        raise SystemExit("--mistake only applies to a stuck attempt")
    for pid in a.ids:
        cur.get(pid)  # validate before writing anything
    for pid in a.ids:
        append(make_entry(pid, outcome, on, a.mistake, a.approach_min, a.note))
    states = replay()
    print(f"\nlogged {len(a.ids)} as {B}{outcome}{X} on {on}\n")
    for pid in a.ids:
        st = states[pid]
        when = f"{Y}re-solve {st.due}{X}" if st.due else f"{G}done{X}"
        print(f"  {label(pid)}  {when}")
    print()


def cmd_today(a):
    today = date.today()
    states = replay()
    wk = current_week()

    due = sorted((s for s in states.values() if s.due and s.due <= today),
                 key=lambda s: s.due)
    print(f"\n{B}Week {wk}{X} {D}·{X} {today}\n")

    if due:
        print(f"{B}Due re-solves{X} {D}(these come first){X}")
        for s in due:
            late = (today - s.due).days
            when = f"{R}{late}d late{X}" if late else f"{Y}today{X}"
            print(f"  {label(s.pid)}  {when}")
        print()

    attempted = set(states)
    fresh = [p for p in cur.problems().values() if p["id"] not in attempted]

    def show(title, rows, n):
        rows = rows[:n]
        if not rows:
            return
        print(f"{B}{title}{X}")
        for p in rows:
            print(f"  {label(p['id'])}")
        print()

    if wk <= 3:
        show("Foundations", [p for p in fresh if p["tier"] == "foundations"], 3)
    show(f"Week {wk} core", [p for p in fresh if p["tier"] == "core" and p["week"] == wk], 2)
    show(f"Week {wk} reps", [p for p in fresh if p["tier"] == "reps" and p["week"] == wk], 2)

    blocks = {p["block"]: p.get("cue") for p in cur.problems().values()
              if p["week"] == wk and p.get("cue")}
    for block, cue in blocks.items():
        print(f"{D}cue · {block}: {cue}{X}\n")


def cmd_stats(a):
    rows = entries()
    if not rows:
        raise SystemExit("nothing logged yet")
    states = replay(rows)
    start = day_one()

    attempted = len(states)
    first_try = sum(1 for s in states.values() if s.outcomes[0] == SOLVED)

    # Cold re-solve rate: of attempts that were a re-solve (not the first
    # attempt at that problem), how many were solved. The curriculum's headline
    # metric -- deliberately NOT "problems completed".
    seen: Counter[int] = Counter()
    resolves = [0, 0]
    for r in rows:
        if seen[r["id"]]:
            resolves[1] += 1
            resolves[0] += r["outcome"] == SOLVED
        seen[r["id"]] += 1

    print(f"\n{B}Day {(date.today() - start).days + 1}{X} {D}· started {start} · week {current_week()}{X}\n")
    print(f"  attempted            {attempted} of 314")
    print(f"  solved cold 1st try  {first_try}/{attempted}"
          f" {D}({first_try / attempted:.0%}){X}")
    if resolves[1]:
        rate = resolves[0] / resolves[1]
        col = G if rate > 0.70 else R
        print(f"  cold re-solve rate   {col}{rate:.0%}{X} {D}of {resolves[1]} re-solves · target >70%{X}")
    else:
        print(f"  cold re-solve rate   {D}-- no re-solves due yet{X}")

    mistakes = Counter(r["mistake"] for r in rows if r.get("mistake"))
    if mistakes:
        print(f"\n  {B}mistake classes{X}")
        for m, n in mistakes.most_common():
            print(f"    {m:<14} {'#' * n} {n}")
    else:
        print(f"\n  {D}no mistake classes logged{X}")

    approach = [r["approach_min"] for r in rows if r.get("approach_min")]
    if approach:
        print(f"\n  time to approach     {sum(approach) / len(approach):.1f} min avg"
              f" {D}· target <5 by week 10{X}")
    print()


def cmd_cues(a):
    rows = cur.cues()
    print(f"\n{B}Cue -> pattern{X} {D}· cover the right column, fill it from memory{X}\n")
    for i, c in enumerate(rows, 1):
        print(f"{i:>3}. {c['says']}")
        if a.answers:
            print(f"     {G}{c['reach_for']}{X}")
    if not a.answers:
        print(f"\n{D}run with --answers to check{X}")
    print()


def cmd_week(a):
    wk = a.n or current_week()
    ps = [p for p in cur.problems().values() if p["week"] == wk]
    if not ps:
        raise SystemExit(f"no week {wk}")
    print(f"\n{B}Week {wk} · {ps[0]['block']}{X}")
    print(f"{D}cue: {ps[0].get('cue', '')}{X}\n")
    states = replay()
    for role in ("core", "reps"):
        rows = [p for p in ps if p["role"] == role]
        if not rows:
            continue
        print(f"{B}{role.upper()}{X}")
        for p in rows:
            st = states.get(p["id"])
            mark = f"{G}v{X}" if st and st.done else (f"{Y}~{X}" if st else " ")
            arrow = f"{D}->{X}" if p["immediately_after_prev"] else "  "
            print(f"  {mark} {arrow} {label(p['id'])}")
        print()


def cmd_show(a):
    p = cur.get(a.id)
    print(f"\n{B}{p['id']} {p['title']}{X}{'  ' + R + 'HARD' + X if p['hard'] else ''}")
    print(f"{D}{p['tier']} · week {p['week']} · {p['block']}{X}")
    if p.get("cue"):
        print(f"\n{B}cue:{X} {p['cue']}")
    print(f"\n{D}{cur.url(p['id'])}{X}")
    print(f"\n{Y}Name the pattern and the target complexity before writing code.{X}\n")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lcsr", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("log", help="record attempts")
    p.add_argument("ids", nargs="+", type=int)
    p.add_argument("--date", default="today", help="today | yesterday | YYYY-MM-DD")
    p.add_argument("--stuck", action="store_true", help="needed the editorial")
    p.add_argument("--mistake", choices=MISTAKES)
    p.add_argument("--approach-min", type=float, help="minutes to the correct approach")
    p.add_argument("--note", help="one line: the cue -> the pattern")
    p.set_defaults(fn=cmd_log)

    p = sub.add_parser("today", help="what to solve now")
    p.set_defaults(fn=cmd_today)

    p = sub.add_parser("stats", help="the three metrics")
    p.set_defaults(fn=cmd_stats)

    p = sub.add_parser("cues", help="self-test the cue table")
    p.add_argument("--answers", action="store_true")
    p.set_defaults(fn=cmd_cues)

    p = sub.add_parser("week", help="show a week's blocks")
    p.add_argument("n", nargs="?", type=int)
    p.set_defaults(fn=cmd_week)

    p = sub.add_parser("show", help="show one problem and its cue")
    p.add_argument("id", type=int)
    p.set_defaults(fn=cmd_show)

    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except KeyError as e:
        raise SystemExit(str(e).strip("'"))


if __name__ == "__main__":
    main()
