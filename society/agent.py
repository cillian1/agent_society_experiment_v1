import json
import re
from dataclasses import dataclass, field


@dataclass
class Traits:
    """Personality attributes, each 0.0 - 1.0."""
    openness: float = 0.5
    conscientiousness: float = 0.5
    extraversion: float = 0.5
    agreeableness: float = 0.5
    neuroticism: float = 0.5

    def describe(self) -> str:
        def lvl(v):
            return "very high" if v >= .8 else "high" if v >= .6 else "moderate" if v > .4 else "low" if v > .2 else "very low"
        return ", ".join(f"{k} {lvl(v)}" for k, v in vars(self).items())


@dataclass
class Agent:
    name: str
    role: str
    goal: str
    traits: Traits
    skills: list[str] = field(default_factory=list)
    resources: int = 10
    memory: list[str] = field(default_factory=list)  # messages heard so far

    def system_prompt(self, others: list[str]) -> str:
        return (
            f"You are {self.name}, a member of a small new society of {len(others) + 1} agents "
            f"({', '.join(others)} are the others).\n"
            f"Role: {self.role}\nGoal: {self.goal}\n"
            f"Personality: {self.traits.describe()}\n"
            f"Skills: {', '.join(self.skills) or 'none'}\n"
            f"You hold {self.resources} resource units.\n"
            "Stay in character. Each turn, speak to one agent or to everyone. "
            'Reply ONLY with JSON: {"to": "<name or all>", "message": "<1-2 sentences>"}'
        )

    def act(self, llm, others: list[str], max_memory: int = 12) -> dict:
        recent = "\n".join(self.memory[-max_memory:]) or "(nothing yet - you have just arrived)"
        raw = llm.complete(self.system_prompt(others), f"Recent conversation:\n{recent}\n\nYour turn.")
        return self._parse(raw, others)

    @staticmethod
    def _parse(raw: str, others: list[str]) -> dict:
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            data = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            data = {}
        to = data.get("to", "all")
        if to != "all" and to not in others:
            to = "all"
        return {"to": to, "message": str(data.get("message") or raw).strip()}

    def hear(self, sender: str, to: str, message: str):
        target = "everyone" if to == "all" else ("you" if to == self.name else to)
        self.memory.append(f"{sender} -> {target}: {message}")
