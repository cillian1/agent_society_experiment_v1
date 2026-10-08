"""LLM backends and a router: Claude (Anthropic API), local models (Ollama / OpenAI-compatible servers), and a mock.

Agent model strings: "claude-..." -> Anthropic, "local" -> the default local model, "local:<name>" -> a specific local model.
"""
import json
import os
import re
import threading
import urllib.error
from contextlib import contextmanager
import urllib.request

from .config import HAIKU, LOCAL


def is_local(model: str | None) -> bool:
    return model is not None and (model == LOCAL or model.startswith("local:"))


class UsageMixin:
    """Counts API calls and tokens per model; optional $/million-token prices give a cost estimate."""

    def _init_usage(self, prices: dict | None = None):
        self._usage: dict[str, dict] = {}
        self._ulock = threading.Lock()
        self.prices = prices or {}  # model -> (input $/M tokens, output $/M tokens)

    def _record(self, model: str, inp: int, out: int, cached: int = 0, written: int = 0):
        """inp = input tokens at full price; cached = read from the prompt cache (a tenth of the price);
        written = put into the cache (a quarter more than full price, once)."""
        with self._ulock:
            u = self._usage.setdefault(model, {"calls": 0, "input": 0, "output": 0, "cached": 0, "written": 0})
            u["calls"] += 1
            u["input"] += inp
            u["output"] += out
            u["cached"] = u.get("cached", 0) + cached
            u["written"] = u.get("written", 0) + written

    def usage(self) -> dict:
        with self._ulock:
            models = {m: dict(u) for m, u in self._usage.items()}
        cost = 0.0
        priced = True
        for m, u in models.items():
            if m in self.prices:
                pi, po = self.prices[m]
                u["cost"] = (u["input"] + 0.1 * u.get("cached", 0) + 1.25 * u.get("written", 0)) * pi / 1e6 + u["output"] * po / 1e6
                cost += u["cost"]
            else:
                priced = False
        return {"models": models, "calls": sum(u["calls"] for u in models.values()),
                "input": sum(u["input"] + u.get("cached", 0) + u.get("written", 0) for u in models.values()),
                "cached": sum(u.get("cached", 0) for u in models.values()),
                "output": sum(u["output"] for u in models.values()),
                "cost": cost if priced and models else None}


class ClaudeLLM(UsageMixin):
    def __init__(self, model: str = HAIKU, max_tokens: int = 500, prices: dict | None = None):
        self._init_usage(prices)
        import anthropic  # imported lazily so the other backends work without the SDK

        self.client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, system: str, prompt: str, model: str | None = None, json_mode: bool = True,
                 max_tokens: int | None = None) -> str:
        model = model or self.model
        resp = self.client.messages.create(
            model=model,
            max_tokens=max_tokens or self.max_tokens,
            # the shared rules are identical for every agent: cache them (reads cost a tenth). Models only cache
            # prompts above a minimum length; shorter ones are simply sent normally.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}] if len(system) > 2000 else system,
            messages=[{"role": "user", "content": prompt}],
        )
        u = resp.usage
        self._record(model, u.input_tokens, u.output_tokens, getattr(u, "cache_read_input_tokens", 0) or 0,
                     getattr(u, "cache_creation_input_tokens", 0) or 0)
        return "".join(b.text for b in resp.content if b.type == "text")


class Slots:
    """How many requests we send to the local server at once - with a fast lane: an urgent request (the Human is
    waiting for an answer) goes before every queued routine one, and may use a couple of extra slots."""

    def __init__(self, n: int, extra: int = 2):
        self.free, self.extra, self.urgent, self.cv = n, extra, 0, threading.Condition()
        self.size = self.max = n                     # shrinks while the server is overloaded, grows back after

    def shrink(self) -> bool:
        with self.cv:
            if self.size <= 2:
                return False
            self.size -= 1
            self.free -= 1
            return True

    def grow(self):
        with self.cv:
            if self.size < self.max:
                self.size += 1
                self.free += 1
                self.cv.notify_all()

    def busy(self) -> bool:
        """Is everything taken (so an optional request, like a dream, should wait for another night)?"""
        with self.cv:
            return self.free <= 0 or self.urgent > 0

    @contextmanager
    def take(self, urgent: bool = False):
        with self.cv:
            self.urgent += urgent
            while not (self.free > -self.extra if urgent else self.free > 0 and not self.urgent):
                self.cv.wait()
            self.urgent -= urgent
            self.free -= 1
        try:
            yield
        finally:
            with self.cv:
                self.free += 1
                self.cv.notify_all()


class LocalLLM(UsageMixin):
    """Local model served by Ollama (native /api/chat) or any OpenAI-compatible server (LM Studio, llama.cpp, vLLM)."""

    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "qwen2.5:7b-instruct",
                 api: str = "ollama", concurrency: int = 8, ctx: int = 4096, max_tokens: int = 400,
                 timeout: float = 180):
        self._init_usage()
        self.base, self.model, self.api = base_url.rstrip("/"), model, api
        self.ctx, self.max_tokens, self.timeout = ctx, max_tokens, timeout
        self.slots = Slots(concurrency)                # how many requests we send to the server at once
        self.ok_streak = 0

    def usage(self) -> dict:
        u = super().usage()
        for m in u["models"].values():
            m["cost"] = 0.0                          # running locally is free
        u["cost"] = 0.0 if u["models"] else None
        return u

    def _post(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"local model server said {e.code}: {e.read()[:300].decode(errors='replace')}") from e
        except (TimeoutError, OSError) as e:
            if isinstance(e, TimeoutError) or "timed out" in str(e):
                self.ok_streak = 0
                fewer = self.slots.shrink()              # it's overloaded: ask it for less at once
                raise RuntimeError(f"the local model didn't answer within {int(self.timeout)} s - it's overloaded"
                                   + (f" (now sending at most {self.slots.size} requests at once)" if fewer else "")
                                   + ". Check `ollama ps`: it should say 100% GPU") from e
            raise RuntimeError(f"can't reach the local model server at {self.base} ({e}) - is Ollama running?") from e

    def complete(self, system: str, prompt: str, model: str | None = None, json_mode: bool = True,
                 urgent: bool = False, max_tokens: int | None = None) -> str:
        model = model or self.model
        limit = max_tokens or self.max_tokens
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        with self.slots.take(urgent):
            if self.api == "ollama":
                body = {"model": model, "messages": msgs, "stream": False, "keep_alive": "30m",
                        "options": {"num_ctx": self.ctx, "temperature": 0.6, "num_predict": limit}}
                if json_mode:
                    body["format"] = "json"
                r = self._post("/api/chat", body)
                text, inp, out = r["message"]["content"], r.get("prompt_eval_count", 0), r.get("eval_count", 0)
            else:
                body = {"model": model, "messages": msgs, "max_tokens": limit, "temperature": 0.6}
                try:
                    r = self._post("/v1/chat/completions",
                                   {**body, **({"response_format": {"type": "json_object"}} if json_mode else {})})
                except RuntimeError:
                    if not json_mode:
                        raise
                    r = self._post("/v1/chat/completions", body)   # server without JSON mode
                text = r["choices"][0]["message"]["content"]
                inp, out = r.get("usage", {}).get("prompt_tokens", 0), r.get("usage", {}).get("completion_tokens", 0)
        self._record(f"local:{model}", inp, out)
        self.ok_streak += 1
        if self.ok_streak % 25 == 0:
            self.slots.grow()                            # coping again: back up toward the full number
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()   # drop reasoning blocks some models emit

    def probe(self) -> tuple[bool, str]:
        """Is the server up, and does it have our model?"""
        try:
            path = "/api/tags" if self.api == "ollama" else "/v1/models"
            with urllib.request.urlopen(self.base + path, timeout=3) as r:
                data = json.loads(r.read())
        except Exception as e:
            return False, f"local model server not reachable at {self.base} ({e})"
        names = [m.get("name") or m.get("id") for m in (data.get("models") or data.get("data") or [])]
        if self.api == "ollama" and self.model not in names and f"{self.model}:latest" not in names:
            return False, f"server is up but model '{self.model}' isn't installed - run: ollama pull {self.model}"
        return True, f"local model '{self.model}' ready at {self.base}"


class RouterLLM:
    """Sends each call to the right backend based on the agent's model string."""

    def __init__(self, claude: ClaudeLLM | None = None, local: LocalLLM | None = None, mock=None,
                 notes: list[str] | None = None):
        self.claude, self.local, self.mock = claude, local, mock
        self.notes = notes or []
        self.default_model = LOCAL if local else HAIKU

    def complete(self, system: str, prompt: str, model: str | None = None, json_mode: bool = True,
                 urgent: bool = False, max_tokens: int | None = None) -> str:
        """urgent: someone (the Human) is waiting for this answer - it skips the queue of routine thinking.
        max_tokens: a longer answer than usual is allowed (Sol speaks to and advises many people at once)."""
        model = model or self.default_model
        if self.mock:
            return self.mock.complete(system, prompt, model, json_mode)
        if is_local(model):
            if not self.local:
                raise RuntimeError("no local model server available (is Ollama running?)")
            return self.local.complete(system, prompt, None if model == LOCAL else model[6:], json_mode, urgent, max_tokens)
        if not self.claude:
            raise RuntimeError("no ANTHROPIC_API_KEY set, so Claude models are unavailable")
        return self.claude.complete(system, prompt, model, json_mode, max_tokens)

    def usage(self) -> dict:
        parts = [b.usage() for b in (self.claude, self.local, self.mock) if b]
        models: dict = {}
        for u in parts:
            models.update(u["models"])
        costs = [u["cost"] for u in parts if u["models"]]
        return {"models": models, "calls": sum(u["calls"] for u in parts), "input": sum(u["input"] for u in parts),
                "cached": sum(u.get("cached", 0) for u in parts),
                "output": sum(u["output"] for u in parts),
                "cost": None if (not costs or None in costs) else sum(costs)}

    def info(self) -> dict:
        return {"mock": bool(self.mock), "claude": bool(self.claude), "local": bool(self.local),
                "local_model": self.local.model if self.local else None,
                "notes": self.notes}
