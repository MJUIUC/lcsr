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
from . import settings as cfg
from . import store
from .plan import (curriculum_view, export_csv, foundations_left, frequent_view,
                   history_view, intake_week, todays_plan)
from .schedule import SOLVED, STUCK
from .store import (HOME, LOCK, LOG, MISTAKES, amend, append, current_sprint,
                    raw_entries,
                    make_entry, replay, start_sprint, undo)

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

    # Flipped on by the serverless entrypoint. When true there is no writable
    # disk, so the client posts its own state with every request and gets back
    # the records to persist. The local server leaves this false and keeps
    # reading and writing ~/.lcsr exactly as before.
    STATELESS = False

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
        if isinstance(body, dict):
            body = {**body, "stateless": self.STATELESS}
            mem = getattr(self, "_mem", None)
            if mem is not None:
                patch = mem.patch()
                if patch:
                    # What the browser must apply to its own copy. Log records
                    # are appended, never replaced, so its copy stays the same
                    # append-only jsonl the file would have been.
                    body["state_patch"] = patch
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
        if route.path == "/api/settings":
            return self._send(200, self._load_view())
        if route.path == "/api/export.csv":
            return self._download(export_csv().encode("utf-8"),
                                  "text/csv; charset=utf-8", "lcsr-progress.csv")
        if route.path == "/api/export.jsonl":
            # The raw log, byte for byte. The CSV is a view of it; this is the
            # thing the CLI can read straight back.
            raw = LOG.read_bytes() if LOG.exists() else b""
            return self._download(raw, "application/x-ndjson", "lcsr-log.jsonl")
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
        token = None
        if self.STATELESS or "state" in body:
            self._mem = store.MemoryBackend.from_payload(body.get("state"))
            token = store.use(self._mem)
        try:
            return self._post_routes(body)
        finally:
            if token is not None:
                store.release(token)

    # /api/settings is the one path that both reads and writes, so the payload
    # decides. Routing it by path alone made every save look like a read: it
    # answered with the old values and saved nothing.
    SETTING_KEYS = ("foundations", "core", "reps", "daily_total", "reset")
    READ_PATHS = ("/api/plan", "/api/curriculum", "/api/history",
                  "/api/frequent", "/api/cues")

    def _route(self, body) -> str:
        """Which endpoint this POST means.

        GOTCHA: a Vercel rewrite gives the function the DESTINATION path, so every
        request arrives as /api/index and self.path tells you nothing about what
        was asked for. Everything 404'd. The client names the endpoint in the body
        instead, which is true regardless of how any host rewrites, and self.path
        stays the fallback for the local server and for curl.
        """
        op = body.get("op")
        if isinstance(op, str) and op.startswith("/api/"):
            return op
        return self.path

    def _is_read(self, body) -> bool:
        path = self._route(body)
        if path in self.READ_PATHS:
            return True
        return (path == "/api/settings"
                and not any(k in body for k in self.SETTING_KEYS))

    def _post_routes(self, body):
        path = self._route(body)
        try:
            # The read endpoints answer a POST too, because that is the only way
            # a stateless client can hand over its state. Same code, same shapes.
            if self._is_read(body):
                q = f"?date={body['date']}" if body.get("date") else ""
                return self._get(urlparse(path + q))
            if path == "/api/log":
                return self._send(200, self._log(body))
            if path == "/api/export":
                # Same bytes the GET download serves, but as JSON, because a
                # stateless client cannot GET a file the server cannot build.
                fmt = "jsonl" if body.get("format") == "jsonl" else "csv"
                if fmt == "jsonl":
                    text = "\n".join(json.dumps(r, ensure_ascii=False)
                                     for r in raw_entries())
                    text = text + "\n" if text else ""
                else:
                    text = export_csv()
                return self._send(200, {"ok": True, "format": fmt, "text": text,
                                        "filename": f"lcsr-progress.csv" if fmt == "csv"
                                                    else "lcsr-log.jsonl"})
            if path == "/api/add":
                return self._send(200, self._add(body))
            if path == "/api/sprint":
                mark = start_sprint()
                return self._send(200, {"ok": True, "sprint": mark["sprint"],
                                        "date": mark["date"]})
            if path == "/api/settings":
                # Absent key means "leave alone"; an explicit null clears that
                # override back to the curriculum's own load. They are different
                # instructions and the UI sends both.
                if body.get("reset"):
                    cfg.reset()
                else:
                    cfg.update(**{k: body[k] for k in
                                  ("foundations", "core", "reps", "daily_total")
                                  if k in body})
                return self._send(200, self._load_view())
            if path == "/api/amend":
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
            if path == "/api/undo":
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
            raise ValueError(f"{pid} is already solved. Pass again to re-open it.")
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

    def _download(self, raw: bytes, ctype: str, filename: str):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _load_view(self):
        """Settings plus the day they produce.

        The effective mix is computed here rather than in the page, because a
        cap that silently zeroes a tier is exactly the thing a user needs shown
        back to them, and the rule for it lives in settings.daily_quota().
        """
        attempted = set(replay())
        return cfg.describe(intake_week(attempted), foundations_left(attempted),
                            cfg.load(), current_sprint())

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
