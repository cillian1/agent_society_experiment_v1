"""What each action does to the world. Every handler takes (sim, agent, act, day) and returns a short result
string that the agent sees next turn. Register new actions with @action("name") - and describe them in mind.py."""
import re

from .config import (FUNCTIONS, FIRE_MEAL_BONUS, BOND, FRIEND_BOND, BUILD_COST, CARE_RELIEF, CHILD_COOLDOWN, CHILD_FOOD_COST, CRAFT_COST, EAT_RELIEF, FISH_COOLDOWN,
                     GROW_NEEDED, HEARING_RADIUS, LOVE_BOND, MAX_ITEMS)
from . import clock, culture, needs, social
from .ecology import ANIMALS
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
    kinds = [k for k in ANIMALS if k in low] or (list(ANIMALS) if low in ("animal", "animals", "game", "hunt", "prey") else [])
    if kinds:
        prey = [b for b in sim.eco.animals.values() if b["kind"] in kinds and not b["owner"]
                and max(abs(b["x"] - a.x), abs(b["y"] - a.y)) <= 14]
        if not prey:
            return None, f"{low} (none seen nearby)"
        b = min(prey, key=lambda b: max(abs(b["x"] - a.x), abs(b["y"] - a.y)))
        return w.path((a.x, a.y), lambda x, y: max(abs(x - b["x"]), abs(y - b["y"])) <= 1), f"the {b['kind']}"
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
        return f'unknown destination "{target}" - use food, explore, wood, stone, water, animal, a name, or x,y'
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
    bare = False
    for fx, fy in w.gather_options(a.x, a.y):
        if w.tiles[fy][fx] == "food" and clock.season(tick) == "winter":
            bare = True                                      # wild bushes are bare in winter
            continue
        got = w.harvest(fx, fy, tick)
        if not got:
            continue
        bonus = ""
        if sim.rng.random() < needs.skill(a, "gathering") * 0.07:
            k = "food" if got["food"] else "wood" if got["wood"] else "stone" if got["stone"] else None
            if k:
                got[k] += 1
                bonus = " (skilled hands)"
        if got["food"] and "crop" in got["what"] and needs.skill(a, "farming") >= 5:
            got["food"] += 1
            bonus = " (expert farmer)"
        if needs.tired_factor(a) < 1 and sum(got[k] for k in ("food", "wood", "stone")) > 1 and sim.rng.random() < 0.5:
            k = max(("food", "wood", "stone"), key=lambda k: got[k])
            got[k] -= 1
            bonus += " (too tired to do it well)"
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
        n = 2 if sim.has("boats") else 1
        a.food += n
        sim.event(tick, a, "caught a fish", "food")
        return f"caught {'two fish' if n > 1 else 'a fish'} in the water: +{n} food"
    return "the bushes are bare in winter - hunt, fish, farm or take from a store" if bare else "nothing to gather within reach"


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
        if not culture.understands(o, a):              # a stranger of another people
            o.heard.append(f"{a.name} {culture.garble(msg)}")
            o.remember(tick, f"{a.name} {culture.garble(msg)}")
            culture.exchange(a, o)
            continue
        culture.exchange(a, o)
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
        res = (act["title"] or "food").lower().rstrip("s") if (act["title"] or "food").lower() != "seeds" else "seeds"
        res = {"seed": "seeds"}.get(res, res)
        if res not in GOODS:
            return f"you don't have a {act['title']} (objects: {', '.join(i['name'] for i in a.items) or 'none'})"
        n = max(1, min(int(act.get("amount") or 1) if str(act.get("amount") or "1").isdigit() else 1, getattr(a, res)))
        if getattr(a, res) <= 0:
            return f"no {res} to give"
        setattr(a, res, getattr(a, res) - n)
        setattr(o, res, getattr(o, res) + n)
        what = f"{n} {res}" if (n > 1 or res != "food") else "food"
        what += social.delivered(sim, a, o, res, n, tick)
        culture.exchange(a, o)
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
        hours = min(w.days_to_ripe(*p) for p in near)
        return (f"these plants were tended recently - they grow by themselves now (ripe in about {hours} hours). "
                "Go and do something else meanwhile")
    x, y = todo[0]
    growth, partners, _ = w.tend(x, y, a.name, tick)
    extra = (1 if a.has_tool("farm") else 0) + (0.5 if a.abilities.wits >= 7 else 0) + 0.15 * needs.skill(a, "farming")
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
            + ("" if ripe else f", ripe in about {w.days_to_ripe(x, y)} hours on its own - no need to stay")
            + (f" - teamwork with {', '.join(partners)} doubled the effect!" if partners else "")
            + (" It is now ripe!" if ripe else ""))


def footprints(a, w: int, h: int, direction):
    """Places for a w x h building right next to the agent, in the given direction (or any)."""
    for d in [direction] if direction in DIRS else list(DIRS):
        if d in ("east", "west"):
            x0s = [a.x + 1] if d == "east" else [a.x - w]
            y0s = sorted(range(a.y - h + 1, a.y + 1), key=lambda y: abs(y + (h - 1) / 2 - a.y))
        else:
            y0s = [a.y + 1] if d == "south" else [a.y - h]
            x0s = sorted(range(a.x - w + 1, a.x + 1), key=lambda x: abs(x + (w - 1) / 2 - a.x))
        for x0 in x0s:
            for y0 in y0s:
                yield d, x0, y0


def place_building(sim, a, kind: str, text: str, bp: dict, direction, tick: int):
    """Try every spot next to the agent; returns (building, '') or (None, why it failed)."""
    w, h = bp.get("size") or (1, 1)
    why = "no room next to you"
    for _, x0, y0 in footprints(a, w, h, direction):
        if any(sim.occupied(x, y) for x in range(x0, x0 + w) for y in range(y0, y0 + h)):
            why = "someone is standing where it would go"
            continue
        ok, why, b = sim.world.build_at(x0, y0, w, h, kind, text, a.name, tick, bp["function"])
        if ok:
            return b, ""
        if "already a" in why:
            return None, why
    return None, why


@action("build")
def build(sim, a, act, tick):
    title = (act["title"] or "structure")[:40]
    new = sim.blueprint_key(title) not in sim.blueprints
    bp = sim.blueprint(title, act.get("blueprint"), a.name, tick)
    if bp.get("function") == "fire" and not sim.has("fire"):
        return (f"nobody knows how to make fire yet, so a {title} would be useless. Try to discover fire "
                "(attempt: e.g. strike flint stones together over dry grass).")
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
    b, why = place_building(sim, a, title, act["message"][:160], bp, act["direction"], tick)
    if not b:
        w, h = bp.get("size") or (1, 1)
        return f"couldn't build the {title} ({w}x{h} tiles): {why}" + ("" if "already" in why else
                                                                        " - try another direction or a more open spot")
    for k, v in cost.items():
        setattr(a, k, getattr(a, k) - v)
    x, y, size = b["x"], b["y"], f"{b['w']}x{b['h']}"
    hours = work_hours(bp)
    b["work"], b["done"] = hours, False
    b["group"] = a.group                                  # buildings belong to the builder's group: its land
    a.task = {"type": "build", "id": b["id"]}
    sim.event(tick, a, f'started building a {title} ({size}) at ({x}, {y}) - {hours} hours of work{_quote(act["message"])}', "build")
    for o in sim.agents.values():
        if o is not a and max(abs(o.x - x), abs(o.y - y)) <= HEARING_RADIUS:
            o.heard.append(f'{a.name} started building a {title} at ({x}, {y}) - you could help with work.')
            o.remember(tick, f'{a.name} started building a "{title}" at ({x}, {y}).')
    a.remember(tick, f'I started building a "{title}" ({size}) at ({x}, {y}); it needs {hours} hours of work.')
    return (f"started building a {title} ({size} tiles) at ({x}, {y}): it needs {hours} hours of work. You'll keep "
            f"working on it automatically; others can help with work. {what}")


def work_hours(bp: dict) -> int:
    w, h = bp.get("size") or (1, 1)
    return int(max(2, min(16, sum(bp["cost"].values()) + w * h)))


@action("work")
def work(sim, a, act, tick):
    """Put an hour of work into a building under construction next to you (yours or someone else's)."""
    w = sim.world
    site = w.buildings.get((a.task or {}).get("id")) if a.task else None
    if not site or site.get("done", True) or w._gap(site, a.x, a.y) > 1:
        near = w.sites_near(a.x, a.y, 1)
        site = near[0] if near else None
    if not site:
        a.task = None
        return "nothing under construction next to you"
    helpers = [n for n, t in site["workers"].items() if n != a.name and tick - t <= 1]
    gain = ((1 + (0.5 if a.abilities.strength >= 7 else 0) + (0.5 if a.traits.driven >= 0.7 else 0)
             + (0.5 if helpers else 0) + 0.1 * needs.skill(a, "building"))
            * (1.5 if sim.has("masonry") else 1) * needs.tired_factor(a))
    site["progress"] = min(site["work"], site["progress"] + gain)
    site["workers"][a.name] = tick
    a.task = {"type": "build", "id": site["id"]}
    for n in helpers:
        if n in sim.agents:
            sim.bond(a, sim.agents[n], BOND["teamwork"])
            sim.bond(sim.agents[n], a, BOND["teamwork"])
    if site["progress"] >= site["work"]:
        w.finish(site)
        a.task = None
        crew = sorted(site["workers"])
        for n in crew:
            if n in sim.agents:
                sim.agents[n].remember(tick, f'We finished the {site["kind"]} at ({site["x"]}, {site["y"]})! ({", ".join(crew)})')
                if sim.agents[n].task and sim.agents[n].task.get("id") == site["id"]:
                    sim.agents[n].task = None
        sim.event(tick, a, f'finished the {site["kind"]} at ({site["x"]}, {site["y"]})' +
                  (f" with {', '.join(n for n in crew if n != a.name)}" if len(crew) > 1 else ""), "build")
        return f'finished the {site["kind"]}! It now works: {(FUNCTIONS.get(site["function"]) or (None, "decorative"))[1]}.'
    left = site["work"] - site["progress"]
    return (f'worked on the {site["kind"]}: {site["progress"]:.0f}/{site["work"]} hours done, {left:.0f} to go'
            + (f" (helped by {', '.join(helpers)})" if helpers else ""))


@action("craft")
def craft(sim, a, act, tick):
    title = act["title"][:30]
    if not title:
        return "name the object you want to craft (title)"
    cost = 0 if (sim.tech("building") >= 1 or sim.world.function_near(a.x, a.y, "workshop", 2)
                 or sim.rng.random() < needs.skill(a, "crafting") * 0.08) else CRAFT_COST
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
    sim.bond(o, a, BOND["court"] * (0.5 + o.traits.kind))
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
    return f"{mother.name} is now pregnant - the baby will be born in about 10 days"


# ================================================================ body
@action("rest")
def rest(sim, a, act, tick):
    home = sim.world.function_near(a.x, a.y, "home", 1)
    needs.nudge(a, "rest", -20 if home else -12)
    a.health = min(100.0, a.health + (2 if home else 1))
    return "rested" + (" in the shelter of the " + home[1]["kind"] if home else "") + f" (tiredness now {int(a.needs['rest'])})"


# ================================================================ animals
def _prey(sim, a, act, reach):
    kind = (act.get("target") or act.get("title") or "").lower()
    kind = next((k for k in ANIMALS if k in kind), None)
    near = sim.eco.near(a.x, a.y, reach, kind, wild=True)
    return near[0] if near else None


@action("hunt")
def hunt(sim, a, act, tick):
    armed = sim.has("weapons") or any(w in i["name"].lower() for i in a.items for w in ("spear", "bow", "sling", "javelin"))
    b = _prey(sim, a, act, 3 if armed else 1)
    if not b:
        seen = sim.eco.near(a.x, a.y, a.abilities.view(), wild=True)
        return ("no animal within reach" + (f" - the nearest is a {seen[0]['kind']} at ({seen[0]['x']}, {seen[0]['y']}): "
                                            "go there first (go target animal)" if seen else " - none in sight"))
    a.animation = [tick, "hunt", b["x"] - a.x, b["y"] - a.y]
    info = ANIMALS[b["kind"]]
    chance = 0.3 + 0.06 * needs.skill(a, "hunting") + (0.3 if armed else 0) + (0.05 if a.abilities.speed >= 7 else 0)
    if sim.rng.random() < chance * needs.tired_factor(a):
        sim.eco.remove(b["id"])
        n = info["food"] + needs.skill(a, "hunting") // 3
        a.food += n
        a.remember(tick, f"I hunted a {b['kind']} (+{n} food).")
        sim.event(tick, a, f"hunted a {b['kind']} (+{n} food)", "food")
        return f"hunted a {b['kind']}: +{n} food"
    hurt = info["fights"] and sim.rng.random() < 0.5
    if hurt:
        a.health = max(1.0, a.health - 15)
        a.remember(tick, f"A {b['kind']} fought back and hurt me.")
    for _ in range(2):
        sim.eco._step_animal(b, {a.name: a})                       # it runs off
    return f"the {b['kind']} got away" + (" - and it gored you (-15 health)" if hurt else "")


@action("tame")
def tame(sim, a, act, tick):
    b = _prey(sim, a, act, 1)
    if not b:
        return "no animal next to you to tame (go target goat / sheep / animal first)"
    if a.food <= 0:
        return "you need some food to coax it"
    a.food -= 1
    a.animation = [tick, "tame", b["x"] - a.x, b["y"] - a.y]
    info = ANIMALS[b["kind"]]
    chance = (0.5 if sim.has("husbandry") else 0.12) + 0.04 * needs.skill(a, "hunting")
    if not info["tame"]:
        chance /= 4
    if sim.rng.random() < chance:
        b["owner"] = a.name
        a.remember(tick, f"I tamed a {b['kind']}. It follows me now." + (" It will give me food every day." if info["milk"] else ""))
        sim.event(tick, a, f"tamed a {b['kind']}", "food")
        return f"tamed the {b['kind']}! It follows you" + (" and gives food every day" if info["milk"] else "")
    return f"the {b['kind']} ate your food but wouldn't be tamed" + ("" if info["tame"] else f" (a {b['kind']} is hard to tame)")


# ================================================================ teaching
@action("teach")
def teach(sim, a, act, tick):
    o = sim.agents.get(act["to"])
    if not o or o is a or a.dist(o) > 1:
        return "nobody next to you to teach"
    sk = next((k for k in needs.SKILLS if k in (act["title"] or act["message"] or "").lower()), None)
    sk = sk or max(needs.SKILLS, key=lambda k: needs.skill(a, k))
    mine, theirs = needs.skill(a, sk), needs.skill(o, sk)
    if mine < theirs + 2:
        return f"you can't teach {o.name} much about {sk} (you {mine}, them {theirs})"
    if not culture.understands(o, a):
        culture.exchange(a, o)
        return f"{o.name} doesn't understand your language well enough to learn yet"
    note = needs.practise(o, sk, tick, 4 + 1.5 * mine)
    sim.bond(o, a, BOND["teamwork"] * 2)
    o.remember(tick, f"{a.name} taught me {sk}." + (f" My {note}." if note else ""))
    a.remember(tick, f"I taught {o.name} {sk}.")
    if note:
        sim.event(tick, a, f"taught {o.name} {sk} ({o.name}'s {note})", "craft")
    return f"taught {o.name} {sk}" + (f" - their {note}" if note else "")


# ================================================================ trade & promises
def _other(sim, a, act, reach=8):
    o = sim.agents.get(act["to"])
    return o if o and o is not a and a.dist(o) <= reach else None


@action("offer")
def offer(sim, a, act, tick):
    o = _other(sim, a, act)
    if not o:
        return "nobody by that name within earshot to trade with"
    return social.offer(sim, a, o, social.bundle(act.get("give")), social.bundle(act.get("want")), act.get("within") or 0, tick)


@action("accept")
def accept(sim, a, act, tick):
    d = social.find_offer(sim, a, act.get("target") or act["to"], tick)
    return social.accept(sim, a, d, tick) if d else "there is no open offer to accept"


@action("decline")
def decline(sim, a, act, tick):
    d = social.find_offer(sim, a, act.get("target") or act["to"], tick)
    return social.decline(sim, a, d, tick) if d else "there is no open offer to decline"


@action("promise")
def promise(sim, a, act, tick):
    o = _other(sim, a, act)
    what = social.bundle(act.get("give") or act.get("title") or "")
    if not o or not what:
        return 'promise needs "to" (someone within earshot) and "give" (e.g. "3 wood")'
    p = social.promise(sim, a, o, what, act.get("within") or social.DEFAULT_DUE, tick)
    return f"promised {o.name} {social.text(what)} by {clock.short(p['due'])} - keep it, or they won't trust you"


@action("steal")
def steal(sim, a, act, tick):
    o = _other(sim, a, act, 1)
    if not o:
        return "nobody next to you to steal from"
    res = next((r for r in GOODS if r in (act["title"] or "food").lower()), "food")
    n = min(2, getattr(o, res))
    if not n:
        return f"{o.name} has no {res}"
    setattr(o, res, getattr(o, res) - n)
    setattr(a, res, getattr(a, res) + n)
    if not o.is_baby(tick):
        o.bonds[a.name] = max(-100.0, o.bonds.get(a.name, 0) - 30)
        o.anger = max(o.anger, 24)
        o.heard.append(f"{a.name} STOLE {n} {res} from you!")
        o.remember(tick, f"{a.name} stole {n} {res} from me.")
    a.remember(tick, f"I stole {n} {res} from {o.name}.")
    sim.event(tick, a, f"stole {n} {res} from {o.name}", "law")
    return f"stole {n} {res} from {o.name}"


# ================================================================ groups & laws
@action("found")
def found(sim, a, act, tick):
    return social.found(sim, a, act["title"], act["message"], tick)


@action("join")
def join(sim, a, act, tick):
    return social.join(sim, a, act["title"] or act.get("target") or "", tick)


@action("leave")
def leave(sim, a, act, tick):
    return social.leave(sim, a, tick)


@action("vote")
def vote(sim, a, act, tick):
    who = act["to"] if act["to"] not in ("all", "") else (act.get("target") or "")
    return social.vote(sim, a, who if who in sim.agents else a.name if who.lower() in ("me", "myself") else who, tick)


@action("propose")
def propose(sim, a, act, tick):
    return social.propose(sim, a, act["title"] or act["message"], tick)


@action("support")
def support(sim, a, act, tick):
    return social.support(sim, a, act.get("target") or act["title"], tick)


@action("punish")
def punish(sim, a, act, tick):
    o = _other(sim, a, act, 3)
    return social.punish(sim, a, o, act["message"], tick) if o else "nobody by that name close enough"


@action("forgive")
def forgive(sim, a, act, tick):
    o = _other(sim, a, act)
    return social.forgive(sim, a, o, tick) if o else "nobody by that name within earshot"


@action("exile")
def exile(sim, a, act, tick):
    o = sim.agents.get(act["to"])
    return social.exile(sim, a, o, tick) if o and o is not a else "exile whom?"


# ================================================================ culture
@action("name")
def name(sim, a, act, tick):
    return culture.name_place(sim, a, act["title"] or act["message"], tick)


@action("tell")
def tell(sim, a, act, tick):
    return culture.tell(sim, a, act["title"], act["message"], act["to"], tick)
