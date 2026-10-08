import json
import re
from dataclasses import dataclass, field

DIRS = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
ACTIONS = ("move", "gather", "eat", "say", "give", "wait")
VIEW_RADIUS = 5
SMELL_RADIUS = 10   # how far an agent can sense the nearest food
HEARING_RADIUS = 8


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
    model: str | None = None  # per-agent Claude model override (None = society default)
    color: str = "#ffffff"
    x: int = 0
    y: int = 0
    hunger: float = 20.0      # 0 = full, 100 = starving
    food: int = 0             # food items carried
    heard: list[str] = field(default_factory=list)      # messages not yet acted on
    history: list[dict] = field(default_factory=list)   # every thought + action so far
    last_say: str = ""
    last_say_tick: int = -99

    def system_prompt(self, others: list[str]) -> str:
        return (
            f"You are {self.name}, one of {len(others) + 1} agents living in a 2D tile world "
            f"(the others: {', '.join(others)}).\n"
            f"Role: {self.role}\nGoal: {self.goal}\n"
            f"Personality: {self.traits.describe()}\nSkills: {', '.join(self.skills) or 'none'}\n\n"
            "World: tiles are G grass, . sand, ~ water (impassable), # rock (impassable), F food (berry bush). "
            "North is up (y decreases), east is right. Hunger rises every turn; eat food to lower it.\n"
            "Each turn pick ONE action:\n"
            '  move  - {"direction": "north|south|east|west"}\n'
            "  gather - pick food from your tile or an adjacent tile\n"
            "  eat   - eat one carried food (hunger -40)\n"
            '  say   - {"to": "<name, all, or Human>", "message": "..."} heard by agents within 8 tiles\n'
            '  give  - {"to": "<name>"} hand one carried food to an adjacent agent\n'
            "  wait\n"
            "A human observer may speak to you (\"The Human says ...\"); they are not in the world. "
            'Reply with a say action to "Human" when they ask something.\n'
            "Stay in character and pursue your goal. Reply ONLY with JSON, e.g.\n"
            '{"thought": "<1-2 sentences of private reasoning>", "action": "move", "direction": "east"}'
        )

    def observe(self, world, agents: list["Agent"], tick: int) -> str:
        others = {(a.x, a.y): a.name[0] for a in agents if a is not self}
        lines = [f"Turn {tick}. You are at ({self.x}, {self.y}).",
                 f"Hunger: {int(self.hunger)}/100. Food carried: {self.food}.",
                 f"Your surroundings (@ = you, letters = other agents' initials):\n"
                 f"{world.view(self.x, self.y, VIEW_RADIUS, others)}"]
        near = [f"{a.name} at dx={a.x - self.x} dy={a.y - self.y}" for a in agents
                if a is not self and max(abs(a.x - self.x), abs(a.y - self.y)) <= VIEW_RADIUS]
        lines.append("Agents in view: " + ("; ".join(near) or "none"))
        food = world.food_near(self.x, self.y, SMELL_RADIUS)
        if food:
            fx, fy = food[0]
            lines.append(f"Nearest food: dx={fx - self.x} dy={fy - self.y}")
        else:
            lines.append("Nearest food: none sensed")
        reach = bool(world.food_near(self.x, self.y, 1))
        lines.append(f"Food within reach to gather: {'yes' if reach else 'no'}")
        lines.append("Messages heard:\n" + ("\n".join(self.heard) or "(none)"))
        recent = [f"t{h['tick']}: {h['action']} -> {h['result']}" for h in self.history[-4:]]
        lines.append("Your recent actions:\n" + ("\n".join(recent) or "(none yet)"))
        return "\n".join(lines) + "\n\nWhat do you do?"

    def decide(self, llm, prompt: str, others: list[str]) -> dict:
        raw = llm.complete(self.system_prompt(others), prompt, model=self.model)
        return self.parse(raw, others)

    @staticmethod
    def parse(raw: str, others: list[str]) -> dict:
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            data = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            data = {}
        action = data.get("action") if data.get("action") in ACTIONS else "wait"
        to = data.get("to", "all")
        if to not in ("all", "Human") and to not in others:
            to = "all"
        return {"thought": str(data.get("thought") or raw[:200]).strip(), "action": action,
                "direction": data.get("direction"), "to": to,
                "message": str(data.get("message") or "").strip()}
