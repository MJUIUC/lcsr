"""Local web UI. Binds to loopback only; there is no auth and none is wanted.

The UI is a thin shell over the same plan/store functions the CLI uses -- it
holds no state of its own, so the two can never disagree about what is due.
"""

import json
import webbrowser
from urllib.parse import parse_qs, urlparse
from datetime import date
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import curriculum as cur
from .plan import curriculum_view, frequent_view, history_view, todays_plan
from .schedule import SOLVED, STUCK
from .store import MISTAKES, amend, append, make_entry, replay, undo

INDEX = Path(__file__).parent / "static" / "index.html"


def enrich(p: dict) -> dict:
    return {**p, "url": cur.url(p["id"])}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):        # keep the terminal quiet
        pass

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
        route = urlparse(self.path)
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
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"error": "bad json"})
        try:
            if self.path == "/api/log":
                return self._send(200, self._log(body))
            if self.path == "/api/add":
                return self._send(200, self._add(body))
            if self.path == "/api/amend":
                pid = int(body["id"])
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
                pid = int(body["id"])
                was = undo(pid)
                st = replay().get(pid)
                return self._send(200, {"ok": True, "id": pid,
                                        "undone": was["outcome"],
                                        "date": was["date"],
                                        "status": "new" if st is None
                                                  else ("done" if st.done else "learning")})
        except (KeyError, ValueError) as e:
            return self._send(400, {"error": str(e).strip("'")})
        return self._send(404, {"error": "not found"})

    def _log(self, body):
        pid = int(body["id"])
        cur.loggable(pid)                             # curriculum OR frequent pool
        # A problem that has cleared the ladder schedules nothing, so logging it
        # again only inflates the attempt counts and the cold re-solve rate.
        # Guarded here rather than only in the UI so the CLI cannot do it either.
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
        append(make_entry(pid, outcome, on, mistake, note=(body.get("note") or None)))
        st = replay()[pid]
        return {"ok": True, "id": pid, "done": st.done,
                "due": st.due.isoformat() if st.due else None}

    def _add(self, body):
        title = (body.get("title") or "").strip()
        if not title:
            raise ValueError("title is required")
        return {"ok": True, "problem": enrich(cur.add(
            int(body["id"]), title,
            week=int(body["week"]) if body.get("week") else None,
            hard=bool(body.get("hard")),
            block=(body.get("block") or "Added"),
            cue=(body.get("cue") or None),
        ))}


def serve(host="127.0.0.1", port=8765, open_browser=True):
    httpd = ThreadingHTTPServer((host, port), partial(Handler))
    url = f"http://{host}:{port}"
    print(f"lcsr → {url}   (ctrl-c to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
