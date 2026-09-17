"""Append-only attempt log, plus the projection of it into schedule state.

log.jsonl is the only record. Everything else -- due dates, boxes, the three
metrics -- is recomputed from it by replay(). Nothing is stored twice, so
nothing can drift out of sync, and the scheduling rule can be changed later
without invalidating the history.
"""

import contextvars
import json
import os
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .schedule import advance, EDITORIAL, NOTE

HOME = Path(os.environ.get("LCSR_HOME", Path.home() / ".lcsr"))
LOG = HOME / "log.jsonl"

MISTAKES = ("off-by-one", "invariant", "edge-case", "no-pattern")

# Every read-modify-write on the log runs under this. The server is a
# ThreadingHTTPServer, so two requests genuinely do run concurrently: without it,
# two logs of the same problem both read "not yet solved", both pass the
# already-solved gate and both append, advancing the ladder twice; and two amends
# both read the same "latest" attempt, so the second retracts a record the first
# had already replaced -- cancelling an unrelated older attempt.
# Reentrant because amend() calls entries() and append() while holding it.
LOCK = threading.RLock()


def atomic_write(path, text: str) -> None:
    """Replace a file's contents without ever exposing a partial one.

    A plain write truncates first, so a concurrent reader can see an empty or
    half-written file and a crash mid-write destroys the original.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# --- where the three pieces of user state live -----------------------------
#
# There are three: the log, the problems you added, and the daily-load overrides.
# Locally they are files under ~/.lcsr. On a serverless deploy there is no
# writable disk at all, so the browser holds them and posts them with each
# request. Nothing above this line knows the difference: plan.py, schedule.py and
# settings.py all operate on lists and dicts either way.

class FileBackend:
    """~/.lcsr. What the CLI and `lcsr serve` always use.

    Reads the module-level paths on every call rather than capturing them, so the
    monkeypatching every test does (store.LOG, curriculum.CUSTOM) keeps working.
    """

    stateless = False

    def read_log(self) -> str:
        return LOG.read_text(encoding="utf-8") if LOG.exists() else ""

    def append_log(self, entry: dict) -> None:
        HOME.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read_custom(self) -> list[dict]:
        from . import curriculum          # late: curriculum imports this module
        f = curriculum.CUSTOM
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []

    def write_custom(self, rows: list[dict]) -> None:
        from . import curriculum
        atomic_write(curriculum.CUSTOM, json.dumps(rows, indent=1, ensure_ascii=False))

    def read_settings(self) -> dict:
        f = HOME / "settings.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}

    def write_settings(self, data: dict) -> None:
        atomic_write(HOME / "settings.json", json.dumps(data, indent=1) + "\n")


@dataclass
class MemoryBackend:
    """State supplied by the client, for one request, and never retained.

    `appended` collects the log records a write produced. They go back in the
    response for the browser to persist, which is what keeps the log append-only
    on the client too: it accumulates the same jsonl the file would have, undo
    records and pass markers included, so an export still feeds the CLI.
    """

    stateless = True
    log: list[dict] = field(default_factory=list)
    custom: list[dict] = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    appended: list[dict] = field(default_factory=list)
    custom_written: bool = False
    settings_written: bool = False

    @classmethod
    def from_payload(cls, state) -> "MemoryBackend":
        state = state if isinstance(state, dict) else {}
        log = state.get("log")
        custom = state.get("custom")
        settings = state.get("settings")
        return cls(log=list(log) if isinstance(log, list) else [],
                   custom=list(custom) if isinstance(custom, list) else [],
                   settings=dict(settings) if isinstance(settings, dict) else {})

    def read_log(self) -> str:
        return "\n".join(json.dumps(r, ensure_ascii=False) for r in self.log)

    def append_log(self, entry: dict) -> None:
        self.log.append(entry)
        self.appended.append(entry)

    def read_custom(self) -> list[dict]:
        return list(self.custom)

    def write_custom(self, rows: list[dict]) -> None:
        self.custom = list(rows)
        self.custom_written = True

    def read_settings(self) -> dict:
        return dict(self.settings)

    def write_settings(self, data: dict) -> None:
        self.settings = dict(data)
        self.settings_written = True

    def patch(self) -> dict:
        """What the client must apply to its own copy."""
        out: dict = {}
        if self.appended:
            out["log_append"] = self.appended
        if self.custom_written:
            out["custom"] = self.custom
        if self.settings_written:
            out["settings"] = self.settings
        return out


# A ContextVar, not a global: it is per-thread and per-task, so the threaded
# local server and a serverless invocation both get isolation without a lock.
# Defaulting to None means the CLI needs no changes whatsoever.
_ACTIVE: contextvars.ContextVar = contextvars.ContextVar("lcsr_backend", default=None)


def backend():
    return _ACTIVE.get() or FileBackend()


def use(b):
    return _ACTIVE.set(b)


def release(token) -> None:
    _ACTIVE.reset(token)


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
    with LOCK:
        backend().append_log(entry)


def raw_entries() -> list[dict]:
    """Every line in the log, retractions included, in attempt order.

    Entries can be logged out of order (backfilling yesterday after today), and
    replay is order-dependent -- sort by the attempt date, not by insertion, or
    a backfill would be folded in as if it happened last.
    """
    rows = []
    # split("\n"), NOT splitlines(): append() terminates records with "\n", but
    # str.splitlines() also breaks on U+2028, U+2029, U+0085, \v, \f and \x1c-\x1e.
    # json.dumps(ensure_ascii=False) passes those through raw, so a note pasted
    # from Word (which emits U+2028 for a soft line break) would be written as one
    # line and read back as two unparseable halves -- permanently bricking every
    # read path, with the error naming a line number that is not the real boundary.
    for n, ln in enumerate(backend().read_log().split("\n"), 1):
        if not ln.strip():
            continue
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError as e:
            # Name the line. Skipping it silently would drop real attempts and
            # quietly change every metric; a raw JSONDecodeError names nothing.
            where = LOG if not backend().stateless else "the supplied log"
            raise ValueError(
                f"{where}:{n} is not valid JSON ({e.msg}). Fix or delete that line."
            ) from None
    return sorted(rows, key=_order_key)


def _order_key(r: dict):
    """Order by attempt date, then by the real instant the record was written.

    ts carries a UTC offset, and comparing those as strings is wrong whenever the
    offset changes: after a DST fall-back, "…T01:30:00+01:00" sorts AFTER
    "…T02:00:00+02:00" as text while happening 30 minutes earlier. Since a
    retraction cancels whatever the ordering says is latest, that made undo and
    amend cancel the wrong record. Compare instants instead.
    """
    ts = r.get("ts")
    try:
        when = datetime.fromisoformat(ts).astimezone(timezone.utc)
    except (TypeError, ValueError):
        when = datetime.min.replace(tzinfo=timezone.utc)   # legacy/missing ts sorts first
    return (r.get("date", ""), when)


def _live(with_marks: bool) -> list[dict]:
    """Attempts that still stand, with retractions applied.

    Undo appends a retraction rather than deleting a line: the file stays
    append-only, so a mis-logged attempt is recoverable and the record of what
    actually happened is never rewritten underneath you. A retraction cancels
    the most recent surviving attempt at that problem.

    Sprint markers carry no `id`, so they are skipped unless asked for. Every
    caller that reads r["id"] would raise on one otherwise, and there are a
    dozen of those.
    """
    alive: list[dict | None] = []
    positions: dict[int, list[int]] = {}
    for r in raw_entries():
        if "sprint" in r:
            if with_marks:
                alive.append(r)          # index bookkeeping below still lines up
            continue
        if "skip" in r:
            # Setting a problem aside is not an attempt at it. It must never
            # reach replay() (which would read r["outcome"] and raise) nor the
            # metrics, or declining the hard ones would quietly improve the cold
            # re-solve rate, which is the one number the curriculum says
            # predicts anything. See skipped_ids().
            continue
        pid = r["id"]
        if r.get("undo"):
            if positions.get(pid):
                alive[positions[pid].pop()] = None
            continue
        positions.setdefault(pid, []).append(len(alive))
        alive.append(r)
    return [r for r in alive if r is not None]


def entries() -> list[dict]:
    """Every surviving attempt, all passes. This is the history."""
    return _live(False)


def stream() -> list[dict]:
    """Surviving attempts plus sprint markers, in order. This is what replays."""
    return _live(True)


def make_skip(pid: int, on: date, skip: bool = True) -> dict:
    return {"ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "date": on.isoformat(), "id": pid, "skip": bool(skip)}


def set_skipped(pid: int, skip: bool = True) -> dict:
    """Set a problem aside, or bring it back. Appends either way.

    Toggling is a new record rather than a retraction of the old one, so the log
    keeps the fact that you set it aside on a date and changed your mind on
    another. Nothing here touches the ladder.
    """
    with LOCK:
        mark = make_skip(pid, date.today(), skip)
        append(mark)
        return mark


def skip_marks() -> dict[int, dict]:
    """The latest skip record per problem, in the pass you are on.

    Scoped to the current pass for the same reason schedule state is: a new pass
    puts every problem back on offer, and that has to include the ones you
    declined last time round. Declining them again is one click.

    The record is returned whole, not just the flag, because the DATE matters:
    a problem set aside today must not change the shape of today.
    """
    rows = raw_entries()
    cut = max((i for i, r in enumerate(rows) if "sprint" in r), default=-1)
    marks: dict[int, dict] = {}
    for r in rows[cut + 1:]:
        if "skip" in r:
            marks[r["id"]] = r
    return marks


def skipped_ids() -> set[int]:
    return {pid for pid, r in skip_marks().items() if r.get("skip")}


def skipped_on(day: date) -> set[int]:
    """Set aside on this particular day, and still set aside."""
    iso = day.isoformat()
    return {pid for pid, r in skip_marks().items()
            if r.get("skip") and r.get("date") == iso}


def make_sprint(n: int, on: date) -> dict:
    return {"ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "date": on.isoformat(), "sprint": n}


def current_sprint() -> int:
    """Which pass through the curriculum you are on. 1 until you start another."""
    marks = [r["sprint"] for r in raw_entries() if "sprint" in r]
    return marks[-1] if marks else 1


def start_sprint() -> dict:
    """Begin another pass, without deleting anything.

    A marker in the log, not a flag in settings: where you are in the curriculum
    is a record, and settings are a preference that falls back to defaults when
    the file will not parse. A sprint boundary that vanished on a corrupt
    settings.json would silently re-offer the entire curriculum.
    """
    with LOCK:
        mark = make_sprint(current_sprint() + 1, date.today())
        append(mark)
        return mark


def current_entries() -> list[dict]:
    """Attempts belonging to the pass in progress.

    Sliced by position rather than by date: a new pass can start on a day that
    already has attempts logged against the old one, and those belong to the old
    one.
    """
    rows = stream()
    cut = max((i for i, r in enumerate(rows) if "sprint" in r), default=-1)
    return [r for r in rows[cut + 1:] if "sprint" not in r]


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
    with LOCK:
        live = [r for r in current_entries() if r["id"] == pid]
        if not live:
            raise ValueError(f"{pid} has no logged attempt to change")
        last = live[-1]
        on = date.fromisoformat(last["date"])
        append(make_undo(pid, on))
        # Carry forward the fields this call is not changing. Rebuilding the
        # entry from scratch silently dropped the note, mistake class and
        # approach_min recorded at the time -- an amend is a correction to one
        # field, not a re-entry of the attempt.
        append(make_entry(
            pid, outcome, on,
            mistake if mistake is not None else last.get("mistake"),
            last.get("approach_min"),
            note if note is not None else last.get("note"),
            created_at=last.get("created_at") or last.get("ts"),
        ))
        return last


def delete_entry_by_ts(pid: int, ts: str) -> dict:
    """Retract a specific log entry by its timestamp.

    Used for deleting note/editorial entries where we want to remove a
    specific one rather than the most recent for that problem.
    Appends a targeted retraction: {id, ts_target, undo: True}.
    _live() recognises ts_target and cancels that exact entry.
    """
    with LOCK:
        live = [r for r in entries() if r.get("id") == pid]
        target = next((r for r in live if r.get("ts") == ts), None)
        if not target:
            raise ValueError(f"no entry with ts={ts!r} found for problem {pid}")
        # Append a standard undo -- _live cancels the most recent surviving
        # entry for this pid. Since note entries are appended after cold attempts,
        # they will be the most recent and the undo will target them correctly.
        # For safety we verify the target is actually the last surviving entry.
        if live[-1].get("ts") != ts:
            raise ValueError(
                f"can only delete the most recent entry for {pid}; "
                f"expected ts={live[-1].get('ts')!r}, got {ts!r}"
            )
        append(make_undo(pid, date.fromisoformat(target["date"])))
        return target


def undo(pid: int) -> dict:
    with LOCK:
        # current_entries(), not entries(): correcting a button-press belongs to
        # the pass you are in. Reaching back into a finished pass would rewrite
        # history that is already being reported as done.
        live = [r for r in current_entries() if r["id"] == pid]
        if not live:
            raise ValueError(f"{pid} has no logged attempt to undo in this pass")
        last = live[-1]
        append(make_undo(pid, date.fromisoformat(last["date"])))
        return last


def replay(rows: list[dict] | None = None) -> dict[int, ProblemState]:
    """Fold the log into per-problem schedule state.

    A sprint marker empties the state: a new pass means nothing is solved yet and
    the ladder starts over. The attempts before it are not discarded, they are
    just not what you are being scheduled on any more.
    """
    rows = stream() if rows is None else rows
    states: dict[int, ProblemState] = {}
    for r in rows:
        if "sprint" in r:
            states = {}
            continue
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
               approach_min: float | None = None, note: str | None = None,
               created_at: str | None = None) -> dict:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    return {
        "ts": now,
        "created_at": created_at or now,  # preserved across edits; ts becomes updated_at
        "date": on.isoformat(),
        "id": pid,
        "outcome": outcome,
        "mistake": mistake,
        "approach_min": approach_min,
        "note": note,
    }
