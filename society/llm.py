"""LLM backends: Claude via the Anthropic API, or an offline mock for testing."""
import json
import os
import random
import re
import threading


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
        priced = bool(self.prices)
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
    def __init__(self, model: str = "claude-haiku-5-5", max_tokens: int = 500, prices: dict | None = None):
        self._init_usage(prices)
        import anthropic  # imported lazily so the mock works without the SDK

        self.client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, system: str, prompt: str, model: str | None = None) -> str:
        model = model or self.model
        resp = self.client.messages.create(
            model=model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        self._record(model, resp.usage.input_tokens, resp.usage.output_tokens)
        return "".join(b.text for b in resp.content if b.type == "text")


class MockLLM(UsageMixin):
    """Offline stand-in: seeks food, eats when hungry, wanders and chats a little."""

    LINES = ["Found some berries over here!", "Anyone seen water nearby?",
             "Let's stick together.", "I'll look around the east side.", "Careful, rocks ahead."]

    def __init__(self, seed: int = 0):
        self._init_usage()
        self.rng = random.Random(seed)

    def complete(self, system: str, prompt: str, model: str | None = None) -> str:
        self._record("mock", 0, 0)
        rng = self.rng
        if "CHAT_WITH_HUMAN" in prompt:
            who = re.search(r"You are (\w+),", system)
            return json.dumps(dict(thought="The human spoke to me, I should answer.",
                                   message=f"Hello, human! It's {who.group(1) if who else 'me'} - I'm busy surviving, but happy to chat. (mock reply)"))
        hunger = int(re.search(r"Hunger: (\d+)", prompt).group(1))
        carried = int(re.search(r"Food carried: (\d+)", prompt).group(1))
        seeds = int(re.search(r"Seeds: (\d+)", prompt).group(1))
        reach = "reach to gather: yes" in prompt
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


def make_llm(mock: bool = False, model: str | None = None, prices: dict | None = None):
    if mock or not os.environ.get("ANTHROPIC_API_KEY"):
        if not mock:
            print("[no ANTHROPIC_API_KEY set - using mock LLM]")
        return MockLLM()
    return ClaudeLLM(model=model, prices=prices) if model else ClaudeLLM(prices=prices)
