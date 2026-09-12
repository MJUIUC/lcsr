"""lcsr -- run the 18-week DSA curriculum's daily loop."""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from . import curriculum as cur
from . import settings as cfg
from .plan import (export_csv, foundations_left, intake_week, metrics,
                   todays_plan)
from .schedule import SOLVED, STUCK
from .store import (LOG, MISTAKES, amend, append, current_sprint, make_entry,
                    replay, set_skipped, skipped_ids, start_sprint, undo)

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
    if on > date.today():
        raise SystemExit(f"cannot log an attempt for {on}: it is in the future")
    outcome = STUCK if a.stuck else SOLVED
    if a.mistake and outcome == SOLVED:
        raise SystemExit("--mistake only applies to a stuck attempt")
    # De-duplicate: `lcsr log 42 42` validated both against the SAME pre-loop
    # snapshot, so the second append slipped past the ladder-cleared guard and
    # fabricated a cold re-solve out of one sitting.
    ids = list(dict.fromkeys(a.ids))
    states = replay()
    for pid in ids:
        cur.loggable(pid)                  # curriculum OR frequent pool
        st = states.get(pid)
        if st is not None and st.done and not a.again:
            raise SystemExit(
                f"{pid} is already solved and schedules nothing. "
                f"re-run with --again to re-open it")
    for pid in ids:
        append(make_entry(pid, outcome, on, a.mistake, a.approach_min, a.note))
    states = replay()
    print(f"\nlogged {len(ids)} as {B}{outcome}{X} on {on}\n")
    for pid in ids:
        st = states[pid]
        print(f"  {label(cur.loggable(pid))}  "
              f"{f'{Y}re-solve {st.due}{X}' if st.due else f'{G}done{X}'}")
    print()


def cmd_today(a):
    on = parse_day(a.date)
    p = todays_plan(on)
    if on != date.today():
        print(f"\n{Y}preview of {on}: nothing can be logged for another day{X}")
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
    from .plan import intake_week
    wk = a.n or intake_week(set(replay()))
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


def cmd_up(a):
    """Idempotent: bring the UI up if it is not already, then open it."""
    import webbrowser

    from .server import is_up, start_detached
    url = f"http://{a.host}:{a.port}"
    if is_up(a.host, a.port):
        print(f"\n{G}already running{X} → {B}{url}{X}\n")
    elif start_detached(a.host, a.port):
        print(f"\n{G}started{X} → {B}{url}{X}   {D}(stop with `lcsr down`){X}\n")
    else:
        from .server import SERVERLOG
        raise SystemExit(f"failed to start; see {SERVERLOG}")
    if not a.no_open:
        webbrowser.open(url)


def cmd_down(a):
    from .server import is_up, stop
    if stop() or not is_up(a.host, a.port):
        print(f"\n{D}stopped{X}\n")
    else:
        print(f"\n{Y}still listening on {a.port}, not started by `lcsr up`?{X}\n")


def cmd_status(a):
    from .server import PIDFILE, is_up
    url = f"http://{a.host}:{a.port}"
    if is_up(a.host, a.port):
        pid = PIDFILE.read_text(encoding="utf-8").strip() if PIDFILE.exists() else "?"
        print(f"\n{G}up{X}   {url}   {D}pid {pid}{X}\n")
    else:
        print(f"\n{D}down{X}   {D}start it with `lcsr up`{X}\n")


def cmd_config(a):
    """Show or change the daily load."""
    named = {k: getattr(a, k) for k in ("foundations", "core", "reps", "daily_total")
             if getattr(a, k) is not None}
    if a.reset:
        cfg.reset()
    elif named:
        # "default" is how you clear one override from a shell, since there is no
        # way to pass null through argparse and 0 is a real, different value.
        cfg.update(**{k: (None if v == "default" else v) for k, v in named.items()})

    attempted = set(replay())
    d = cfg.describe(intake_week(attempted), foundations_left(attempted), cfg.load(),
                     current_sprint())
    eff, curric, st = d["effective"], d["curriculum"], d["settings"]

    sp = f"  {D}pass {d['sprint']} (+{d['pass_bonus']}/day){X}" if d["sprint"] > 1 else ""
    print(f"\n{B}daily load{X}  {D}week {d['week']}{X}{sp}")
    for tier in ("foundations", "core", "reps"):
        own = st[tier]
        src = f"{D}curriculum{X}" if own is None else f"{Y}you set {own}{X}"
        print(f"  {tier:<12} {B}{eff[tier]}{X}   {D}curriculum says {curric[tier]}{X}  {src}")
    total = sum(eff[t] for t in ("foundations", "core", "reps"))
    cap = "" if st["daily_total"] is None else f"   {Y}capped at {st['daily_total']}{X}"
    print(f"  {'total':<12} {B}{total}{X}{cap}")
    if d["is_default"]:
        print(f"\n{D}following the curriculum's own load. "
              f"change it with `lcsr config --core 3`{X}\n")
    else:
        print(f"\n{D}`lcsr config --core default` clears one, "
              f"`lcsr config --reset` clears all{X}\n")


def cmd_skip(a):
    """Set problems aside, or bring them back."""
    for pid in a.ids:
        cur.loggable(pid)
        set_skipped(pid, not a.undo)
        p = cur.loggable(pid)
        verb = f"{D}back on the list{X}" if a.undo else f"{Y}set aside{X}"
        print(f"  {pid:<5} {label(p)}  {verb}")
    print()


def cmd_skipped(a):
    ids = sorted(skipped_ids())
    if not ids:
        print(f"\n{D}nothing set aside. `lcsr skip 42` to set one aside{X}\n")
        return
    print(f"\n{B}set aside{X}  {D}{len(ids)} problem{'s' if len(ids) != 1 else ''}{X}")
    for pid in ids:
        try:
            print(f"  {pid:<5} {label(cur.loggable(pid))}")
        except KeyError:
            print(f"  {pid:<5} {D}(not in the curriculum){X}")
    print(f"\n{D}`lcsr skip 42 --undo` puts one back{X}\n")


def cmd_sprint(a):
    """Start another pass over the curriculum, keeping every attempt."""
    states = replay()
    done = sum(1 for st in states.values() if st.done)
    total = len(cur.problems())
    if done < total and not a.force:
        left = total - done
        raise SystemExit(
            f"{left} of {total} problems are not finished yet.\n"
            f"Starting a new pass re-offers everything and drops the re-solves\n"
            f"currently scheduled. Pass --force if that is what you want.")
    mark = start_sprint()
    print(f"\n{G}pass {mark['sprint']} started{X}  {D}{mark['date']}{X}")
    print(f"{D}every problem is on offer again; nothing was deleted.{X}")
    print(f"{D}new problems a day go up by one. `lcsr today` to begin.{X}\n")


def cmd_export(a):
    text = export_csv() if a.format == "csv" else (
        LOG.read_text(encoding="utf-8") if LOG.exists() else "")
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"\n{G}wrote{X} {a.out}  {D}({len(text.splitlines())} lines){X}\n")
    else:
        sys.stdout.write(text)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lcsr", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def net(sp):
        sp.add_argument("--host", default="127.0.0.1")
        sp.add_argument("--port", type=int, default=8765)
        return sp

    p = net(sub.add_parser("up", help="start the web UI in the background and open it"))
    p.add_argument("--no-open", action="store_true")
    p.set_defaults(fn=cmd_up)

    p = net(sub.add_parser("down", help="stop the background web UI"))
    p.set_defaults(fn=cmd_down)

    p = net(sub.add_parser("status", help="is the web UI running?"))
    p.set_defaults(fn=cmd_status)

    p = net(sub.add_parser("serve", help="run the web UI in the foreground"))
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

    p = sub.add_parser("skip", help="set a problem aside, so it stops being offered")
    p.add_argument("ids", nargs="+", type=int)
    p.add_argument("--undo", action="store_true", help="put it back on the list")
    p.set_defaults(fn=cmd_skip)

    p = sub.add_parser("skipped", help="what you have set aside")
    p.set_defaults(fn=cmd_skipped)

    p = sub.add_parser("sprint", help="start another pass over the curriculum")
    p.add_argument("--force", action="store_true",
                   help="start even though the curriculum is not finished")
    p.set_defaults(fn=cmd_sprint)

    p = sub.add_parser("export", help="export your progress as CSV, or the raw log")
    p.add_argument("--format", choices=("csv", "jsonl"), default="csv")
    p.add_argument("--out", help="write to this file instead of stdout")
    p.set_defaults(fn=cmd_export)

    p = sub.add_parser("config", help="show or change how many new problems a day")
    for flag, dest in (("--foundations", "foundations"), ("--core", "core"),
                       ("--reps", "reps"), ("--total", "daily_total")):
        p.add_argument(flag, dest=dest, default=None,
                       help="a number, or `default` to follow the curriculum")
    p.add_argument("--reset", action="store_true", help="clear every override")
    p.set_defaults(fn=cmd_config)

    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except (KeyError, ValueError) as e:
        raise SystemExit(str(e).strip("'"))


if __name__ == "__main__":
    main()
