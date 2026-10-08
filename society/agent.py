import json
import re
from dataclasses import dataclass, field

DIRS = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
ACTIONS = ("move", "gather", "eat", "say", "give", "plant", "tend", "court", "procreate", "invent", "wait")
VIEW_RADIUS = 5
SMELL_RADIUS = 10   # how far an agent can sense the nearest food
HEARING_RADIUS = 8
ADULT_AGE = 40          # turns before an agent can have children
LOVE_BOND = 50          # mutual bond needed to have a child
CHILD_FOOD_COST = 2     # each parent pays this much food
CHILD_COOLDOWN = 50


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
    symbol: str = "?"
    x: int = 0
    y: int = 0
    hunger: float = 20.0      # 0 = full, 100 = starving
    health: float = 100.0
    food: int = 0             # food items carried
    seeds: int = 0
    born: int = -999          # turn of birth (original agents are adults from the start)
    parents: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    bonds: dict[str, float] = field(default_factory=dict)  # how much this agent likes/loves others (0-100)
    memory: list[str] = field(default_factory=list)        # long-term notes the agent chose to remember
    pending: tuple | None = None                           # (partner, tick) of an outstanding procreate request
    last_child_tick: int = -999
    heart_tick: int = -99
    heard: list[str] = field(default_factory=list)      # messages not yet acted on
    history: list[dict] = field(default_factory=list)   # every thought + action so far
    last_say: str = ""
    last_say_tick: int = -99

    # ---- family / love ----
    def age(self, tick: int) -> int:
        return tick - self.born

    def adult(self, tick: int) -> bool:
        return self.age(tick) >= ADULT_AGE

    def related(self, o: "Agent") -> bool:
        """Parent/child or siblings (sharing a parent) can't be partners."""
        return (o.name in self.parents or self.name in o.parents
                or bool(set(self.parents) & set(o.parents)))

    def ready_for_child(self, tick: int) -> bool:
        return (self.adult(tick) and self.hunger < 85 and self.food >= CHILD_FOOD_COST
                and tick - self.last_child_tick >= CHILD_COOLDOWN)

    def child_partners(self, agents: list["Agent"], tick: int) -> list[str]:
        """Nearby agents this agent could have a child with right now."""
        if not self.ready_for_child(tick):
            return []
        return [o.name for o in agents if o is not self and o.ready_for_child(tick) and not self.related(o)
                and max(abs(o.x - self.x), abs(o.y - self.y)) <= 2
                and self.bonds.get(o.name, 0) >= LOVE_BOND and o.bonds.get(self.name, 0) >= LOVE_BOND]

    def system_prompt(self, others: list[str]) -> str:
        return (
            f"You are {self.name}, one of {len(others) + 1} agents living in a 2D tile world "
            f"(the others: {', '.join(others) or 'nobody yet'}). You are building a society together, with no instructions "
            "beyond your own goals - use your imagination: invent customs, names, tools, jobs, laws, friendships.\n"
            f"Role: {self.role}\nGoal: {self.goal}\n"
            f"Personality: {self.traits.describe()}\nSkills: {', '.join(self.skills) or 'none'}\n\n"
            "World: g grass, . sand, ~ water (impassable), # rock (impassable), f wild food bush (slow to regrow), "
            ", young plant, * ripe crop. North is up (y decreases), east is right. Uppercase letters are agents (you are @). "
            "Hunger rises every turn; at 100 you take damage and can die. Eating food lowers hunger.\n"
            "Each turn pick ONE action:\n"
            '  move    - {"direction": "north|south|east|west"}\n'
            "  gather  - pick food from a bush / ripe crop on your tile or adjacent (bushes sometimes yield a seed)\n"
            "  eat     - eat one carried food (hunger -40)\n"
            '  say     - {"to": "<name, all, or Human>", "message": "..."} heard within 8 tiles\n'
            '  give    - {"to": "<name>"} hand one carried food to an adjacent agent\n'
            '  plant   - {"direction": "..."} put a carried seed into an adjacent grass tile\n'
            "  tend    - work on a young plant within reach to help it grow\n"
            '  court   - {"to": "<name>", "message": "..."} show affection to an agent within 3 tiles\n'
            f'  procreate - {{"to": "<name>", "baby_name": "..."}} both partners must choose it (needs mutual love >= {LOVE_BOND}, '
            f"adults, nearby, each pays {CHILD_FOOD_COST} food)\n"
            '  invent  - {"title": "...", "message": "describe your idea, custom, tool or law"} shared with the whole society\n'
            "  wait\n"
            "A human observer may speak to you (\"The Human says ...\"); they are not in the world. "
            'Reply with a say action to "Human" when they ask something.\n'
            "Reply ONLY with JSON; add an optional \"remember\" string for something worth keeping in long-term memory, e.g.\n"
            '{"thought": "<1-2 sentences of private reasoning>", "action": "move", "direction": "east", "remember": "berries near the lake"}'
        )

    def observe(self, world, agents: list["Agent"], tick: int, ideas: list[str]) -> str:
        others = {(a.x, a.y): a.symbol for a in agents if a is not self}
        age = self.age(tick)
        lines = [f"Turn {tick}. You are at ({self.x}, {self.y})."
                 + ("" if self.adult(tick) else f" You are a child ({age} turns old); you become an adult at {ADULT_AGE}."),
                 f"Hunger: {int(self.hunger)}/100. Health: {int(self.health)}/100. Food carried: {self.food}. Seeds: {self.seeds}.",
                 f"Your surroundings (@ = you):\n{world.view(self.x, self.y, VIEW_RADIUS, others)}"]
        near = [f"{a.name} [{a.symbol}] dx={a.x - self.x} dy={a.y - self.y}" for a in agents
                if a is not self and max(abs(a.x - self.x), abs(a.y - self.y)) <= VIEW_RADIUS]
        lines.append("Agents in view: " + ("; ".join(near) or "none"))
        food = world.food_near(self.x, self.y, SMELL_RADIUS)
        if food:
            fx, fy = food[0]
            lines.append(f"Nearest food: dx={fx - self.x} dy={fy - self.y}")
        else:
            lines.append("Nearest food: none sensed")
        lines.append(f"Food within reach to gather: {'yes' if world.food_near(self.x, self.y, 1) else 'no'}")
        lines.append(f"Young plants within reach to tend: {len(world.plants_near(self.x, self.y, 1))}")
        feelings = sorted(((b, n) for n, b in self.bonds.items() if b >= 10), reverse=True)
        if feelings:
            lines.append("Your feelings toward others: " + ", ".join(
                f"{n} {int(b)}" + (" (in love)" if b >= LOVE_BOND else "") for b, n in feelings))
        partners = self.child_partners(agents, tick)
        if partners:
            lines.append("You could have a child right now with: " + ", ".join(partners))
        if self.parents or self.children:
            lines.append(f"Family - parents: {', '.join(self.parents) or 'none'}; children: {', '.join(self.children) or 'none'}")
        if self.memory:
            lines.append("Your long-term memory:\n" + "\n".join("- " + m for m in self.memory[-10:]))
        if ideas:
            lines.append("Ideas invented by the society so far:\n" + "\n".join("- " + i for i in ideas))
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
        if not isinstance(data, dict):
            data = {}
        action = data.get("action") if data.get("action") in ACTIONS else "wait"
        to = data.get("to", "all")
        if to not in ("all", "Human") and to not in others:
            to = "all"
        return {"thought": str(data.get("thought") or raw[:200]).strip(), "action": action,
                "direction": data.get("direction"), "to": to,
                "message": str(data.get("message") or "").strip(),
                "title": str(data.get("title") or "").strip(),
                "baby_name": str(data.get("baby_name") or "").strip(),
                "remember": str(data.get("remember") or "").strip()}
