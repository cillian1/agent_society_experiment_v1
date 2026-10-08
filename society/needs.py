"""What people feel and what they're good at.

Needs (0 = satisfied, 100 = desperate) rise and fall with what happens: rest, belonging, safety, status and curiosity.
Personality decides which need is loudest, and the loudest need (plus grief or anger) gives the mood the model is
told about - so a lonely agent seeks company and a humiliated one holds a grudge.

Skills grow by doing (children learn twice as fast) and make people better at what they practise; experts can teach."""
from . import clock

NEEDS = {
    "rest": "rest",
    "belonging": "company and closeness",
    "safety": "safety (food in hand, shelter, warmth)",
    "status": "respect and achievement",
    "curiosity": "something new to see or try",
}
START = {"rest": 10, "belonging": 25, "safety": 20, "status": 30, "curiosity": 35}
SKILLS = {
    "farming": "planting, tending and harvesting crops",
    "gathering": "foraging food and getting wood and stone",
    "building": "construction work",
    "crafting": "making tools and objects",
    "hunting": "hunting and taming animals",
}
SKILL_OF = {"plant": "farming", "tend": "farming", "work": "building", "build": "building", "craft": "crafting",
            "hunt": "hunting", "tame": "hunting"}


def level(xp: float) -> int:
    return min(10, int((max(0.0, xp) / 12) ** 0.5))     # 12 xp = level 1, 300 = 5, 1200 = 10


def skill(a, name: str) -> int:
    return level(a.skills.get(name, 0))


def practise(a, name: str, tick: int, amount: float = 1.0) -> str:
    """Add experience; returns a note when the agent reaches a new level."""
    before = skill(a, name)
    a.skills[name] = a.skills.get(name, 0) + amount * (2 if a.stage(tick) == "child" else 1)
    after = skill(a, name)
    return f"{name} skill is now {after}" if after > before else ""


def nudge(a, need: str, amount: float):
    a.needs[need] = max(0.0, min(100.0, a.needs.get(need, START[need]) + amount))


def hourly(a, tick: int, *, asleep: bool, sheltered: bool, warm: bool, winter: bool, fire_near: bool,
           friends_near: int, in_group: bool, hungry: bool, has_food: bool, home_exists: bool):
    """Drift every need by one hour of life."""
    t = a.traits
    if asleep:
        nudge(a, "rest", -12)
    else:
        nudge(a, "rest", 3.2)
        nudge(a, "belonging", (1.4 if not in_group else 0.8) * (0.5 + t.social) - 4 * min(friends_near, 3))
        nudge(a, "status", 0.5 * (0.4 + t.driven))
        nudge(a, "curiosity", 0.9 * (0.4 + t.curious))
    target = (15 + (30 if hungry else 0) + (15 if not has_food else 0) + (10 if not home_exists else 0)
              + (30 if winter and asleep and not (sheltered or fire_near or warm) else 0) - (15 if sheltered else 0))
    a.needs["safety"] = a.needs.get("safety", 20) + (max(0, min(100, target)) - a.needs.get("safety", 20)) * 0.2
    if a.grief > 0:
        a.grief -= 1
    if a.anger > 0:
        a.anger -= 1


# what an action does to needs (it happened, so it satisfies or frustrates something)
SATISFY = {"say": {"belonging": -10}, "give": {"belonging": -8, "status": -4}, "court": {"belonging": -15},
           "care": {"belonging": -8}, "tell": {"belonging": -10, "status": -5}, "teach": {"status": -12, "belonging": -6},
           "rest": {"rest": -25}, "attempt": {"curiosity": -25}, "invent": {"curiosity": -20, "status": -10},
           "found": {"status": -20, "belonging": -10}, "join": {"belonging": -20}, "name": {"status": -8, "curiosity": -8},
           "hunt": {"curiosity": -6}, "explore": {"curiosity": -18}, "finished": {"status": -30}, "discovery": {"status": -35},
           "gather": {"rest": 2}, "work": {"rest": 3}}


def after_action(a, act: str):
    for need, v in SATISFY.get(act, {}).items():
        nudge(a, need, v)


WEIGHT = {"rest": lambda t: 1.0, "safety": lambda t: 1.1, "belonging": lambda t: 0.6 + t.social,
          "status": lambda t: 0.6 + t.driven, "curiosity": lambda t: 0.6 + t.curious}
MOOD_OF = {"rest": "exhausted", "belonging": "lonely", "safety": "anxious", "status": "restless to prove yourself",
           "curiosity": "bored and restless"}


def loudest(a) -> tuple[str, float]:
    return max(((n, v * WEIGHT[n](a.traits)) for n, v in a.needs.items() if n in WEIGHT), key=lambda p: p[1])


def mood(a, tick: int) -> str:
    """One word or phrase for how the agent feels right now."""
    if a.stage(tick) == "baby":
        return "hungry" if a.hunger >= 40 else "content"
    if a.hunger >= 80:
        return "starving"
    if a.grief > 0:
        return "grieving"
    if a.anger > 0:
        return "angry"
    need, score = loudest(a)
    if score >= 55:
        return MOOD_OF[need]
    if all(v < 35 for v in a.needs.values()):
        return "happy"
    return "content"


MOOD_ICON = {"starving": "😫", "grieving": "😢", "angry": "😠", "exhausted": "🥱", "lonely": "🥺", "anxious": "😟",
             "restless to prove yourself": "😤", "bored and restless": "🤔", "happy": "😊", "content": "🙂", "hungry": "😫"}


def describe(a, tick: int) -> str:
    """The feelings line of the prompt."""
    m = mood(a, tick)
    need, _ = loudest(a)
    low = [n for n, v in a.needs.items() if v >= 60]
    out = f"You feel {m}."
    if m not in ("happy", "content"):
        out += f" What you want most: {NEEDS[need]}."
    if low and set(low) - {need}:
        out += " Also lacking: " + ", ".join(NEEDS[n] for n in low if n != need) + "."
    if a.needs.get("rest", 0) >= 70:
        out += " You're so tired your work suffers - rest (or sleep tonight)."
    return out


def skills_text(a) -> str:
    have = sorted(((skill(a, k), k) for k in SKILLS if skill(a, k) > 0), reverse=True)
    return ", ".join(f"{k} {lv}" for lv, k in have) or "none yet (skills grow by doing)"


def tired_factor(a) -> float:
    return 0.5 if a.needs.get("rest", 0) >= 70 else 1.0


def hour_of(tick: int) -> int:
    return clock.when(tick)["hour"]
