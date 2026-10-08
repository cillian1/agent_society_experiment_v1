import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

INDEX = Path(__file__).parent / "static" / "index.html"


def serve(society, host: str, port: int, interval: float):
    ctl = {"paused": False, "interval": interval}

    def loop():
        while True:
            if ctl["paused"]:
                time.sleep(0.2)
                continue
            t0 = time.time()
            try:
                society.step()
            except Exception as e:  # keep the hub alive if an LLM call blows up
                print("step failed:", e)
                time.sleep(2)
            time.sleep(max(0.0, ctl["interval"] - (time.time() - t0)))

    threading.Thread(target=loop, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                body = INDEX.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif url.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
            elif url.path == "/api/world":
                self._json(society.world_data())
            elif url.path == "/api/state":
                s = society.snapshot()
                s.update(paused=ctl["paused"], interval=ctl["interval"], tiles=society.tiles_now(), fog=society.fog())
                self._json(s)
            elif url.path == "/api/history":
                self._json(society.history(parse_qs(url.query).get("name", [""])[0]))
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            if urlparse(self.path).path == "/api/control":
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if "paused" in data:
                    ctl["paused"] = bool(data["paused"])
                if data.get("authority") in ("leader", "advisor", "observer"):
                    society.human_authority = data["authority"]
                if "interval" in data:
                    ctl["interval"] = max(0.1, float(data["interval"]))
                self._json(ctl)
            elif urlparse(self.path).path == "/api/speak":
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                self._json({"delivered": society.human_say(data.get("to", "all"), str(data.get("message", "")))})
            elif urlparse(self.path).path == "/api/tier":
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                self._json({"model": society.set_model(data.get("name", ""), data.get("model") or data.get("tier", ""))})
            else:
                self._json({"error": "not found"}, 404)

        def log_message(self, *args):
            pass

    print(f"Hub running at http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
