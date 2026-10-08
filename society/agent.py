import json
import re
from dataclasses import dataclass, field

DIRS = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
ACTIONS = ("move", "gather", "eat", "say", "give", "plant", "tend", "build", "court", "procreate", "invent", "wait")
VIEW_RADIUS = 6
SMELL_RADIUS = 10   # how far an agent can sense the nearest food
HEARING_RADIUS = 8
ADULT_AGE = 40          # days before an agent can have children
OLD_AGE = 500           # days after which an agent may die of old age
LOVE_BOND = 50          # mutual bond needed to have a child
FRIEND_BOND = 25
CHILD_FOOD_COST = 2     # each parent pays this much food
CHILD_COOLDOWN = 50
BUILD_COST = 2          # wood/stone needed per structure
KEEP_RECENT = 25        # memory lines shown verbatim; older ones are folded into the summary
COMPACT_AFTER = 20      # unsummarised old lines that trigger a summarisation
DEFAULT_GOAL = ("Survive, make friends, and build a life and a society together with the others. "
                "Nobody tells you what to do or who to be - decide for yourselves what matters.")


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
    traits: Traits
    role: str = ""            # no assigned role: agents invent and claim their own
    goal: str = DEFAULT_GOAL
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
    wood: int = 0
    stone: int = 0
    born: int = -999          # turn of birth (age = tick - born); originals get a random age at spawn
    parents: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    bonds: dict[str, float] = field(default_factory=dict)  # how much this agent likes/loves others (0-100)
    log: list[str] = field(default_factory=list)           # lifelong memory: everything notable that happened to it
    summary: str = ""                                      # compressed version of the oldest part of the log
    sum_upto: int = 0                                      # log[:sum_upto] is covered by the summary
    pending: tuple | None = None                           # (partner, tick) of an outstanding procreate request
    last_child_tick: int = -999
    heart_tick: int = -99
    heard: list[str] = field(default_factory=list)      # messages not yet acted on
    history: list[dict] = field(default_factory=list)   # every thought + action so far
    last_say: str = ""
    last_say_to: str = "all"
    last_say_tick: int = -99
    chat: list[tuple[str, str]] = field(default_factory=list)  # (speaker, text) conversation with the Human

    # ---- family / age ----
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

    # ---- prompts ----
    def system_prompt(self, others: list[str]) -> str:
        return (
            f"You are {self.name}, one of {len(others) + 1} agents living in a 2D tile world "
            f"(the others: {', '.join(others) or 'nobody yet'}). Nobody has a job or a role until they invent one; "
            "nobody is anybody's family until children are born. You are free to do what you want: explore, "
            "talk, make friends (or enemies), plan together, farm, build, invent customs, tools, jobs and laws. "
            "Be creative and resourceful, and think about how to solve your problems in new ways. "
            "Talking is valuable: answer people who speak to you, share what you know, ask questions, make deals. "
            "You remember everything that has happened to you.\n"
            f"Goal: {self.goal}\nPersonality: {self.traits.describe()}\n\n"
            "World: g grass, . sand, ~ water (impassable), # rock (impassable), ^ tree (impassable), f wild food bush "
            "(slow to regrow), , young plant, * ripe crop, & a structure someone built. North is up (y decreases), "
            "east is right. Uppercase letters are agents (you are @). "
            "Hunger rises every turn; at 100 you take damage and can starve. Eating food lowers hunger. "
            "Life lasts roughly 500-700 days; one turn is one day.\n"
            "Each turn pick ONE action:\n"
            '  move    - {"direction": "north|south|east|west"}\n'
            "  gather  - take from an adjacent/own-tile food bush or ripe crop (food, sometimes seeds), tree (wood) or rock (stone)\n"
            "  eat     - eat one carried food (hunger -40)\n"
            '  say     - {"to": "<name or all>", "message": "..."} heard within 8 tiles; talk to people!\n'
            '  give    - {"to": "<name>"} hand one carried food to an adjacent agent\n'
            '  plant   - {"direction": "..."} put a carried seed into an adjacent grass tile\n'
            "  tend    - work on a young plant within reach to help it grow (faster with a helper)\n"
            f'  build   - {{"direction": "...", "title": "<what you build: house, wall, bridge, sign, anything>", "message": "<description or sign text>"}} '
            f"costs {BUILD_COST} wood/stone; bridges/paths/floors can be walked on, everything else blocks. Water only takes bridges/docks.\n"
            '  court   - {"to": "<name>", "message": "..."} show affection to an agent within 3 tiles\n'
            f'  procreate - {{"to": "<name>", "baby_name": "..."}} both partners must choose it (needs mutual love >= {LOVE_BOND}, '
            f"adults, nearby, each pays {CHILD_FOOD_COST} food)\n"
            '  invent  - {"title": "...", "message": "describe your idea, custom, tool or law"} shared with the whole society\n'
            "  wait\n"
            "A human observer outside the world sometimes talks to you; you answer them directly and in character "
            "(that happens in a separate chat, so it does not use up your turn).\n"
            "Reply ONLY with JSON. Optional extra fields: \"remember\" (a note to your future self) and \"role\" "
            "(claim or change your own role/title whenever you like), e.g.\n"
            '{"thought": "<1-2 sentences of private reasoning>", "action": "say", "to": "Ada", "message": "Want to farm together?", "role": "farmer"}'
        )

    def observe(self, world, agents: list["Agent"], tick: int, ideas: list[str]) -> str:
        others = {(a.x, a.y): a.symbol for a in agents if a is not self}
        age = self.age(tick)
        stage = "adult" if self.adult(tick) else f"child - you become an adult at {ADULT_AGE}"
        lines = [f"Day {tick}. You are at ({self.x}, {self.y}). You are {age} days old ({stage}).",
                 "Your role: " + (self.role or 'none yet - claim one by adding "role" to your reply, or stay free') + ".",
                 f"Hunger: {int(self.hunger)}/100. Health: {int(self.health)}/100. Food carried: {self.food}. "
                 f"Seeds: {self.seeds}. Wood: {self.wood}. Stone: {self.stone}.",
                 f"Your surroundings (@ = you):\n{world.view(self.x, self.y, VIEW_RADIUS, others)}"]
        near = [f"{a.name} [{a.symbol}] dx={a.x - self.x} dy={a.y - self.y}" + (f", role: {a.role}" if a.role else "")
                + f", {a.age(tick)} days old" for a in agents
                if a is not self and max(abs(a.x - self.x), abs(a.y - self.y)) <= VIEW_RADIUS]
        lines.append("Agents in view: " + ("; ".join(near) or "none"))
        built = [f"{s['kind']} at dx={dx} dy={dy}" + (f' ("{s["text"]}")' if s["text"] else "") + f" built by {s['by']}"
                 for dx, dy, s in world.structures_near(self.x, self.y, VIEW_RADIUS)][:6]
        if built:
            lines.append("Structures in view: " + "; ".join(built))
        food = world.food_near(self.x, self.y, SMELL_RADIUS)
        if food:
            fx, fy = food[0]
            lines.append(f"Nearest food: dx={fx - self.x} dy={fy - self.y}")
        else:
            lines.append("Nearest food: none sensed")
        lines.append(f"Food within reach to gather: {'yes' if world.food_near(self.x, self.y, 1) else 'no'}")
        mats = [o for o in world.gather_options(self.x, self.y) if world.tile(*o) in ("tree", "rock")]
        lines.append(f"Materials (trees/rocks) within reach: {len(mats)}")
        lines.append(f"Young plants within reach to tend: {len(world.plants_near(self.x, self.y, 1))}")
        feelings = sorted(((b, n) for n, b in self.bonds.items() if b >= 10), reverse=True)
        if feelings:
            lines.append("Your feelings toward others: " + ", ".join(
                f"{n} {int(b)}" + (" (in love)" if b >= LOVE_BOND else " (friend)" if b >= FRIEND_BOND else "")
                for b, n in feelings))
        partners = self.child_partners(agents, tick)
        if partners:
            lines.append("You could have a child right now with: " + ", ".join(partners))
        if self.parents or self.children:
            lines.append(f"Family - parents: {', '.join(self.parents) or 'none'}; children: {', '.join(self.children) or 'none'}")
        if self.summary:
            lines.append("What you remember of your earlier life (summary):\n" + self.summary)
        if self.log[self.sum_upto:]:
            lines.append("Your recent memories (oldest first):\n" + "\n".join(
                "- " + m for m in self.log[max(self.sum_upto, len(self.log) - KEEP_RECENT - COMPACT_AFTER):]))
        if ideas:
            lines.append("Ideas invented by the society so far:\n" + "\n".join("- " + i for i in ideas))
        lines.append("Messages heard this turn:\n" + ("\n".join(self.heard) or "(none)"))
        recent = [f"t{h['tick']}: {h['action']} -> {h['result']}" for h in self.history[-4:]]
        lines.append("Your last few actions:\n" + ("\n".join(recent) or "(none yet)"))
        return "\n".join(lines) + "\n\nWhat do you do?"

    # ---- memory ----
    def needs_compaction(self) -> bool:
        return len(self.log) - self.sum_upto > KEEP_RECENT + COMPACT_AFTER

    def compact(self, llm, model: str | None = None):
        """Fold the oldest unsummarised memories into the running summary (keeps prompts small, loses nothing)."""
        upto = len(self.log) - KEEP_RECENT
        old = self.log[self.sum_upto:upto]
        prompt = ("SUMMARIZE_MEMORIES\nYou are keeping the memory of a person named " + self.name + ".\n"
                  f"Current summary of their earlier life:\n{self.summary or '(none)'}\n\nNew memories to fold in:\n"
                  + "\n".join(old) + "\n\nWrite the updated summary in the first person, under 200 words. Keep names, "
                  "relationships, promises, places, inventions and anything important; drop trivia.")
        text = llm.complete("You write concise, faithful memory summaries.", prompt, model=model).strip()
        if text:
            self.summary, self.sum_upto = text, upto

    # ---- decisions ----
    def decide(self, llm, prompt: str, others: list[str]) -> dict:
        raw = llm.complete(self.system_prompt(others), prompt, model=self.model)
        return self.parse(raw, others)

    def reply_prompt(self, situation: str, human_msg: str, also_to: list[str]) -> str:
        talk = "\n".join(f"{who}: {t}" for who, t in self.chat[-8:]) or "(this is the first time they speak to you)"
        also = f" (they said it to {', '.join(also_to)} as well)" if also_to else ""
        return (f"CHAT_WITH_HUMAN\nYour current situation:\n{situation}\n\nYour earlier conversation with the Human:\n{talk}\n\n"
                f'The Human (an observer outside the world) just said to you{also}: "{human_msg}"\n'
                "Answer them directly and in character in 1-3 sentences: reply to what they actually say or ask, and "
                "mention what is going on in your life if it fits. Reply ONLY with JSON: "
                '{"thought": "<private reasoning>", "message": "<what you say to them>"}')

    def reply(self, llm, situation: str, human_msg: str, others: list[str], also_to: list[str]) -> dict:
        raw = llm.complete(self.system_prompt(others), self.reply_prompt(situation, human_msg, also_to), model=self.model)
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            data = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        return {"thought": str(data.get("thought") or "").strip(),
                "message": str(data.get("message") or (raw if not data else "")).strip()}

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
        s = lambda k: str(data.get(k) or "").strip()
        return {"thought": s("thought") or raw[:200].strip(), "action": action,
                "direction": data.get("direction"), "to": to, "message": s("message"), "title": s("title"),
                "baby_name": s("baby_name"), "remember": s("remember"), "role": s("role")}
