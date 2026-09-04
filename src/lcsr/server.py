"""Local web UI. Binds to loopback only; there is no auth and none is wanted.

The UI is a thin shell over the same plan/store functions the CLI uses -- it
holds no state of its own, so the two can never disagree about what is due.
"""

import json
import os
import signal
import socket
import subprocess
import time
import sys
import webbrowser
from urllib.parse import parse_qs, urlparse
from datetime import date
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import curriculum as cur
from .plan import curriculum_view, frequent_view, history_view, todays_plan
from .schedule import SOLVED, STUCK
from .store import HOME, LOCK, MISTAKES, amend, append, make_entry, replay, undo

INDEX = Path(__file__).parent / "static" / "index.html"

PIDFILE = HOME / "server.pid"
SERVERLOG = HOME / "server.log"


def is_up(host: str, port: int, timeout: float = 0.4) -> bool:
    """Liveness by connecting, not by the pidfile.

    A pidfile outlives a crash and the pid can be reused, so it is a claim about
    the past; a successful connect is a fact about now.
    """
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def start_detached(host: str, port: int) -> bool:
    """Launch the server in its own session so it outlives this terminal.

    start_new_session detaches it from the calling process group, so closing the
    shell -- or the agent session that ran it -- does not take it down with them.
    """
    HOME.mkdir(parents=True, exist_ok=True)
    with SERVERLOG.open("a", encoding="utf-8") as out:
        proc = subprocess.Popen(
            [sys.executable, "-m", "lcsr", "serve", "--host", host,
             "--port", str(port), "--no-open"],
            stdout=out, stderr=out, stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    PIDFILE.write_text(str(proc.pid), encoding="utf-8")
    for _ in range(40):                      # up to ~8s
        if is_up(host, port):
            return True
        if proc.poll() is not None:          # died on startup
            return False
        time.sleep(0.2)
    return is_up(host, port)


def stop() -> bool:
    try:
        pid = int(PIDFILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        PIDFILE.unlink(missing_ok=True)
        return False
    for _ in range(25):
        time.sleep(0.2)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
    PIDFILE.unlink(missing_ok=True)
    return True


def problem_id(body: dict) -> int:
    """Strict id parsing.

    int() accepts bools (True -> 1, logging an attempt against Two Sum) and
    truncates floats (42.9 -> 42), both silently writing to the wrong problem.
    """
    v = body.get("id")
    if isinstance(v, bool) or v is None:
        raise ValueError("id must be an integer")
    if isinstance(v, float) and not v.is_integer():
        raise ValueError("id must be a whole number")
    try:
        return int(v)
    except (TypeError, ValueError):
        raise ValueError("id must be an integer") from None


def enrich(p: dict) -> dict:
    # url_of(), not url(): plan["due"] rows are built with cur.loggable(), which
    # resolves the curriculum OR the frequent pool, so a frequent-only problem
    # coming due would raise KeyError here and kill the handler thread -- the
    # client gets a closed socket with zero bytes and the whole UI goes blank.
    return {**p, "url": cur.url_of(p["id"])}


def err_text(e: BaseException) -> str:
    """KeyError stringifies as its repr, so str() wraps the message in quotes.
    Take the argument directly instead of stripping quotes off the outside,
    which also ate quotes that were part of the message."""
    if isinstance(e, KeyError) and e.args:
        return str(e.args[0])
    return str(e)


class Handler(BaseHTTPRequestHandler):
    # A handler that blocks forever on a short body ties up a thread for good.
    timeout = 15

    def log_message(self, *a):        # keep the terminal quiet
        pass

    def _same_origin(self) -> bool:
        """Reject cross-site writes.

        The server has no auth and binds to a predictable port, so ANY page the
        user happens to visit while `lcsr serve` runs could POST here and corrupt
        the log. Browsers always send Origin on a cross-origin POST; curl and the
        CLI send none, which is why absent is allowed.
        """
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        host = self.headers.get("Host", "")
        return origin.split("://")[-1] == host

    def _send(self, code, body, ctype="application/json"):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        # The page is read fresh from disk on every request, but the browser was
        # free to cache it, so editing index.html and reloading showed the old
        # UI. Nothing here is worth caching -- it is localhost and every response
        # is derived from a log that changes as you use it.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        try:
            return self._get(urlparse(self.path))
        except (KeyError, ValueError, TypeError, AttributeError) as e:
            # Never answer a GET with a closed socket: a handler that raises
            # writes zero bytes, and the UI's bootstrap has no way to tell that
            # from a dead server.
            return self._send(400, {"error": err_text(e)})

    def _get(self, route):
        if route.path in ("/", "/index.html"):
            return self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
        if route.path == "/api/plan":
            q = parse_qs(route.query)
            try:
                on = date.fromisoformat(q["date"][0]) if q.get("date") else date.today()
            except ValueError:
                return self._send(400, {"error": "date must be YYYY-MM-DD"})
            plan = todays_plan(on)
            plan["is_today"] = on == date.today()
            plan["due"] = [enrich(p) for p in plan["due"]]
            for key in ("sections", "ahead"):
                for s in plan[key]:
                    s["problems"] = [enrich(p) for p in s["problems"]]
            plan["mistakes"] = list(MISTAKES)
            return self._send(200, plan)
        if route.path == "/api/curriculum":
            return self._send(200, curriculum_view())
        if route.path == "/api/history":
            return self._send(200, history_view())
        if route.path == "/api/frequent":
            return self._send(200, frequent_view())
        if route.path == "/api/cues":
            return self._send(200, cur.cues())
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._same_origin():
            return self._send(403, {"error": "cross-origin write refused"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n < 0 or n > 1_000_000:
                return self._send(413, {"error": "body too large"})
            raw = self.rfile.read(n) if n else b"{}"
            if len(raw) < n:
                return self._send(400, {"error": "truncated body"})
            body = json.loads(raw or b"{}")
        except (ValueError, json.JSONDecodeError, OSError):
            return self._send(400, {"error": "bad json"})
        if not isinstance(body, dict):
            return self._send(400, {"error": "body must be a JSON object"})
        try:
            if self.path == "/api/log":
                return self._send(200, self._log(body))
            if self.path == "/api/add":
                return self._send(200, self._add(body))
            if self.path == "/api/amend":
                pid = problem_id(body)
                cur.loggable(pid)
                outcome = STUCK if body.get("outcome") == STUCK else SOLVED
                mistake = body.get("mistake") or None
                if mistake and mistake not in MISTAKES:
                    raise ValueError(f"mistake must be one of {MISTAKES}")
                if outcome == SOLVED:
                    mistake = None
                was = amend(pid, outcome, mistake, body.get("note") or None)
                st = replay()[pid]
                return self._send(200, {"ok": True, "id": pid, "was": was["outcome"],
                                        "now": outcome, "date": was["date"],
                                        "due": st.due.isoformat() if st.due else None})
            if self.path == "/api/undo":
                pid = problem_id(body)
                was = undo(pid)
                st = replay().get(pid)
                return self._send(200, {"ok": True, "id": pid,
                                        "undone": was["outcome"],
                                        "date": was["date"],
                                        "status": "new" if st is None
                                                  else ("done" if st.done else "learning")})
        # AttributeError/TypeError too: an unvalidated body could reach code that
        # calls a method on the wrong type, and an uncaught raise kills the thread
        # mid-response, leaving the client with a closed socket and no status.
        except (KeyError, ValueError, TypeError, AttributeError) as e:
            return self._send(400, {"error": err_text(e)})
        return self._send(404, {"error": "not found"})

    def _log(self, body):
        pid = problem_id(body)
        cur.loggable(pid)                             # curriculum OR frequent pool
        # A problem that has cleared the ladder schedules nothing, so logging it
        # again only inflates the attempt counts and the cold re-solve rate.
        # Guarded here rather than only in the UI so the CLI cannot do it either.
        # Gate and append are one critical section. Threaded server: two
        # concurrent logs of the same problem would both read "not yet solved",
        # both pass this gate, and both append -- advancing the ladder twice.
        with LOCK:
            return self._log_locked(pid, body)

    def _log_locked(self, pid, body):
        prior = replay().get(pid)
        if prior is not None and prior.done and not body.get("again"):
            raise ValueError(f"{pid} is already solved — pass again to re-open it")
        outcome = STUCK if body.get("outcome") == STUCK else SOLVED
        mistake = body.get("mistake") or None
        if mistake and mistake not in MISTAKES:
            raise ValueError(f"mistake must be one of {MISTAKES}")
        if outcome == SOLVED:
            mistake = None                            # only meaningful on a failure
        on = date.fromisoformat(body["date"]) if body.get("date") else date.today()
        if on > date.today():
            raise ValueError("cannot log an attempt for a future date")
        append(make_entry(pid, outcome, on, mistake, note=(body.get("note") or None)))
        st = replay()[pid]
        return {"ok": True, "id": pid, "done": st.done,
                "due": st.due.isoformat() if st.due else None}

    def _add(self, body):
        title = (body.get("title") or "").strip()
        if not title:
            raise ValueError("title is required")
        return {"ok": True, "problem": enrich(cur.add(
            problem_id(body), title,
            week=int(body["week"]) if body.get("week") else None,
            hard=bool(body.get("hard")),
            block=(body.get("block") or "Added"),
            cue=(body.get("cue") or None),
        ))}


def serve(host="127.0.0.1", port=8765, open_browser=True):
    httpd = ThreadingHTTPServer((host, port), partial(Handler))
    httpd.allow_reuse_address = True
    url = f"http://{host}:{port}"
    print(f"lcsr → {url}   (ctrl-c to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
