"""lcsr -- run the 18-week DSA curriculum's daily loop."""

import argparse
import sys
from datetime import date, timedelta

from . import curriculum as cur
from .plan import metrics, todays_plan
from .schedule import SOLVED, STUCK
from .store import MISTAKES, amend, append, make_entry, replay, undo

B, D, R, G, Y, X = "\033[1m", "\033[2m", "\033[31m", "\033[32m", "\033[33m", "\033[0m"
if not sys.stdout.isatty():
    B = D = R = G = Y = X = ""


def parse_day(s: str) -> date:
    s = s.strip().lower()
    if s in ("today", "t"):
        return date.today()
    if s in ("yesterday", "y"):
        return date.today() - timedelta(days=1)
    if s in ("tomorrow", "tm"):
        return date.today() + timedelta(days=1)
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise SystemExit(f"bad date {s!r}: use today, yesterday, or YYYY-MM-DD")


def label(p: dict) -> str:
    tag = f"{R}H{X}" if p["hard"] else " "
    return (f"{B}{p['id']:>5}{X} {p['title'][:46]:<46}{tag} "
            f"{D}{p['tier']:<11} W{p['week'] or '-'}{X}")


# ---------------------------------------------------------------- commands

def cmd_log(a):
    on = parse_day(a.date)
    outcome = STUCK if a.stuck else SOLVED
    if a.mistake and outcome == SOLVED:
        raise SystemExit("--mistake only applies to a stuck attempt")
    states = replay()
    for pid in a.ids:
        cur.loggable(pid)                  # curriculum OR frequent pool
        st = states.get(pid)
        if st is not None and st.done and not a.again:
            raise SystemExit(
                f"{pid} is already solved and schedules nothing — "
                f"re-run with --again to re-open it")
    for pid in a.ids:
        append(make_entry(pid, outcome, on, a.mistake, a.approach_min, a.note))
    states = replay()
    print(f"\nlogged {len(a.ids)} as {B}{outcome}{X} on {on}\n")
    for pid in a.ids:
        st = states[pid]
        print(f"  {label(cur.loggable(pid))}  "
              f"{f'{Y}re-solve {st.due}{X}' if st.due else f'{G}done{X}'}")
    print()


def cmd_today(a):
    on = parse_day(a.date)
    p = todays_plan(on)
    if on != date.today():
        print(f"\n{Y}preview of {on} — nothing can be logged for another day{X}")
    print(f"\n{B}Day {p['day']} · Week {p['week']}{X} {D}·{X} {p['date']}\n")
    if p["due"]:
        print(f"{B}{Y}Due re-solves{X} {D}(these come first){X}")
        for q in p["due"]:
            late = q["days_late"]
            print(f"  {label(q)}  "
                  f"{f'{R}{late}d late{X}' if late else f'{Y}today{X}'}")
        print()
    for s in p["sections"]:
        print(f"{B}{s['title']}{X}")
        for q in s["problems"]:
            print(f"  {label(q)}")
        print()
    if not p["due"] and not p["sections"]:
        print(f"{D}nothing queued{X}\n")


def cmd_stats(a):
    m = metrics()
    if not m.get("attempted"):
        raise SystemExit("nothing logged yet")
    print(f"\n{B}Day {m['day']} · week {m['week']}{X}\n")
    print(f"  attempted            {m['attempted']} of {m['total']}")
    print(f"  solved cold 1st try  {m['first_try']}/{m['attempted']}"
          f" {D}({m['first_try'] / m['attempted']:.0%}){X}")
    if m["resolve_rate"] is None:
        print(f"  cold re-solve rate   {D}-- no re-solves due yet{X}")
    else:
        col = G if m["resolve_rate"] > 0.70 else R
        print(f"  cold re-solve rate   {col}{m['resolve_rate']:.0%}{X}"
              f" {D}of {m['resolve_n']} re-solves · target >70%{X}")
    if m["mistakes"]:
        print(f"\n  {B}mistake classes{X}")
        for k, n in sorted(m["mistakes"].items(), key=lambda kv: -kv[1]):
            print(f"    {k:<14} {'#' * n} {n}")
    else:
        print(f"\n  {D}no mistake classes logged{X}")
    if m["approach_avg"]:
        print(f"\n  time to approach     {m['approach_avg']:.1f} min avg"
              f" {D}· target <5 by week 10{X}")
    print()


def cmd_cues(a):
    print(f"\n{B}Cue -> pattern{X} {D}· cover the right column, fill it from memory{X}\n")
    for i, c in enumerate(cur.cues(), 1):
        print(f"{i:>3}. {c['says']}")
        if a.answers:
            print(f"     {G}{c['reach_for']}{X}")
    if not a.answers:
        print(f"\n{D}run with --answers to check{X}")
    print()


def cmd_week(a):
    from .plan import current_week
    wk = a.n or current_week()
    ps = sorted((p for p in cur.problems().values() if p["week"] == wk),
                key=lambda p: p["order"])
    if not ps:
        raise SystemExit(f"no week {wk}")
    print(f"\n{B}Week {wk} · {ps[0]['block']}{X}")
    print(f"{D}cue: {ps[0].get('cue') or ''}{X}\n")
    states = replay()
    for role in ("core", "reps"):
        rows = [p for p in ps if p["role"] == role]
        if not rows:
            continue
        print(f"{B}{role.upper()}{X}")
        for p in rows:
            st = states.get(p["id"])
            mark = f"{G}v{X}" if st and st.done else (f"{Y}~{X}" if st else " ")
            print(f"  {mark} {f'{D}->{X}' if p['immediately_after_prev'] else '  '} {label(p)}")
        print()


def cmd_show(a):
    p = cur.get(a.id)
    print(f"\n{B}{p['id']} {p['title']}{X}{'  ' + R + 'HARD' + X if p['hard'] else ''}")
    print(f"{D}{p['tier']} · week {p['week']} · {p['block']}{X}")
    if p.get("cue"):
        print(f"\n{B}cue:{X} {p['cue']}")
    print(f"\n{D}{cur.url(p['id'])}{X}")
    print(f"\n{Y}Name the pattern and the target complexity before writing code.{X}\n")


def cmd_add(a):
    p = cur.add(a.id, a.title, week=a.week, hard=a.hard,
                block=a.block or "Added", cue=a.cue)
    print(f"\nadded {label(p)}\n{D}{cur.url(p['id'])}{X}\n")


def cmd_amend(a):
    outcome = STUCK if a.stuck else SOLVED
    for pid in a.ids:
        cur.loggable(pid)
    for pid in a.ids:
        was = amend(pid, outcome, a.mistake if a.stuck else None, a.note)
        st = replay()[pid]
        where = f"{G}done{X}" if st.done else f"{Y}returns {st.due}{X}"
        print(f"\n{was['outcome']} -> {B}{outcome}{X} on {was['date']} for "
              f"{label(cur.loggable(pid))}\n  now: {where}\n")


def cmd_undo(a):
    for pid in a.ids:
        was = undo(pid)
        st = replay().get(pid)
        where = "not attempted" if st is None else (
            f"{G}done{X}" if st.done else f"{Y}returns {st.due}{X}")
        print(f"\nundid {was['outcome']} on {was['date']} for "
              f"{label(cur.loggable(pid))}\n  now: {where}\n")


def cmd_serve(a):
    from .server import serve
    serve(a.host, a.port, open_browser=not a.no_open)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lcsr", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("serve", help="open the web UI")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-open", action="store_true")
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser("log", help="record attempts")
    p.add_argument("ids", nargs="+", type=int)
    p.add_argument("--date", default="today", help="today | yesterday | YYYY-MM-DD")
    p.add_argument("--stuck", action="store_true", help="needed the editorial")
    p.add_argument("--mistake", choices=MISTAKES)
    p.add_argument("--approach-min", type=float)
    p.add_argument("--note")
    p.add_argument("--again", action="store_true",
                   help="re-open a problem that is already solved")
    p.set_defaults(fn=cmd_log)

    p = sub.add_parser("amend", help="change the most recent attempt's outcome")
    p.add_argument("ids", nargs="+", type=int)
    p.add_argument("--stuck", action="store_true", help="change it to stuck")
    p.add_argument("--mistake", choices=MISTAKES)
    p.add_argument("--note")
    p.set_defaults(fn=cmd_amend)

    p = sub.add_parser("undo", help="retract the most recent attempt")
    p.add_argument("ids", nargs="+", type=int)
    p.set_defaults(fn=cmd_undo)

    p = sub.add_parser("today", help="what to solve now")
    p.add_argument("--date", default="today",
                   help="preview another day: tomorrow | YYYY-MM-DD")
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

    p = sub.add_parser("add", help="add your own problem")
    p.add_argument("id", type=int)
    p.add_argument("title")
    p.add_argument("--week", type=int)
    p.add_argument("--block")
    p.add_argument("--cue")
    p.add_argument("--hard", action="store_true")
    p.set_defaults(fn=cmd_add)

    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except (KeyError, ValueError) as e:
        raise SystemExit(str(e).strip("'"))


if __name__ == "__main__":
    main()
