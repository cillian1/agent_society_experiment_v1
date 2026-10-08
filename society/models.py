"""Plain data: an agent's personality, body, possessions, relationships and memories."""
from dataclasses import asdict, dataclass, field, fields

from .config import (ADULT_AGE, BABY_DAYS, CHILD_COOLDOWN, CHILD_FOOD_COST, COMPACT_AFTER, KEEP_RECENT, LOVE_BOND,
                     OLD_AGE, TOOLS)

DEFAULT_GOAL = ("Survive, make friends, and build a life and a society together with the others. "
                "Nobody assigns you a role - decide for yourselves what matters.")


TRAIT_INFO = {     # personality, 0.0-1.0: shapes behaviour, and each one also has a real effect
    "curious": "explores and tries bold new things",
    "social": "others warm to them faster; time together bonds more",
    "kind": "easier to win over; shares, feeds and cares for others",
    "driven": "works faster on construction and sticks to plans",
}
ABILITY_INFO = {   # body and mind, 1-10
    "strength": "extra wood & stone, faster building",
    "speed": "tiles per move",
    "endurance": "gets hungry more slowly, lives longer",
    "wits": "sees and senses further, better farmer, remembers more",
}


@dataclass
class Traits:
    """Personality, each 0.0 - 1.0."""
    curious: float = 0.5
    social: float = 0.5
    kind: float = 0.5
    driven: float = 0.5

    def describe(self) -> str:
        def lvl(v):
            return "very" if v >= .8 else "quite" if v >= .6 else "somewhat" if v > .4 else "not very" if v > .2 else "not at all"
        return ", ".join(f"{lvl(v)} {k}" for k, v in vars(self).items())

    @classmethod
    def from_dict(cls, d: dict) -> "Traits":
        old = {"openness": "curious", "extraversion": "social", "agreeableness": "kind", "conscientiousness": "driven"}
        d = {old.get(k, k): v for k, v in (d or {}).items()}
        return cls(**{k: v for k, v in d.items() if k in TRAIT_INFO})


@dataclass
class Abilities:
    """Body and mind, each 1-10. Unlike personality these change what an agent can physically do."""
    strength: int = 5
    speed: int = 5
    endurance: int = 5
    wits: int = 5

    @classmethod
    def random(cls, rng) -> "Abilities":
        return cls(**{k: rng.randint(2, 9) for k in ABILITY_INFO})

    @classmethod
    def inherit(cls, mum: "Abilities", dad: "Abilities", rng) -> "Abilities":
        return cls(**{k: max(1, min(10, round((getattr(mum, k) + getattr(dad, k)) / 2 + rng.choice([-1, 0, 0, 1]))))
                      for k in ABILITY_INFO})

    @classmethod
    def from_dict(cls, d: dict) -> "Abilities":
        d = dict(d or {})
        if "wits" not in d and ("intelligence" in d or "perception" in d):          # older saves
            d["wits"] = round((d.get("intelligence", 5) + d.get("perception", 5)) / 2)
        return cls(**{k: v for k, v in d.items() if k in ABILITY_INFO})

    # ---- effects ----
    def steps(self) -> int:
        return 2 + self.speed // 4                       # 2-4 tiles per move

    def view(self) -> int:
        return 4 + (self.wits + 1) // 3                  # 4-7 tiles

    def smell(self) -> int:
        return 6 + self.wits                             # 7-16 tiles

    def hunger_factor(self) -> float:
        return 1.25 - self.endurance * 0.05              # 1.2x (1) .. 0.75x (10)

    def memory(self) -> int:
        return 15 + 2 * self.wits                        # memories recalled word for word

    def lifespan(self) -> int:
        return 600 + 80 * self.endurance                 # 680 .. 1400 days

    def describe(self) -> str:
        return ", ".join(f"{k} {getattr(self, k)} ({ABILITY_INFO[k]})" for k in ABILITY_INFO)


@dataclass
class Agent:
    name: str
    traits: Traits
    sex: str = "female"                # "female" | "male" - a woman carries the baby
    abilities: Abilities = field(default_factory=Abilities)
    plan: str = ""                     # the agent's own current plan, kept from day to day
    ambition: str = ""                 # long-term goal it sets for itself when reflecting
    queue: list[dict] = field(default_factory=list)          # follow-up actions it lined up ("next")
    advice: list[list] = field(default_factory=list)         # [day, text] what Sol the mentor told it
    task: dict | None = None                                 # ongoing multi-hour work, e.g. {"type": "build", "id": 3}
    last_reflect: int = -999
    role: str = ""                     # agents invent and claim their own roles
    goal: str = DEFAULT_GOAL
    model: str | None = None           # brain: "local", "local:<name>", or a Claude model id
    color: str = "#ffffff"
    symbol: str = "?"                  # letter on the ASCII map other agents see
    # body & position
    x: int = 0
    y: int = 0
    hunger: float = 20.0               # 0 = full, 100 = starving
    health: float = 100.0
    born: int = -999                   # day of birth; settlers get a random age at spawn
    # possessions
    food: int = 0
    seeds: int = 0
    wood: int = 0
    stone: int = 0
    items: list[dict] = field(default_factory=list)          # crafted objects {name, text, by, tick}
    # relationships
    parents: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    bonds: dict[str, float] = field(default_factory=dict)    # feelings toward others, 0-100
    pending: list | None = None                              # [partner, day] of an open request for a child
    pregnancy: dict | None = None                            # {"father", "conceived", "due", "name"} while pregnant
    last_child_tick: int = -999
    # mind
    log: list[str] = field(default_factory=list)             # lifelong memory
    summary: str = ""                                        # summary of log[:sum_upto]
    sum_upto: int = 0
    heard: list[str] = field(default_factory=list)           # messages waiting for the next turn
    history: list[dict] = field(default_factory=list)        # every thought + action
    chat: list[list[str]] = field(default_factory=list)      # [speaker, text] conversation with the Human
    orders: list[list] = field(default_factory=list)         # [day, text] requests from the Human
    authority: str = "leader"                                # how it treats the Human
    # exploration & misc
    discoveries: int = 0
    unreported: dict = field(default_factory=dict)
    last_fish_tick: int = -99
    heart_tick: int = -99
    last_say: str = ""
    last_say_to: str = "all"
    last_say_tick: int = -99

    # ---- life ----
    def age(self, tick: int) -> int:
        return tick - self.born

    def adult(self, tick: int) -> bool:
        return self.age(tick) >= ADULT_AGE

    def is_baby(self, tick: int) -> bool:
        return self.age(tick) < BABY_DAYS

    def stage(self, tick: int) -> str:
        age = self.age(tick)
        return "baby" if age < BABY_DAYS else "child" if age < ADULT_AGE else \
            "elder" if age >= min(OLD_AGE, (self.abilities.lifespan() - 150) * 24) else "adult"

    def word(self, tick: int | None = None) -> str:
        young = tick is not None and not self.adult(tick)
        return ("girl" if young else "woman") if self.sex == "female" else ("boy" if young else "man")

    def related(self, o: "Agent") -> bool:
        """Parent/child or siblings can't be partners."""
        return o.name in self.parents or self.name in o.parents or bool(set(self.parents) & set(o.parents))

    def ready_for_child(self, tick: int) -> bool:
        return (self.adult(tick) and self.hunger < 85 and self.food >= CHILD_FOOD_COST and not self.pregnancy
                and tick - self.last_child_tick >= CHILD_COOLDOWN)

    def child_partners(self, agents: list["Agent"], tick: int) -> list[str]:
        if not self.ready_for_child(tick):
            return []
        return [o.name for o in agents if o is not self and o.sex != self.sex and o.ready_for_child(tick)
                and not self.related(o)
                and self.dist(o) <= 2
                and self.bonds.get(o.name, 0) >= LOVE_BOND and o.bonds.get(self.name, 0) >= LOVE_BOND]

    def dist(self, o) -> int:
        return max(abs(o.x - self.x), abs(o.y - self.y))

    # ---- things ----
    def charm(self) -> float:
        """How quickly others warm to this agent (social people are liked faster)."""
        return 0.7 + 0.8 * self.traits.social             # 0.7x .. 1.5x

    def has_tool(self, use: str) -> bool:
        return any(i.get("use") == use or any(w in i["name"].lower() for w in TOOLS[use]) for i in self.items)

    def materials(self) -> int:
        return self.wood + self.stone

    def spend_materials(self, n: int):
        use_w = min(self.wood, n)
        self.wood -= use_w
        self.stone -= n - use_w

    # ---- memory ----
    def remember(self, tick: int, text: str):
        from .clock import short
        self.log.append(f"[{short(tick)}] {text[:260]}")

    def needs_compaction(self) -> bool:
        return len(self.log) - self.sum_upto > KEEP_RECENT + COMPACT_AFTER

    # ---- saving ----
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Agent":
        known = {f.name for f in fields(cls)}
        d = {k: v for k, v in d.items() if k in known}
        d["traits"] = Traits.from_dict(d.get("traits", {}))
        d["abilities"] = Abilities.from_dict(d.get("abilities", {}))
        return cls(**d)
