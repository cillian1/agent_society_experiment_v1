"""What each action does to the world. Every handler takes (sim, agent, act, day) and returns a short result
string that the agent sees next turn. Register new actions with @action("name") - and describe them in mind.py."""
import re

from .config import (FIRE_MEAL_BONUS, BOND, FRIEND_BOND, BUILD_COST, CARE_RELIEF, CHILD_COOLDOWN, CHILD_FOOD_COST, CRAFT_COST, EAT_RELIEF, FISH_COOLDOWN,
                     GROW_NEEDED, HEARING_RADIUS, LOVE_BOND, MAX_ITEMS)
from .mind import DIRS

HANDLERS = {}


def action(name):
    def register(fn):
        HANDLERS[name] = fn
        return fn
    return register


def apply(sim, a, act: dict, tick: int) -> str:
    return HANDLERS.get(act["action"], wait)(sim, a, act, tick)


def _quote(msg: str) -> str:
    return f': "{msg}"' if msg else ""


@action("wait")
def wait(sim, a, act, tick):
    return "waited"


@action("move")
def move(sim, a, act, tick):
    dx, dy = DIRS.get(act["direction"], (0, 0))
    if (dx, dy) == (0, 0):
        return "invalid direction"
    w, moved, why = sim.world, 0, ""
    for _ in range(max(1, min(a.abilities.steps() + int(sim.tech("speed")), act.get("steps") or 1))):
        nx, ny = a.x + dx, a.y + dy
        if not w.in_bounds(nx, ny):
            why = "edge of the world"
        elif not w.walkable(nx, ny):
            why = w.tile(nx, ny)
        else:
            a.x, a.y = nx, ny
            moved += 1
            sim.explore(a, tick)
            continue
        break
    if not moved:
        return f"blocked: {why}"
    return (f"moved {act['direction']} {moved} tile{'s' if moved > 1 else ''} to ({a.x}, {a.y})"
            + (f" (then blocked by {why})" if why else ""))


def route_to(sim, a, target: str):
    """Resolve a go-target to (path, label). Targets: food, explore, wood, stone, water, a name, or "x,y"."""
    w, t = sim.world, (target or "").strip()
    low = t.lower()
    from .world import CROP, FOOD, ROCK, TREE, WATER
    near = lambda kinds: lambda x, y: any(w.in_bounds(x + dx, y + dy) and w.tiles[y + dy][x + dx] in kinds
                                          for dx in (-1, 0, 1) for dy in (-1, 0, 1))
    if low in ("food", "berries", "crop", "crops"):
        return w.path((a.x, a.y), near((FOOD, CROP))), "food"
    if low in ("explore", "unexplored", "new land"):
        return w.path((a.x, a.y), lambda x, y: (x, y) not in w.explored), "unexplored land"
    if low in ("wood", "tree", "trees", "forest"):
        return w.path((a.x, a.y), near((TREE,))), "trees"
    if low in ("stone", "rock", "rocks"):
        return w.path((a.x, a.y), near((ROCK,))), "rocks"
    if low in ("water", "lake", "fishing"):
        return w.path((a.x, a.y), near((WATER,))), "water"
    who = next((o for n, o in sim.agents.items() if n.lower() == low and o is not a), None)
    if who:
        return w.path((a.x, a.y), lambda x, y: max(abs(x - who.x), abs(y - who.y)) <= 1), who.name
    m = re.fullmatch(r"\(?\s*(-?\d+)\s*,\s*(-?\d+)\s*\)?", t)
    if m:
        gx, gy = int(m.group(1)), int(m.group(2))
        return w.path((a.x, a.y), lambda x, y: abs(x - gx) + abs(y - gy) <= 1), f"({gx}, {gy})"
    return None, None


@action("go")
def go(sim, a, act, tick):
    """Walk toward a target, finding the way around water, rocks and trees."""
    target = act.get("target") or act.get("title") or act.get("message")
    path, label = route_to(sim, a, target)
    if label is None:
        return f'unknown destination "{target}" - use food, explore, wood, stone, water, a name, or x,y'
    if path is None:
        return f"there is no way to reach {label} from here"
    if not path:
        return f"you are already at {label}"
    steps = path[:a.abilities.steps() + int(sim.tech("speed"))]
    for x, y in steps:
        a.x, a.y = x, y
        sim.explore(a, tick)
    left = len(path) - len(steps)
    return f"walked {len(steps)} tiles toward {label}, now at ({a.x}, {a.y})" + (f", {left} more to go" if left else ", arrived")


@action("gather")
def gather(sim, a, act, tick):
    w = sim.world
    for fx, fy in w.gather_options(a.x, a.y):
        got = w.harvest(fx, fy, tick)
        if not got:
            continue
        bonus = ""
        if got["food"]:
            got["food"] += int(sim.tech("harvest"))
        if got["wood"] or got["stone"]:
            got["wood" if got["wood"] else "stone"] += int(sim.tech("materials"))
        if (got["wood"] or got["stone"]) and sim.rng.random() < a.abilities.strength / 12:
            got["wood" if got["wood"] else "stone"] += 1
            bonus = " (strong arms)"
        if got["wood"] and a.has_tool("wood"):
            got["wood"] += 1
            bonus = " (axe bonus)"
        if got["stone"] and a.has_tool("stone"):
            got["stone"] += 1
            bonus = " (pickaxe bonus)"
        for k in ("food", "seeds", "wood", "stone"):
            setattr(a, k, getattr(a, k) + got[k])
        gains = ", ".join(f"+{got[k]} {k}" for k in ("food", "seeds", "wood", "stone") if got[k])
        msg = f"took from {got['what']} at ({fx}, {fy}): {gains}{bonus}"
        if got["food"]:
            sim.event(tick, a, msg, "food")
        return msg
    if w.water_near(a.x, a.y):
        if not a.has_tool("fish") and sim.tech("fishing") < 1:
            return "water here, but you need a fishing tool (craft a fishing rod or net) to catch fish"
        if tick - a.last_fish_tick < FISH_COOLDOWN:
            return "the fish aren't biting yet - try again in a moment"
        a.last_fish_tick = tick
        a.food += 1
        sim.event(tick, a, "caught a fish", "food")
        return "caught a fish: +1 food"
    return "nothing to gather within reach"


@action("eat")
def eat(sim, a, act, tick):
    if a.food <= 0:
        return "no food to eat"
    a.food -= 1
    fire = sim.world.function_near(a.x, a.y, "fire", 2)
    a.hunger = max(0.0, a.hunger - EAT_RELIEF - (FIRE_MEAL_BONUS if fire else 0))
    return "ate a warm cooked meal by the fire" if fire else "ate food"


GOODS = ("food", "seeds", "wood", "stone")


def _amount(act, have: int) -> int:
    try:
        n = int(act.get("amount") or 0)
    except (TypeError, ValueError):
        n = 0
    return max(1, min(have, n or have))


@action("store")
def store(sim, a, act, tick):
    """Put supplies into a storehouse next to you, for everyone."""
    hit = sim.world.function_near(a.x, a.y, "storage", 1)
    if not hit:
        return "no storehouse next to you (build one, or go to one)"
    what = (act.get("title") or act.get("what") or "food").lower().strip()
    what = next((g for g in GOODS if g in what), "food")
    if getattr(a, what) <= 0:
        return f"you have no {what} to store"
    n = _amount(act, getattr(a, what))
    setattr(a, what, getattr(a, what) - n)
    stock = hit[1]["stock"]
    stock[what] += n
    a.remember(tick, f"I stored {n} {what} in the {hit[1]['kind']} for everyone.")
    sim.event(tick, a, f"stored {n} {what} in the {hit[1]['kind']} (it now holds {stock['food']} food)", "gift")
    for o in sim.agents.values():
        if o is not a and a.dist(o) <= 6:
            sim.bond(o, a, 2)
    return f"stored {n} {what} in the {hit[1]['kind']}; it now holds " + ", ".join(f"{v} {k}" for k, v in stock.items())


@action("take")
def take(sim, a, act, tick):
    """Take supplies from a storehouse next to you."""
    hit = sim.world.function_near(a.x, a.y, "storage", 1)
    if not hit:
        return "no storehouse next to you"
    stock = hit[1]["stock"]
    what = (act.get("title") or act.get("what") or "food").lower().strip()
    what = next((g for g in GOODS if g in what), "food")
    if stock[what] <= 0:
        return f"the {hit[1]['kind']} has no {what} left"
    n = _amount(act, min(stock[what], 3))
    stock[what] -= n
    setattr(a, what, getattr(a, what) + n)
    a.remember(tick, f"I took {n} {what} from the {hit[1]['kind']}.")
    sim.event(tick, a, f"took {n} {what} from the {hit[1]['kind']}", "food")
    return f"took {n} {what} from the {hit[1]['kind']} ({stock[what]} {what} left there)"


@action("say")
def say(sim, a, act, tick):
    msg, to = act["message"], act["to"]
    if not msg:
        return "said nothing"
    targets = [o for o in sim.agents.values() if o is not a and a.dist(o) <= HEARING_RADIUS and to in ("all", o.name)]
    for o in targets:
        o.heard.append(f'{a.name} says{"" if to == "all" else " to you"}: "{msg}"')
        o.remember(tick, f'{a.name} said to {"everyone nearby" if to == "all" else "me"}: "{msg}"')
        if to == o.name:
            sim.bond(o, a, BOND["talked_to"])
            sim.bond(a, o, BOND["talked_back"])
        else:
            sim.bond(o, a, BOND["heard"])
    a.last_say, a.last_say_to, a.last_say_tick = msg, to, tick
    a.remember(tick, f'I said to {to}: "{msg}"')
    sim.talk.append({"tick": tick, "from": a.name, "to": to, "text": msg, "color": a.color})
    del sim.talk[:-200]
    return f'said "{msg}" to {to} ({len(targets)} heard)'


@action("give")
def give(sim, a, act, tick):
    o = sim.agents.get(act["to"])
    if not o or o is a or a.dist(o) > 1:
        return "no adjacent agent to give to"
    item = next((i for i in a.items if act["title"] and i["name"].lower() == act["title"].lower()), None)
    if item:
        if len(o.items) >= MAX_ITEMS:
            return f"{o.name}'s hands are full"
        a.items.remove(item)
        o.items.append(item)
        what = f"a {item['name']}"
    else:
        if a.food <= 0:
            return "no food to give"
        a.food -= 1
        o.food += 1
        what = "food"
    sim.bond(o, a, BOND["gift"])
    sim.bond(a, o, BOND["gave"])
    msg = act["message"]
    loving = a.bonds.get(o.name, 0) >= FRIEND_BOND or bool(msg)     # a gift for someone dear is a gesture of love
    if loving:
        sim.bond(o, a, BOND["love_gift"])
        a.heart_tick = o.heart_tick = tick
    words = f' with the words "{msg}"' if msg else ""
    o.heard.append(f"{a.name} gave you {what}{words}" + (" - a sign of their affection." if loving else "."))
    a.remember(tick, f"I gave {what} to {o.name}{words}" + (" to show I care." if loving else "."))
    o.remember(tick, f"{a.name} gave me {what}{words}" + (" - they really care about me." if loving else "."))
    sim.event(tick, a, f"gave {what} to {o.name}{words}" + (" ❤️" if loving else ""), "love" if loving else "gift")
    return f"gave {what} to {o.name}{words} (their feelings toward you: {int(o.bonds.get(a.name, 0))})"


@action("plant")
def plant(sim, a, act, tick):
    if a.seeds <= 0:
        return "no seeds to plant"
    for dx, dy in [DIRS[act["direction"]]] if act["direction"] in DIRS else DIRS.values():
        x, y = a.x + dx, a.y + dy
        if not sim.occupied(x, y) and sim.world.plant(x, y):
            a.seeds -= 1
            sim.event(tick, a, f"planted a seed at ({x}, {y})", "farm")
            a.remember(tick, f"I planted a seed at ({x}, {y}).")
            return f"planted a seed at ({x}, {y}); it needs tending to ripen"
    return "nowhere to plant: needs an empty, adjacent grass tile"


@action("tend")
def tend(sim, a, act, tick):
    w = sim.world
    near = w.plants_near(a.x, a.y, 1)
    if not near:
        return "no young plants within reach"
    todo = [p for p in near if w.needs_tending(*p, tick)]
    if not todo:
        days = min(w.days_to_ripe(*p) for p in near)
        return (f"these plants were tended recently - they grow by themselves now (ripe in about {days} days). "
                "Go and do something else meanwhile")
    x, y = todo[0]
    growth, partners, _ = w.tend(x, y, a.name, tick)
    extra = (1 if a.has_tool("farm") else 0) + (0.5 if a.abilities.intelligence >= 7 else 0)
    if extra and w.tiles[y][x] == "sprout":
        growth = w.boost(x, y, extra)
    ripe = growth >= GROW_NEEDED
    if partners:
        for n in partners:
            if n in sim.agents:
                sim.bond(a, sim.agents[n], BOND["teamwork"])
                sim.bond(sim.agents[n], a, BOND["teamwork"])
        sim.event(tick, a, f"and {', '.join(partners)} worked together on the plant at ({x}, {y})", "farm")
        a.remember(tick, f"I farmed together with {', '.join(partners)} at ({x}, {y}).")
    if ripe:
        sim.event(tick, a, f"grew a ripe crop at ({x}, {y})!", "farm")
    return (f"tended the plant at ({x}, {y}): growth {min(growth, GROW_NEEDED):.0f}/{GROW_NEEDED:.0f}"
            + ("" if ripe else f", ripe in about {w.days_to_ripe(x, y)} days on its own - no need to stay")
            + (f" - teamwork with {', '.join(partners)} doubled the effect!" if partners else "")
            + (" It is now ripe!" if ripe else ""))


@action("build")
def build(sim, a, act, tick):
    title = (act["title"] or "structure")[:40]
    new = sim.blueprint_key(title) not in sim.blueprints
    bp = sim.blueprint(title, act.get("blueprint"), a.name, tick)
    cost = {} if sim.tech("building") >= 1 else bp["cost"]
    need = ", ".join(f"{v} {k}" for k, v in cost.items())
    what = f"It will: {bp['description']}." if bp.get("description") else ""
    if new:
        sim.event(tick, a, f"drew up plans for a {title}: needs {need or 'nothing'}. {what}", "idea")
        a.remember(tick, f"I worked out how to build a {title}: it needs {need or 'nothing'}. {what}")
    short = {k: v - getattr(a, k) for k, v in cost.items() if getattr(a, k) < v}
    if short:
        return (f"to build a {title} you need {need} (you have {a.wood} wood, {a.stone} stone, {a.food} food) - "
                f"still missing {', '.join(f'{v} {k}' for k, v in short.items())}. {what} Gather it, then build.")
    why = "no adjacent tile given"
    for dx, dy in [DIRS[act["direction"]]] if act["direction"] in DIRS else DIRS.values():
        x, y = a.x + dx, a.y + dy
        if sim.occupied(x, y):
            why = "an agent is standing there"
            continue
        ok, why = sim.world.build(x, y, title, act["message"][:160], a.name, tick, bp["function"])
        if ok:
            for k, v in cost.items():
                setattr(a, k, getattr(a, k) - v)
            sim.event(tick, a, f'built a {title} at ({x}, {y}){_quote(act["message"])}', "build")
            for o in sim.agents.values():
                if o is not a and max(abs(o.x - x), abs(o.y - y)) <= HEARING_RADIUS:
                    o.remember(tick, f'{a.name} built a "{title}" at ({x}, {y}).')
            a.remember(tick, f'I built a "{title}" at ({x}, {y}).')
            return f"built a {title} at ({x}, {y}). {what}"
    return f"couldn't build: {why}"


@action("craft")
def craft(sim, a, act, tick):
    title = act["title"][:30]
    if not title:
        return "name the object you want to craft (title)"
    cost = 0 if sim.tech("building") >= 1 or sim.world.function_near(a.x, a.y, "workshop", 2) else CRAFT_COST
    if a.materials() < cost:
        return f"need {cost} wood/stone to craft (you have {a.wood} wood, {a.stone} stone)"
    if len(a.items) >= MAX_ITEMS:
        return f"your hands are full ({MAX_ITEMS} objects)"
    if any(i["name"].lower() == title.lower() for i in a.items):
        return f"you already have a {title}"
    a.spend_materials(cost)
    a.items.append({"name": title, "text": act["message"][:120], "by": a.name, "tick": tick})
    sim.event(tick, a, f"crafted a {title}{_quote(act['message'])}", "craft")
    a.remember(tick, f"I crafted a {title}" + (f" ({act['message']})." if act["message"] else "."))
    return f"crafted a {title}"


@action("court")
def court(sim, a, act, tick):
    o = sim.agents.get(act["to"])
    if not o or o is a or a.dist(o) > 3:
        return "nobody by that name close enough to court"
    sim.bond(o, a, BOND["court"] * (0.5 + o.traits.agreeableness))
    sim.bond(a, o, BOND["courted"])
    a.heart_tick = o.heart_tick = tick
    o.heard.append(f"{a.name} is courting you{_quote(act['message']) or '.'}")
    a.remember(tick, f"I courted {o.name}.")
    o.remember(tick, f"{a.name} courted me{_quote(act['message']) or '.'}")
    sim.event(tick, a, f"is courting {o.name}{_quote(act['message'])}", "love")
    return f"courted {o.name} (their feelings toward you: {int(o.bonds.get(a.name, 0))})"


@action("attempt")
def attempt(sim, a, act, tick):
    """Try anything at all - Sol decides what happens."""
    from .gm import apply_outcome
    if not (act.get("what") or act.get("message") or act.get("title")):
        return "say what you want to try (what)"
    if not act.get("gm"):
        return "nothing came of it this time"
    return apply_outcome(sim, a, act, act["gm"], tick)


@action("invent")
def invent(sim, a, act, tick):
    if not act["title"] and not act["message"]:
        return "had no idea to share"
    idea = {"tick": tick, "by": a.name, "color": a.color, "title": (act["title"] or "Untitled")[:60],
            "text": (act["message"] or act["title"])[:300]}
    sim.inventions.append(idea)
    sim.event(tick, a, f'invented "{idea["title"]}": {idea["text"]}', "idea")
    for o in sim.agents.values():
        o.remember(tick, f'I proposed the idea "{idea["title"]}": {idea["text"]}' if o is a
                   else f'{a.name} proposed the idea "{idea["title"]}": {idea["text"]}')
    if act.get("gm"):                    # the referee may turn the idea into a real discovery
        from .gm import apply_outcome
        return f'invented "{idea["title"]}". ' + apply_outcome(sim, a, act, act["gm"], tick)
    return f'invented "{idea["title"]}"'


@action("care")
def care(sim, a, act, tick):
    """Feed and look after a baby (or anyone) next to you."""
    o = sim.agents.get(act["to"])
    if not o or o is a or a.dist(o) > 1:
        babies = [b.name for b in sim.agents.values() if b.is_baby(tick) and a.dist(b) <= 1]
        if not babies:
            return "nobody next to you to care for"
        o = sim.agents[babies[0]]
    sim.bond(o, a, BOND["cared_for"])
    sim.bond(a, o, BOND["carer"])
    if a.food > 0 and o.hunger >= 20:
        a.food -= 1
        o.hunger = max(0.0, o.hunger - CARE_RELIEF)
        what = f"fed {o.name} (their hunger is now {int(o.hunger)})"
    else:
        o.health = min(100.0, o.health + 5)
        what = f"comforted {o.name}" + ("" if a.food else " (you had no food to feed them)")
    a.remember(tick, f"I {what}.")
    o.remember(tick, f"{a.name} took care of me.")
    sim.event(tick, a, what, "care")
    return what


@action("procreate")
def procreate(sim, a, act, tick):
    b = sim.agents.get(act["to"])
    if not b or b is a:
        return "no such partner"
    if a.sex == b.sex:
        return "a baby needs a woman and a man"
    if len(sim.agents) + sim.pending_births() >= sim.max_agents:
        return "the world is at its population limit"
    if a.dist(b) > 2:
        return f"{b.name} is too far away"
    if a.related(b):
        return f"{b.name} is close family"
    mother = a if a.sex == "female" else b
    if mother.pregnancy:
        return f"{mother.name} is already pregnant"
    for p in (a, b):
        if not p.adult(tick):
            return f"{p.name} is still a child"
        if p.food < CHILD_FOOD_COST:
            return f"{p.name} needs {CHILD_FOOD_COST} food to raise a child"
        if p.hunger >= 85:
            return f"{p.name} is too hungry"
        if tick - p.last_child_tick < CHILD_COOLDOWN:
            return f"{p.name} had a child too recently"
    if a.bonds.get(b.name, 0) < LOVE_BOND or b.bonds.get(a.name, 0) < LOVE_BOND:
        return (f"not enough mutual love (need {LOVE_BOND} each; yours {int(a.bonds.get(b.name, 0))}, "
                f"theirs {int(b.bonds.get(a.name, 0))})")
    if not (b.pending and b.pending[0] == a.name and tick - b.pending[1] <= 3):
        a.pending = [b.name, tick]
        b.heard.append(f"{a.name} wants to have a child with you. Choose procreate with to={a.name} to agree.")
        a.heart_tick = tick
        return f"asked {b.name} to have a child; waiting for their consent"
    for p in (a, b):
        p.food -= CHILD_FOOD_COST
        p.last_child_tick = tick
        p.pending = None
    name = re.sub(r"[^A-Za-z]", "", act["baby_name"])[:12].capitalize()
    sim.conceive(mother, a if mother is b else b, name, tick)
    return f"{mother.name} is now pregnant - the baby will be born in 10 days"
