"""Plain data: an agent's personality, body, possessions, relationships and memories."""
from dataclasses import asdict, dataclass, field, fields

from .config import (ADULT_AGE, BABY_DAYS, CHILD_COOLDOWN, CHILD_FOOD_COST, COMPACT_AFTER, KEEP_RECENT, LOVE_BOND,
                     OLD_AGE, TOOLS)

DEFAULT_GOAL = ("Survive, make friends, and build a life and a society together with the others. "
                "Nobody assigns you a role - decide for yourselves what matters.")


@dataclass
class Traits:
    """Big-Five personality, each 0.0 - 1.0."""
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
    sex: str = "female"                # "female" | "male" - a woman carries the baby
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
        return "baby" if age < BABY_DAYS else "child" if age < ADULT_AGE else "elder" if age >= OLD_AGE else "adult"

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
    def has_tool(self, use: str) -> bool:
        return any(w in i["name"].lower() for i in self.items for w in TOOLS[use])

    def materials(self) -> int:
        return self.wood + self.stone

    def spend_materials(self, n: int):
        use_w = min(self.wood, n)
        self.wood -= use_w
        self.stone -= n - use_w

    # ---- memory ----
    def remember(self, tick: int, text: str):
        self.log.append(f"t{tick}: {text[:260]}")

    def needs_compaction(self) -> bool:
        return len(self.log) - self.sum_upto > KEEP_RECENT + COMPACT_AFTER

    # ---- saving ----
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Agent":
        known = {f.name for f in fields(cls)}
        d = {k: v for k, v in d.items() if k in known}
        d["traits"] = Traits(**d.get("traits", {}))
        return cls(**d)
