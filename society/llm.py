"""LLM backends: Claude via the Anthropic API, or an offline mock for testing."""
import json
import os
import random
import re


class ClaudeLLM:
    def __init__(self, model: str = "claude-haiku-5-5", max_tokens: int = 350):
        import anthropic  # imported lazily so the mock works without the SDK

        self.client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, system: str, prompt: str, model: str | None = None) -> str:
        resp = self.client.messages.create(
            model=model or self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")


class MockLLM:
    """Offline stand-in: seeks food, eats when hungry, wanders and chats a little."""

    LINES = ["Found some berries over here!", "Anyone seen water nearby?",
             "Let's stick together.", "I'll look around the east side.", "Careful, rocks ahead."]

    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)

    def complete(self, system: str, prompt: str, model: str | None = None) -> str:
        hunger = int(re.search(r"Hunger: (\d+)", prompt).group(1))
        carried = int(re.search(r"Food carried: (\d+)", prompt).group(1))
        reach = "reach to gather: yes" in prompt
        m = re.search(r"Nearest food: dx=(-?\d+) dy=(-?\d+)", prompt)
        if carried and hunger > 50:
            d = dict(thought="I'm getting hungry, time to eat.", action="eat")
        elif reach:
            d = dict(thought="Food is right here, grabbing it.", action="gather")
        elif m and self.rng.random() < 0.9:
            dx, dy = int(m.group(1)), int(m.group(2))
            dirn = ("east" if dx > 0 else "west") if abs(dx) >= abs(dy) and dx else ("south" if dy > 0 else "north")
            d = dict(thought="I can sense food nearby, heading for it.", action="move", direction=dirn)
        elif self.rng.random() < 0.2:
            d = dict(thought="Let me tell the others something.", action="say", to="all",
                     message=self.rng.choice(self.LINES))
        else:
            d = dict(thought="Nothing in sight, wandering.", action="move",
                     direction=self.rng.choice(["north", "south", "east", "west"]))
        return json.dumps(d)


def make_llm(mock: bool = False, model: str | None = None):
    if mock or not os.environ.get("ANTHROPIC_API_KEY"):
        if not mock:
            print("[no ANTHROPIC_API_KEY set - using mock LLM]")
        return MockLLM()
    return ClaudeLLM(model=model) if model else ClaudeLLM()
