"""Local web UI. Binds to loopback only; there is no auth and none is wanted.

The UI is a thin shell over the same plan/store functions the CLI uses -- it
holds no state of its own, so the two can never disagree about what is due.
"""

import json
import webbrowser
from datetime import date
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import curriculum as cur
from .plan import todays_plan
from .schedule import SOLVED, STUCK
from .store import MISTAKES, append, make_entry, replay

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
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
        if self.path == "/api/plan":
            plan = todays_plan()
            plan["due"] = [enrich(p) for p in plan["due"]]
            for s in plan["sections"]:
                s["problems"] = [enrich(p) for p in s["problems"]]
            plan["mistakes"] = list(MISTAKES)
            return self._send(200, plan)
        if self.path == "/api/cues":
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
        except (KeyError, ValueError) as e:
            return self._send(400, {"error": str(e).strip("'")})
        return self._send(404, {"error": "not found"})

    def _log(self, body):
        pid = int(body["id"])
        cur.get(pid)                                  # validate before writing
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
