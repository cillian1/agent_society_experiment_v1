"""Web hub: runs the simulation in a background thread and serves the viewer + a small JSON API."""
import json
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from society import persistence, views
from society.config import AUTOSAVE_EVERY

STATIC = Path(__file__).parent / "static"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}


class Hub:
    """Owns the running society and its clock, and can swap in a new or loaded world at any time.

    Days don't wait for every brain. At the start of a day every agent that isn't already thinking is asked
    what to do; each decision is applied the moment it arrives (at most one per agent per day). The day ends
    when everyone has answered - or after `max_wait` seconds, whichever comes first - and never sooner than
    `interval`. A slow brain (e.g. Opus) therefore only slows its own agent down: its answer lands a day or two
    later while everyone else carries on."""

    def __init__(self, society, new_world, load_world, interval: float = 1.0, max_wait: float = 5.0,
                 autosave: bool = True):
        self.society, self.new_world, self.load_world = society, new_world, load_world
        self.paused, self.interval, self.max_wait, self.autosave = False, interval, max_wait, autosave
        self.step_once = False
        self.last_autosave = society.tick
        self.pool = ThreadPoolExecutor(max_workers=64)
        self.busy: dict[tuple, int] = {}             # (id(society), agent name) -> day it started thinking
        self.busy_lock = threading.Lock()
        threading.Thread(target=self._loop, daemon=True).start()

    def _think_and_act(self, sim, agent, job, key):
        try:
            sim.apply_decision(agent, sim.think(agent, job), job)
        except Exception:
            traceback.print_exc()
        finally:
            with self.busy_lock:
                self.busy.pop(key, None)

    def _pending(self, sim, day: int) -> int:
        """Agents asked today that haven't answered yet (slow ones from earlier days don't hold today up)."""
        with self.busy_lock:
            return sum(1 for k, d in self.busy.items() if k[0] == id(sim) and d == day)

    def thinking_since(self, sim) -> dict[str, int]:
        with self.busy_lock:
            return {k[1]: d for k, d in self.busy.items() if k[0] == id(sim)}

    def _loop(self):
        while True:
            if self.paused and not self.step_once:
                time.sleep(0.1)
                continue
            self.step_once = False
            sim, t0 = self.society, time.time()
            day = sim.tick
            try:
                day = sim.begin_day()
                for a in list(sim.agents.values()):
                    key = (id(sim), a.name)
                    with self.busy_lock:
                        if key in self.busy:          # still thinking about an earlier day
                            continue
                    queued = sim.take_queued(a)           # a step it planned earlier: no thinking needed
                    if queued:
                        sim.apply_decision(a, queued, {"heard": []})
                        continue
                    job = sim.prepare(a)
                    if job:
                        with self.busy_lock:
                            self.busy[key] = day
                        self.pool.submit(self._think_and_act, sim, a, job, key)
            except Exception:
                traceback.print_exc()
                time.sleep(2)
            while sim is self.society:                # wait for answers, within limits
                waited = time.time() - t0
                if waited >= self.interval and (self._pending(sim, day) == 0 or waited >= max(self.max_wait, self.interval)):
                    break
                time.sleep(0.05)
            sim.end_day(time.time() - t0)
            if self.autosave and sim is self.society and sim.tick - self.last_autosave >= AUTOSAVE_EVERY:
                self.last_autosave = sim.tick
                try:
                    persistence.save(sim, "autosave")
                except OSError as e:
                    print("autosave failed:", e)

    def swap(self, sim):
        self.society, self.last_autosave = sim, sim.tick

    # ---- API ----
    def get(self, path: str, q: dict):
        sim = self.society
        if path == "/api/world":
            return {"width": sim.world.width, "height": sim.world.height, "tiles": sim.world.tiles}
        if path == "/api/state":
            st = {**views.state(sim), "paused": self.paused, "interval": self.interval, "max_wait": self.max_wait}
            slow = self.thinking_since(sim)
            st["thinking"] = len(slow)
            for a in st["agents"]:                    # mark agents whose brain is still on an earlier day
                a["slow"] = a["name"] in slow and slow[a["name"]] < sim.tick
            return st
        if path == "/api/agent":
            return views.agent_detail(sim, q.get("name", [""])[0]) or {"error": "no such agent"}
        if path == "/api/stats":
            return sim.stats
        if path == "/api/saves":
            return persistence.list_saves()
        return None

    def post(self, path: str, d: dict):
        sim = self.society
        if path == "/api/control":
            if "paused" in d:
                self.paused = bool(d["paused"])
            if "interval" in d:
                self.interval = max(0.05, float(d["interval"]))
            if "max_wait" in d:
                self.max_wait = max(0.5, float(d["max_wait"]))
            if d.get("step"):
                self.step_once = True
            if d.get("authority") in ("leader", "advisor", "observer"):
                sim.human_authority = d["authority"]
            return {"paused": self.paused, "interval": self.interval, "max_wait": self.max_wait,
                    "authority": sim.human_authority}
        if path == "/api/speak":
            return {"delivered": sim.human_say(d.get("to", "all"), str(d.get("message", "")))}
        if path == "/api/model":
            return {"model": sim.set_model(d.get("name", ""), d.get("model", ""))}
        if path == "/api/gift":
            return {"gift": sim.gift(d.get("name", ""), d.get("what", ""))}
        if path == "/api/save":
            return {"saved": persistence.save(sim, d.get("name") or f"day {sim.tick}")}
        if path == "/api/load":
            self.swap(self.load_world(d.get("name", "")))
            return {"loaded": d.get("name"), "day": self.society.tick}
        if path == "/api/new":
            seed = d.get("seed")
            self.swap(self.new_world(int(seed) if str(seed or "").lstrip("-").isdigit() else None))
            return {"new": True}
        return None


def serve(hub: Hub, host: str, port: int):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def _handle(self, fn):
            try:
                out = fn()
                self._json(out) if out is not None else self._json({"error": "not found"}, 404)
            except FileNotFoundError:
                self._json({"error": "no such save"}, 404)
            except Exception as e:
                traceback.print_exc()
                self._json({"error": str(e)}, 500)

        def do_GET(self):
            url = urlparse(self.path)
            name = "index.html" if url.path == "/" else url.path.lstrip("/")
            static = {p.name: p for p in STATIC.iterdir()}
            if name in static:                       # only files that really are in static/ (no path tricks)
                return self._send(200, static[name].read_bytes(), TYPES.get(static[name].suffix, "application/octet-stream"))
            if url.path == "/favicon.ico":
                return self._send(204, b"", "image/x-icon")
            self._handle(lambda: hub.get(url.path, parse_qs(url.query)))

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
            self._handle(lambda: hub.post(urlparse(self.path).path, json.loads(body or b"{}")))

        def log_message(self, *args):
            pass

    print(f"Hub running at http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
