"""TimberLive stream overlay server (OBS Browser Source).

Serves the overlay page on http://127.0.0.1:8096/ and three JSON feeds:
  /state.json       - Claude's narration, to-do list and current viewer poll (MCP tools)
  /colony.json      - live colony stats, fetched server-side from the bridge mod
  /poll_counts.json - vote counts only, written by the separate chatpoll service
  /welcome.json     - how many new people joined chat (a number, never names), for the ticker

The bridge token stays in this process; the browser page never sees it. Chat text
is NOT handled here; chatpoll/ reads chat and only ever writes vote counts and a new-chatter count.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "state.json"
COUNTS_FILE = ROOT / "poll_counts.json"
WELCOME_FILE = ROOT / "welcome.json"
SEEN_FILE = ROOT / "userscript_seen.json"   # last time the chat userscript polled
USERSCRIPT = ROOT.parent / "chatpoll" / "timberlive-poll.user.js"   # served so Tampermonkey can install/update it
WELCOME_GAP = 180   # seconds: at most one welcome line every 3 minutes
CONNECTION_FILE = Path(os.environ["LOCALAPPDATA"]) / "TimberLive" / "bridge.json"
PORT = 8096
COLONY_INTERVAL = 3.0

_colony_lock = threading.Lock()
_colony: dict = {"ok": False}


def _bridge_get(path: str):
    connection = json.loads(CONNECTION_FILE.read_text())
    request = urllib.request.Request(f"http://127.0.0.1:{connection['port']}{path}",
                                     headers={"X-TimberLive-Token": connection["token"]})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def _poll_colony():
    global _colony
    while True:
        try:
            state = _bridge_get("/api/state")
            goods = {g["id"]: g for g in _bridge_get("/api/goods")}
            food_ids = ("Berries", "Kohlrabi", "FermentedCassava", "FermentedSoybean", "FermentedMushroom",
                        "CornRation", "EggplantRation", "AlgaeRation", "Carrot", "GrilledPotato", "Bread")
            # Edible goods only: raw Cassava, Soybean, Corn, Eggplant and Potato must be processed first.
            snapshot = {
                "ok": True,
                "cycle": state["time"]["cycle"],
                "day": state["time"]["cycleDay"],
                "speed": state["time"]["speed"],
                "weather": state["weather"],
                "adults": state["population"]["adults"],
                "kits": state["population"]["children"],
                "homeless": state["population"]["homeless"],
                "wellbeing": state["wellbeing"],
                "science": state["science"],
                "water": goods.get("Water", {}).get("available", 0),
                "waterCap": goods.get("Water", {}).get("capacity", 0),
                "food": sum(goods[g]["available"] for g in food_ids if g in goods),
                "logs": goods.get("Log", {}).get("available", 0),
                "planks": goods.get("Plank", {}).get("available", 0),
                "updated": time.time(),
            }
        except Exception as e:  # game loading, closed, or bridge restarting
            snapshot = {"ok": False, "error": type(e).__name__, "updated": time.time()}
        with _colony_lock:
            _colony = snapshot
        time.sleep(COLONY_INTERVAL)


class Handler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "web"), **kwargs)

    def log_message(self, format, *args):
        pass

    def _json(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        # Strict CSP: the page only loads its own files and only shows text.
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:")
        super().end_headers()

    def do_GET(self):
        if self.path.startswith("/state.json"):
            if self.headers.get("X-TimberLive-Poll") == "1":
                # Heartbeat: the chat userscript is alive and can reach this server.
                SEEN_FILE.write_text(json.dumps({"at": time.time()}), encoding="utf-8")
            try:
                self._json(json.loads(STATE_FILE.read_text(encoding="utf-8")))
            except (FileNotFoundError, json.JSONDecodeError):
                self._json({"thoughts": [], "todos": []})
            return
        if self.path.startswith("/poll_counts.json"):
            try:
                self._json(json.loads(COUNTS_FILE.read_text(encoding="utf-8")))
            except (FileNotFoundError, json.JSONDecodeError):
                self._json({})
            return
        if self.path.startswith("/welcome.json"):
            try:
                self._json(json.loads(WELCOME_FILE.read_text(encoding="utf-8")))
            except (FileNotFoundError, json.JSONDecodeError):
                self._json({})
            return
        if self.path == "/timberlive-poll.user.js":
            body = USERSCRIPT.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/colony.json"):
            with _colony_lock:
                self._json(_colony)
            return
        super().do_GET()


    def do_POST(self):
        # Only the browser userscript (chatpoll/timberlive-poll.user.js) posts here. The custom
        # header forces a CORS preflight, which this server never answers, so ordinary web pages
        # can't post. Only integers are accepted: vote totals and a new-chatter count.
        if self.headers.get("X-TimberLive-Poll") != "1":
            self.send_error(404)
            return
        if self.path.startswith("/welcome"):
            self._post_welcome()
        elif self.path.startswith("/poll_counts"):
            self._post_counts()
        else:
            self.send_error(404)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 2048:
            raise ValueError
        return json.loads(self.rfile.read(length))

    def _post_welcome(self):
        # {"new": n} -> the ticker says "Welcome to the n new people in chat". No names, ever.
        try:
            body = self._read_body()
            n = body["new"]
            if type(n) is not int or not 1 <= n <= 1000 or set(body) != {"new"}:
                raise ValueError
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            self.send_error(400)
            return
        try:
            last = json.loads(WELCOME_FILE.read_text(encoding="utf-8")).get("at", 0)
        except (FileNotFoundError, json.JSONDecodeError):
            last = 0
        now = time.time()
        if now - last < WELCOME_GAP:
            self._json({"ok": False, "retryIn": round(WELCOME_GAP - (now - last))})
            return
        tmp = WELCOME_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"id": int(now), "n": n, "at": now}), encoding="utf-8")
        tmp.replace(WELCOME_FILE)
        self._json({"ok": True})

    def _post_counts(self):
        # Vote totals: only integers for the current poll are kept.
        try:
            body = self._read_body()
            poll = json.loads(STATE_FILE.read_text(encoding="utf-8")).get("poll") or {}
            counts = body["counts"]
            if (body["id"] != poll.get("id") or len(counts) != len(poll.get("options", []))
                    or not all(type(c) is int and 0 <= c <= 100000 for c in counts)
                    or type(body["voters"]) is not int):
                raise ValueError
        except (ValueError, KeyError, TypeError, json.JSONDecodeError, FileNotFoundError):
            self.send_error(400)
            return
        payload = {"id": poll["id"], "counts": counts, "voters": body["voters"],
                   "status": "counting_browser", "updated": time.time()}
        tmp = COUNTS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(COUNTS_FILE)
        self._json({"ok": True})


def main():
    threading.Thread(target=_poll_colony, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"TimberLive overlay on http://127.0.0.1:{PORT}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
