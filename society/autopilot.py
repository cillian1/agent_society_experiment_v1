"""Autopilot: what people do between their big-brain moments, worked out by plain code (no model call).

The model plans each agent's day once or twice a day (see Society.brain_due). Every other hour this code runs:
it follows the plan the brain made, and reacts to the little things on its own - eat when hungry, flee a fire,
feed the baby, rest when exhausted, get warm on a winter night, keep a promise, answer a fair offer, chat with a
friend, have a child with the one they love, tend the crops, store spare food - so nobody stands around waiting
for their brain. It always returns something to do."""
import json
import random

from . import clock, culture, needs, social
from .config import HUNGER_WARNING, LOVE_BOND
from .ecology import ANIMALS
from .mind import parse_action

SMALL_TALK = {
    "happy": ["What a good day!", "Things are going well for us.", "I'm glad we're together."],
    "content": ["How's your day going?", "Busy day, isn't it?", "Need a hand with anything?"],
    "lonely": ["I've missed talking to someone.", "Stay a while and talk with me?", "It's good to see you."],
    "anxious": ["Do we have enough food stored?", "I worry about what's coming.", "Is everyone safe?"],
    "angry": ["I'm not in a good mood today.", "Some people can't be trusted."],
    "grieving": ["I keep thinking about who we lost.", "It's hard to carry on some days."],
    "bored and restless": ["Let's find something new to do.", "Have you seen anything interesting out there?"],
    "restless to prove yourself": ["I want to build something that lasts.", "We could do so much more here."],
    "exhausted": ["I'm worn out.", "I need to rest soon."],
    "starving": ["Do you have any food to spare?", "I'm so hungry..."],
}
SEASON_TALK = {"winter": "It's freezing - stay near the fire.", "autumn": "Winter's coming, we should store food.",
               "spring": "Everything's growing again!", "summer": "Long days, good for work."}


def _act(a, others, thought, **act):
    return parse_action(json.dumps({**act, "thought": thought}), others)


def decide(sim, a) -> dict:
    """One hour of autopilot for an agent that isn't asking its brain this hour."""
    w, t, rng = sim.world, sim.tick, sim.rng
    others = [o.name for o in sim.agents.values() if o is not a]
    act = lambda why, **k: _act(a, others, why, **k)
    near = [o for o in sim.agents.values() if o is not a and not o.is_baby(t) and a.dist(o) <= 8]
    hour, season = clock.when(t)["hour"], clock.season(t)

    # ---- danger and the body first
    if any(max(abs(x - a.x), abs(y - a.y)) <= 2 for x, y in sim.eco.burning):
        fx, fy = next((x, y) for x, y in sim.eco.burning if max(abs(x - a.x), abs(y - a.y)) <= 2)
        away = "east" if a.x >= fx else "west"
        return act("Fire! Get away from the burning trees.", action="move", direction=away, steps=3)
    if a.hunger >= HUNGER_WARNING:
        if a.food:
            return act("I'm hungry - eating.", action="eat")
        store = w.function_near(a.x, a.y, "storage", 1)
        if store and store[1]["stock"].get("food"):
            return act("Hungry - taking food from the store.", action="take", title="food", amount=2)
        if w.food_near(a.x, a.y, 1) and not (season == "winter" and not any(w.tiles[y][x] == "crop" for x, y in w.food_near(a.x, a.y, 1))):
            return act("Hungry - food right here.", action="gather")
        prey = sim.eco.near(a.x, a.y, 1, wild=True)
        if prey:
            return act(f"Hungry - a {prey[0]['kind']} is right here.", action="hunt", target=prey[0]["kind"])
        return act("Hungry - off to find food.", action="go", target="food")
    for b in sim.agents.values():
        if a.name in b.parents and b.is_baby(t) and b.hunger >= 40 and a.food:
            if a.dist(b) <= 1:
                return act(f"{b.name} is hungry - feeding them.", action="care", to=b.name)
            return act(f"My baby {b.name} needs me.", action="go", target=b.name)
    if a.needs.get("rest", 0) >= 75:
        return act("I'm exhausted - resting.", action="rest")

    # ---- what was promised and offered
    offer = next(iter(social.open_offers(sim, a, t)), None)
    if offer:
        fair = (social.has(a, offer["want"]) and sum(offer["give"].values()) >= sum(offer["want"].values()) * 0.8
                and a.bonds.get(offer["from"], 0) > -10)
        return act("A fair trade." if fair else "Not a good deal for me.", action="accept" if fair else "decline",
                   target=str(offer["id"]))
    for p in social.owed(sim, a):
        o = sim.agents.get(p["to"])
        if p["from"] == a.name and o and p["due"] - t <= 8:
            res = next((r for r in p["left"] if getattr(a, r) > 0), None)
            if res:
                if a.dist(o) <= 1:
                    return act(f"I keep my word to {o.name}.", action="give", to=o.name, title=res,
                               amount=min(getattr(a, res), p["left"][res]))
                return act(f"I owe {o.name} - going to them.", action="go", target=o.name)

    # ---- the plan the brain made (queue) and ongoing building work are handled by the caller
    # ---- comfort: get warm on winter evenings
    if season == "winter" and hour >= 19 and not (w.function_near(a.x, a.y, "home", 1) or w.function_near(a.x, a.y, "fire", 3)):
        spot = w.function_near(a.x, a.y, "home", 25) or w.function_near(a.x, a.y, "fire", 25)
        if spot:
            b = spot[1]
            return act(f"A cold night is coming - heading to the {b['kind']}.", action="go", target=f"{b['x']},{b['y']}")

    # ---- love and family
    partners = a.child_partners(list(sim.agents.values()), t)
    if partners and rng.random() < 0.35:
        return act(f"I love {partners[0]} - let's have a child.", action="procreate", to=partners[0])
    lover = next((o for o in near if a.bonds.get(o.name, 0) >= LOVE_BOND and o.sex != a.sex and a.adult(t) and o.adult(t)), None)
    if lover and rng.random() < 0.15:
        if a.dist(lover) <= 2:
            return act(f"Spending time with {lover.name}.", action="court", to=lover.name, message="I'm happy you're here.")
        return act(f"Going to see {lover.name}.", action="go", target=lover.name)

    # ---- company when lonely
    if a.needs.get("belonging", 0) >= 55 and near and rng.random() < 0.6:
        o = min(near, key=lambda o: (-a.bonds.get(o.name, 0), a.dist(o)))
        if a.dist(o) <= 3:
            mood = needs.mood(a, t)
            line = rng.choice(SMALL_TALK.get(mood, SMALL_TALK["content"]) + [SEASON_TALK[season]])
            return act(f"Chatting with {o.name}.", action="say", to=o.name, message=line)
        return act(f"I'd like some company - going to {o.name}.", action="go", target=o.name)

    # ---- everyday work, shaped by role and skills
    plants = w.plants_near(a.x, a.y, 1)
    if any(w.needs_tending(x, y, t) for x, y in plants):
        return act("Tending the crops.", action="tend")
    if w.food_near(a.x, a.y, 1) and a.food < 6 and any(w.tiles[y][x] == "crop" or season != "winter" for x, y in w.food_near(a.x, a.y, 1)):
        return act("Gathering food while it's here.", action="gather")
    store = w.function_near(a.x, a.y, "storage", 1)
    if store and a.food >= 8:
        return act("Storing spare food for everyone.", action="store", title="food", amount=a.food - 4)
    if a.food >= 10:
        far_store = w.function_near(a.x, a.y, "storage", 15)
        if far_store:
            b = far_store[1]
            return act("Taking spare food to the store.", action="go", target=f"{b['x']},{b['y']}")
    for s in w.sites_near(a.x, a.y, 1):
        return act(f"Helping with the {s['kind']}.", action="work")
    role = (a.role or "").lower()
    if a.seeds and season != "winter" and ("farm" in role or needs.skill(a, "farming") >= 2 or rng.random() < 0.3):
        return act("Planting seeds.", action="plant", direction=rng.choice(["north", "south", "east", "west"]))
    if ("hunt" in role or needs.skill(a, "hunting") >= 2 or a.food < 3) and sim.eco.near(a.x, a.y, 6, wild=True):
        prey = sim.eco.near(a.x, a.y, 6, wild=True)[0]
        if max(abs(prey["x"] - a.x), abs(prey["y"] - a.y)) <= 1:
            return act(f"Hunting the {prey['kind']}.", action="hunt", target=prey["kind"])
        return act(f"Stalking a {prey['kind']}.", action="go", target=prey["kind"])
    if a.food < 3:
        return act("Stocking up on food.", action="go", target="food")
    built = _obvious_building(sim, a, season)                # build what's plainly missing nearby
    if built:
        return act(built[0], action="build", direction=rng.choice(["north", "south", "east", "west"]),
                   title=built[1], message=built[2])
    mats = [p for p in w.gather_options(a.x, a.y) if w.tile(*p) in ("tree", "rock")]
    if mats and (a.wood + a.stone < 6 or "build" in role or "wood" in role):
        return act("Collecting materials.", action="gather")
    if a.needs.get("curiosity", 0) >= 35 and w.nearest_unexplored(a.x, a.y) and rng.random() < 0.6:
        return act("Off to see what's out there.", action="go", target="explore")
    if a.wood + a.stone < 8 and rng.random() < 0.7:
        return act("We'll need materials.", action="go", target="wood" if a.wood <= a.stone else "stone")
    if a.food < 8 and season != "winter" and rng.random() < 0.6:
        return act("Gathering food for later.", action="go", target="food")
    if near and rng.random() < 0.4:
        o = rng.choice(near)
        if a.dist(o) <= 3 and culture.understands(o, a):
            return act(f"Chatting with {o.name}.", action="say", to=o.name,
                       message=rng.choice(SMALL_TALK.get(needs.mood(a, t), SMALL_TALK["content"])))
    return act("Wandering about.", action="move", direction=rng.choice(["north", "south", "east", "west"]),
               steps=rng.randint(1, a.abilities.steps()))


def _obvious_building(sim, a, season):
    """(why, title, purpose) for a building that's plainly missing around here and affordable, or None."""
    w = sim.world
    if any(not b.get("done", True) for b in w.buildings.values() if max(abs(b["x"] - a.x), abs(b["y"] - a.y)) <= 10):
        return None                                        # finish what's being built first
    wants = [("home", "hut", {"wood": 3}, "No shelter nearby - building a hut.", "a place to rest and keep warm"),
             ("storage", "storehouse", {"wood": 4, "stone": 1}, "Building a storehouse for our food.", "shared food and supplies"),
             ("fire", "hearth", {"wood": 2, "stone": 1}, "A hearth for warm meals and long nights.", "warmth and cooked meals")]
    for func, title, cost, why, purpose in wants:
        if func == "fire" and not sim.has("fire"):
            continue
        if func == "storage" and a.food < 6 and season != "autumn":
            continue
        if not w.function_near(a.x, a.y, func, 10) and all(getattr(a, k) >= v for k, v in cost.items()):
            return why, title, purpose
    return None
