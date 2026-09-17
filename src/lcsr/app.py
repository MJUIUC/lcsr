"""lcsr desktop companion app.

Launches a native desktop window (pywebview / WebKit on macOS) running the
lcsr UI. Replaces `lcsr serve` for local use: the UI calls Python directly
via window.pywebview.api rather than over HTTP, so no server is started.

LeetCode opens in the user's real browser. The timer pops out as a second
native window with reliable audio (no autoplay restrictions, no gesture
required).

Install: pip install lcsr[app]
Launch:  lcsr app
"""

from __future__ import annotations

import json
import webbrowser
from datetime import date as date_
from pathlib import Path

# ---------------------------------------------------------------------------
# Guards: give a clear error if the optional extras are missing rather than
# letting an ImportError bubble up with a confusing traceback.
# ---------------------------------------------------------------------------
try:
    import webview
except ImportError:
    raise SystemExit(
        "pywebview is not installed. Run:  pip install lcsr[app]"
    )

try:
    from youtubesearchpython import VideosSearch
except ImportError:
    raise SystemExit(
        "youtube-search-python is not installed. Run:  pip install lcsr[app]"
    )

from . import curriculum as cur
from . import settings as cfg
from .plan import (curriculum_view, export_csv, foundations_left,
                   frequent_view, history_view, intake_week, todays_plan)
from .schedule import SOLVED, STUCK
from .store import (LOCK, MISTAKES, amend, append, current_sprint,
                    make_entry, replay, set_skipped, start_sprint, undo)

STATIC = Path(__file__).parent / "static"
APP_HTML = STATIC / "app.html"
TIMER_HTML = STATIC / "timer.html"


# ---------------------------------------------------------------------------
# Helpers shared between API methods
# ---------------------------------------------------------------------------

def _today() -> date_:
    return date_.today()


def _problem_id(v) -> int:
    """Same strict validation as server.py's problem_id()."""
    if isinstance(v, bool) or v is None:
        raise ValueError("id must be an integer")
    if isinstance(v, float) and not v.is_integer():
        raise ValueError("id must be a whole number")
    try:
        return int(v)
    except (TypeError, ValueError):
        raise ValueError("id must be an integer") from None


def _enrich(p: dict) -> dict:
    return {**p, "url": cur.url_of(p["id"])}


# ---------------------------------------------------------------------------
# Python API — exposed to every window via window.pywebview.api
# ---------------------------------------------------------------------------

class LcsrAPI:
    """
    All methods that return data return plain dicts/lists (JSON-serialisable).
    pywebview serialises the return value for you; JS receives a Promise that
    resolves to the value.

    Methods that write state return a small result dict so the JS call site
    can update the UI without a follow-up read call.
    """

    def __init__(self):
        self._timer_win = None   # webview.Window | None, set when timer opens
        self._main_win = None   # webview.Window | None, set after main window creation

    # ---------------------------------------------------------------- reads

    def get_plan(self, date: str | None = None) -> dict:
        on = date_.fromisoformat(date) if date else _today()
        today = _today()
        plan = todays_plan(on, today=today)
        plan["is_today"] = (on == today)
        plan["due"] = [_enrich(p) for p in plan["due"]]
        for key in ("sections", "ahead"):
            for s in plan[key]:
                s["problems"] = [_enrich(p) for p in s["problems"]]
        plan["mistakes"] = list(MISTAKES)
        return plan

    def get_curriculum(self) -> dict:
        return curriculum_view()

    def get_history(self) -> dict:
        return history_view()

    def get_cues(self) -> list:
        return cur.cues()

    def get_settings(self) -> dict:
        attempted = set(replay())
        return cfg.describe(
            intake_week(attempted),
            foundations_left(attempted),
            cfg.load(),
            current_sprint(),
        )

    def get_frequent(self) -> dict:
        return frequent_view()

    # --------------------------------------------------------------- writes

    def log(self, id, outcome: str, approach_min=None,
            mistake: str | None = None, note: str | None = None) -> dict:
        pid = _problem_id(id)
        cur.loggable(pid)
        with LOCK:
            prior = replay().get(pid)
            if prior is not None and prior.done:
                raise ValueError(
                    f"{pid} is already solved. Use log_again to re-open it."
                )
            out = STUCK if outcome == STUCK else SOLVED
            mk = mistake or None
            if mk and mk not in MISTAKES:
                raise ValueError(f"mistake must be one of {MISTAKES}")
            if out == SOLVED:
                mk = None
            am = None
            if approach_min is not None:
                try:
                    am = float(approach_min)
                    if am < 0:
                        am = None
                except (TypeError, ValueError):
                    am = None
            append(make_entry(pid, out, _today(), mk, am, note or None))
            st = replay()[pid]
        return {"ok": True, "id": pid, "done": st.done,
                "due": st.due.isoformat() if st.due else None}

    def log_again(self, id, outcome: str, approach_min=None,
                  mistake: str | None = None, note: str | None = None) -> dict:
        """Re-open and re-log an already-solved problem."""
        pid = _problem_id(id)
        cur.loggable(pid)
        with LOCK:
            out = STUCK if outcome == STUCK else SOLVED
            mk = (mistake or None) if out == STUCK else None
            am = None
            if approach_min is not None:
                try:
                    am = float(approach_min)
                    if am < 0:
                        am = None
                except (TypeError, ValueError):
                    am = None
            append(make_entry(pid, out, _today(), mk, am, note or None))
            st = replay()[pid]
        return {"ok": True, "id": pid, "done": st.done,
                "due": st.due.isoformat() if st.due else None}

    def undo(self, id) -> dict:
        pid = _problem_id(id)
        was = undo(pid)
        st = replay().get(pid)
        return {"ok": True, "id": pid, "undone": was["outcome"],
                "date": was["date"],
                "status": "new" if st is None else ("done" if st.done else "learning")}

    def amend(self, id, outcome: str,
              mistake: str | None = None, note: str | None = None) -> dict:
        pid = _problem_id(id)
        cur.loggable(pid)
        out = STUCK if outcome == STUCK else SOLVED
        mk = (mistake or None) if out == STUCK else None
        if mk and mk not in MISTAKES:
            raise ValueError(f"mistake must be one of {MISTAKES}")
        was = amend(pid, out, mk, note or None)
        st = replay()[pid]
        return {"ok": True, "id": pid, "was": was["outcome"], "now": out,
                "date": was["date"],
                "due": st.due.isoformat() if st.due else None}

    def skip(self, id, skip: bool = True) -> dict:
        pid = _problem_id(id)
        cur.loggable(pid)
        set_skipped(pid, skip)
        return {"ok": True, "id": pid, "skipped": skip}

    def save_settings(self, **kwargs) -> dict:
        cfg.update(**{k: kwargs[k] for k in
                      ("foundations", "core", "reps", "daily_total")
                      if k in kwargs})
        attempted = set(replay())
        return cfg.describe(intake_week(attempted), foundations_left(attempted),
                            cfg.load(), current_sprint())

    def reset_settings(self) -> dict:
        cfg.reset()
        attempted = set(replay())
        return cfg.describe(intake_week(attempted), foundations_left(attempted),
                            cfg.load(), current_sprint())

    def start_sprint(self) -> dict:
        mark = start_sprint()
        return {"ok": True, "sprint": mark["sprint"], "date": mark["date"]}

    def add_problem(self, id, title: str, block: str = "Added",
                    cue: str | None = None, week: int | None = None,
                    hard: bool = False) -> dict:
        pid = _problem_id(id)
        p = cur.add(pid, title, week=week, hard=hard, block=block, cue=cue)
        return {"ok": True, "id": pid, "title": p["title"]}

    def export(self, fmt: str = "csv") -> dict:
        if fmt == "jsonl":
            from .store import LOG
            text = LOG.read_text(encoding="utf-8") if LOG.exists() else ""
            filename = "lcsr-log.jsonl"
        else:
            text = export_csv()
            filename = "lcsr-progress.csv"
        return {"ok": True, "format": fmt, "text": text, "filename": filename}

    # ------------------------------------------------- timer / companion

    def open_timer(self, id, title: str, url: str,
                   timer_min: float = 25) -> dict:
        """
        Open the LeetCode problem in the real browser, then pop out the
        timer window. Calling again while a timer is open for the same id
        just focuses the existing window.
        """
        pid = _problem_id(id)
        webbrowser.open(url)

        # If a timer is already open, just focus it.
        if self._timer_win is not None:
            try:
                self._timer_win.show()
                return {"ok": True, "reused": True}
            except Exception:
                self._timer_win = None  # window was closed; fall through

        params = (f"?id={pid}"
                  f"&title={_urlencode(title)}"
                  f"&min={float(timer_min):.1f}")

        self._timer_win = webview.create_window(
            f"Timer — #{pid}",
            str(TIMER_HTML) + params,
            width=360,
            height=520,
            resizable=False,
            on_top=True,
            js_api=self,
        )
        # Clean up the reference when the user closes the popup.
        # pywebview fires the closed event on the GUI thread.
        def _on_closed():
            self._timer_win = None
        self._timer_win.events.closed += _on_closed  # type: ignore[union-attr]

        return {"ok": True, "reused": False}

    def timer_done(self, id, elapsed_sec: float, paused_sec: float = 0) -> dict:
        """Called by timer.html when Done is clicked (solved before timeout)."""
        pid = _problem_id(id)
        am = round(elapsed_sec / 60, 1)
        result = self.log(pid, SOLVED, approach_min=am)
        self._close_timer()
        self._refresh_main()
        return result

    def timer_timeout(self, id, elapsed_sec: float,
                      paused_sec: float = 0) -> dict:
        """Called by timer.html when the countdown reaches zero."""
        pid = _problem_id(id)
        am = round(elapsed_sec / 60, 1)
        # Don't log yet — pre-fill the stuck panel in the main window so
        # the user can still pick a mistake class and add a note before
        # committing. The main window handles the actual /log call.
        self._refresh_main(prefill_stuck=pid, approach_min=am)
        # Video search runs in background; timer window transitions to results.
        try:
            p = cur.get(pid)
            title = p.get("title", str(pid))
        except KeyError:
            title = str(pid)
        results = self._youtube_search(f"{title} leetcode solution")
        return {"ok": True, "id": pid, "results": results}

    def video_search(self, query: str) -> list:
        return self._youtube_search(query)

    def open_leetcode(self, url: str) -> dict:
        webbrowser.open(url)
        return {"ok": True}

    # ------------------------------------------------------------ internals

    def _close_timer(self):
        if self._timer_win is not None:
            try:
                self._timer_win.destroy()
            except Exception:
                pass
            self._timer_win = None

    def _refresh_main(self, prefill_stuck: int | None = None,
                      approach_min: float | None = None):
        """Tell the main window to re-render. Runs on the GUI thread."""
        if self._main_win is None:
            return
        if prefill_stuck is not None:
            payload = json.dumps({"id": prefill_stuck, "approach_min": approach_min})
            self._main_win.evaluate_js(
                f"window._lcsrTimerTimeout && window._lcsrTimerTimeout({payload})"
            )
        else:
            self._main_win.evaluate_js(
                "window._lcsrRefresh && window._lcsrRefresh()"
            )

    def _youtube_search(self, query: str) -> list:
        try:
            vs = VideosSearch(query, limit=8)
            raw = vs.result().get("result", [])
            return [
                {
                    "id": r.get("id", ""),
                    "title": r.get("title", ""),
                    "channel": (r.get("channel") or {}).get("name", ""),
                    "duration": r.get("duration", ""),
                    "thumbnail": (
                        (r.get("thumbnails") or [{}])[0].get("url", "")
                    ),
                }
                for r in raw
                if r.get("id")
            ]
        except Exception:
            return []


def _urlencode(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    api = LcsrAPI()

    main_win = webview.create_window(
        "lcsr",
        str(APP_HTML),
        width=1100,
        height=800,
        min_size=(680, 500),
        js_api=api,
    )
    api._main_win = main_win

    # start() blocks until all windows are closed.
    webview.start(debug=False)
