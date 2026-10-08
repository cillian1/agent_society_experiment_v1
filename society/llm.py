"""LLM backends: Claude via the Anthropic API, or an offline mock for testing."""
import os
import random


class ClaudeLLM:
    def __init__(self, model: str = "claude-haiku-5-5", max_tokens: int = 300):
        import anthropic  # imported lazily so the mock works without the SDK

        self.client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, system: str, prompt: str) -> str:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")


class MockLLM:
    """Deterministic-ish stand-in so the simulation runs with no API key."""

    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)

    def complete(self, system: str, prompt: str) -> str:
        line = self.rng.choice(
            ["Let's pool our resources.", "I disagree with that plan.",
             "What does everyone think we should build first?",
             "I'll take care of that.", "Can we agree on some rules?"]
        )
        return f'{{"to": "all", "message": "{line}"}}'


def make_llm(mock: bool = False, model: str | None = None):
    if mock or not os.environ.get("ANTHROPIC_API_KEY"):
        if not mock:
            print("[no ANTHROPIC_API_KEY set - using mock LLM]")
        return MockLLM()
    return ClaudeLLM(model=model) if model else ClaudeLLM()
