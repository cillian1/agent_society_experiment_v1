"""LLM backends and a router: Claude (Anthropic API), local models (Ollama / OpenAI-compatible servers), and a mock.

Agent model strings: "claude-..." -> Anthropic, "local" -> the default local model, "local:<name>" -> a specific local model.
"""
import json
import os
import random
import re
import threading
import urllib.error
import urllib.request

HAIKU = "claude-haiku-5-5"
LOCAL = "local"


def is_local(model: str | None) -> bool:
    return model is not None and (model == LOCAL or model.startswith("local:"))


class UsageMixin:
    """Counts API calls and tokens per model; optional $/million-token prices give a cost estimate."""

    def _init_usage(self, prices: dict | None = None):
        self._usage: dict[str, dict] = {}
        self._ulock = threading.Lock()
        self.prices = prices or {}  # model -> (input $/M tokens, output $/M tokens)

    def _record(self, model: str, inp: int, out: int):
        with self._ulock:
            u = self._usage.setdefault(model, {"calls": 0, "input": 0, "output": 0})
            u["calls"] += 1
            u["input"] += inp
            u["output"] += out

    def usage(self) -> dict:
        with self._ulock:
            models = {m: dict(u) for m, u in self._usage.items()}
        cost = 0.0
        priced = True
        for m, u in models.items():
            if m in self.prices:
                pi, po = self.prices[m]
                u["cost"] = u["input"] * pi / 1e6 + u["output"] * po / 1e6
                cost += u["cost"]
            else:
                priced = False
        return {"models": models, "calls": sum(u["calls"] for u in models.values()),
                "input": sum(u["input"] for u in models.values()),
                "output": sum(u["output"] for u in models.values()),
                "cost": cost if priced and models else None}


class ClaudeLLM(UsageMixin):
    def __init__(self, model: str = HAIKU, max_tokens: int = 500, prices: dict | None = None):
        self._init_usage(prices)
        import anthropic  # imported lazily so the other backends work without the SDK

        self.client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, system: str, prompt: str, model: str | None = None, json_mode: bool = True) -> str:
        model = model or self.model
        resp = self.client.messages.create(
            model=model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        self._record(model, resp.usage.input_tokens, resp.usage.output_tokens)
        return "".join(b.text for b in resp.content if b.type == "text")


class LocalLLM(UsageMixin):
    """Local model served by Ollama (native /api/chat) or any OpenAI-compatible server (LM Studio, llama.cpp, vLLM)."""

    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "qwen2.5:7b-instruct",
                 api: str = "ollama", concurrency: int = 8, ctx: int = 4096, max_tokens: int = 400,
                 timeout: float = 300):
        self._init_usage()
        self.base, self.model, self.api = base_url.rstrip("/"), model, api
        self.ctx, self.max_tokens, self.timeout = ctx, max_tokens, timeout
        self.sem = threading.Semaphore(concurrency)   # how many requests we send to the server at once

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
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise RuntimeError(f"can't reach the local model server at {self.base} ({e})") from e

    def complete(self, system: str, prompt: str, model: str | None = None, json_mode: bool = True) -> str:
        model = model or self.model
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        with self.sem:
            if self.api == "ollama":
                body = {"model": model, "messages": msgs, "stream": False, "keep_alive": "30m",
                        "options": {"num_ctx": self.ctx, "temperature": 0.8, "num_predict": self.max_tokens}}
                if json_mode:
                    body["format"] = "json"
                r = self._post("/api/chat", body)
                text, inp, out = r["message"]["content"], r.get("prompt_eval_count", 0), r.get("eval_count", 0)
            else:
                body = {"model": model, "messages": msgs, "max_tokens": self.max_tokens, "temperature": 0.8}
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


class MockLLM(UsageMixin):
    """Offline stand-in: seeks food, eats when hungry, wanders and chats a little. NOT real thinking."""

    LINES = ["Found some berries over here!", "Anyone seen water nearby?",
             "Let's stick together.", "I'll look around the east side.", "Careful, rocks ahead."]

    def __init__(self, seed: int = 0):
        self._init_usage()
        self.rng = random.Random(seed)

    def complete(self, system: str, prompt: str, model: str | None = None, json_mode: bool = True) -> str:
        self._record("mock", 0, 0)
        rng = self.rng
        if "SUMMARIZE_MEMORIES" in prompt:
            lines = prompt.split("New memories to fold in:\n", 1)[-1].split("\n\nWrite the updated")[0].splitlines()
            return "I remember: " + " ".join(l.split(": ", 1)[-1] for l in lines)[:600]
        if "CHAT_WITH_HUMAN" in prompt:
            who = re.search(r"You are (\w+),", system)
            return json.dumps(dict(thought="The human spoke to me, I should answer.",
                                   message=f"[MOCK MODE - scripted, not a real reply] This is {who.group(1) if who else 'me'}."))
        hunger = int(re.search(r"Hunger: (\d+)", prompt).group(1))
        carried = int(re.search(r"Food carried: (\d+)", prompt).group(1))
        seeds = int(re.search(r"Seeds: (\d+)", prompt).group(1))
        reach = "reach to gather: yes" in prompt
        mats = int(re.search(r"within reach: (\d+)", prompt).group(1))
        mat_have = sum(int(x) for x in re.findall(r"(?:Wood|Stone): (\d+)", prompt))
        friend = re.search(r"Agents in view: (\w+) \[", prompt)
        tendable = int(re.search(r"to tend: (\d+)", prompt).group(1))
        m = re.search(r"Nearest food: dx=(-?\d+) dy=(-?\d+)", prompt)
        partner = re.search(r"have a child right now with: (\w+)", prompt)
        asked = re.search(r"Choose procreate with to=(\w+)", prompt)
        near = re.search(r"Agents in view: (\w+) \[", prompt)
        if partner or asked:
            return json.dumps(dict(thought="We love each other; let's have a child.", action="procreate",
                                   to=(partner or asked).group(1), baby_name=rng.choice(["Tiko", "Mara", "Bo", "Lio"])))
        if carried and hunger > 45:
            d = dict(thought="I'm getting hungry, time to eat.", action="eat")
        elif reach and hunger > 20:
            d = dict(thought="Food is right here, grabbing it.", action="gather")
        elif mat_have >= 2 and rng.random() < 0.25:
            d = dict(thought="I have materials; let me build something useful.", action="build",
                     direction=rng.choice(["north", "south", "east", "west"]),
                     title=rng.choice(["shelter", "sign", "storage hut", "bridge"]),
                     message=rng.choice(["Meet here to share news.", "A safe place to rest.", "Free food storage."]))
        elif mats and mat_have < 4 and rng.random() < 0.5:
            d = dict(thought="Gathering wood and stone for building.", action="gather")
        elif friend and rng.random() < 0.3:
            d = dict(thought=f"Let me chat with {friend.group(1)}.", action="say", to=friend.group(1),
                     message=rng.choice(self.LINES), role=rng.choice(["", "", "farmer", "builder", "storyteller"]))
        elif tendable and rng.random() < 0.8:
            d = dict(thought="This plant needs tending.", action="tend")
        elif seeds and rng.random() < 0.5:
            d = dict(thought="I'll plant a seed and start a little farm.", action="plant",
                     direction=rng.choice(["north", "south", "east", "west"]))
        elif near and rng.random() < 0.5:
            d = dict(thought=f"I like {near.group(1)}; let me show it.", action="court", to=near.group(1),
                     message="You make this world brighter.")
        elif m and rng.random() < 0.9:
            dx, dy = int(m.group(1)), int(m.group(2))
            dirn = ("east" if dx > 0 else "west") if abs(dx) >= abs(dy) and dx else ("south" if dy > 0 else "north")
            d = dict(thought="I can sense food nearby, heading for it.", action="move", direction=dirn,
                     remember="food is to the " + dirn)
        elif rng.random() < 0.05:
            d = dict(thought="An idea!", action="invent", title="Shared Harvest",
                     message="Everyone brings extra food to the middle of the map.")
        elif rng.random() < 0.2:
            d = dict(thought="Let me tell the others something.", action="say", to="all", message=rng.choice(self.LINES))
        else:
            d = dict(thought="Nothing in sight, wandering.", action="move", direction=rng.choice(["north", "south", "east", "west"]))
        return json.dumps(d)


class RouterLLM:
    """Sends each call to the right backend based on the agent's model string."""

    def __init__(self, claude: ClaudeLLM | None = None, local: LocalLLM | None = None,
                 mock: MockLLM | None = None, notes: list[str] | None = None):
        self.claude, self.local, self.mock = claude, local, mock
        self.notes = notes or []
        self.default_model = LOCAL if local else HAIKU

    def complete(self, system: str, prompt: str, model: str | None = None, json_mode: bool = True) -> str:
        model = model or self.default_model
        if self.mock:
            return self.mock.complete(system, prompt, model, json_mode)
        if is_local(model):
            if not self.local:
                raise RuntimeError("no local model server available (is Ollama running?)")
            return self.local.complete(system, prompt, None if model == LOCAL else model[6:], json_mode)
        if not self.claude:
            raise RuntimeError("no ANTHROPIC_API_KEY set, so Claude models are unavailable")
        return self.claude.complete(system, prompt, model, json_mode)

    def usage(self) -> dict:
        parts = [b.usage() for b in (self.claude, self.local, self.mock) if b]
        models: dict = {}
        for u in parts:
            models.update(u["models"])
        costs = [u["cost"] for u in parts if u["models"]]
        return {"models": models, "calls": sum(u["calls"] for u in parts), "input": sum(u["input"] for u in parts),
                "output": sum(u["output"] for u in parts),
                "cost": None if (not costs or None in costs) else sum(costs)}

    def info(self) -> dict:
        return {"mock": bool(self.mock), "claude": bool(self.claude), "local": bool(self.local),
                "local_model": self.local.model if self.local else None, "notes": self.notes}
