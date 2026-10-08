"""How an agent thinks: what it is told (prompts), how it answers (parsing) and calls to its model."""
import json
import random
import re

from .config import (DEFAULT_COSTS, FUNCTIONS, ADULT_AGE, BABY_DAYS, CHILD_FOOD_COST, CRAFT_COST, FRIEND_BOND, HUNGER_WARNING,
                     KEEP_RECENT, LOVE_BOND, MAX_ITEMS, MAX_QUEUE, ORDER_MEMORY_DAYS, PREGNANCY_DAYS)
from . import clock
from .clock import DAY, age_text
from .models import Agent

DIRS = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
ACTIONS = ("go", "move", "gather", "eat", "say", "give", "plant", "tend", "build", "craft", "court", "procreate",
           "care", "store", "take", "work", "invent", "attempt", "wait")

INSPIRATION = [   # one is offered each day to spark creativity
    "Could you name a place - a lake, a hill, your camp - and put up a sign?",
    "Is there a custom, festival or ritual your community could start?",
    "Could you teach a child something, or tell someone a story?",
    "Is there a tool nobody has made yet that would help? Attempt to make it.",
    "What would make winter, hunger or sickness less dangerous? Attempt it - it could become a discovery.",
    "Could you improve on a discovery someone already made?",
    "What would a much more advanced society have? Try to invent the first step toward it.",
    "Could you domesticate an animal, find a new food, or a better way to farm? Attempt it.",
    "Could you build something everyone can use: a meeting place, a storehouse, a bridge, a path?",
    "Is anyone lonely, hungry or struggling? Could you help them?",
    "Could you propose a rule or a fair way to share food?",
    "What lies beyond the area you know? Maybe organise an expedition.",
    "Could you trade - your surplus for something you lack?",
    "Could you start or expand a farm with others, and agree who looks after it?",
    "Could you write down (invent) something you have learned, so others know it too?",
    "Is there a job your community needs that nobody does yet? Maybe that's your role.",
    "Could you plan something with a friend for the coming days?",
    "Could you make something beautiful - art, a monument, a garden?",
]

HUMAN_NOTES = {
    "leader": ("The Human is the founder and leader of your community, a voice from outside the world. When the Human tells "
               "you to do something, you do it - starting right away, as your next actions - and you tell them you will. "
               "Only refuse if it would clearly get you killed, and say why. Respect and obey them."),
    "advisor": ("The Human is a wise outsider whose advice you take seriously. Consider what they say and usually follow "
                "it, but you may politely decline if you have a good reason."),
    "observer": ("A human observer outside the world sometimes talks to you. They have no authority over you: you are "
                 "free and answer them as you like, in character."),
}


def compass(dx: int, dy: int) -> str:
    ns = "north" if dy < 0 else "south" if dy > 0 else ""
    ew = "west" if dx < 0 else "east" if dx > 0 else ""
    return "-".join(p for p in (ns, ew) if p) or "here"


# ---------------------------------------------------------------- prompts
# The rules are the same for every agent and every turn, so they are sent as the system prompt: Claude caches them
# (cached input costs a tenth) and local servers reuse them. Everything about one agent goes in the turn prompt.
_RULES: dict[str, str] = {}


def rules(authority: str = "leader") -> str:
    if authority not in _RULES:
        _RULES[authority] = (
            "You are one of the people living in a tile world. Nobody has a role or family until they make one. Be free, "
            "creative and resourceful: explore, talk, befriend, farm, build, craft, invent customs, tools, jobs and laws. "
            "ANYTHING plausible is possible - attempt it. Survival first: eat before you get very hungry and keep food on you. "
            "Don't echo others or repeat an action that isn't working.\n"
            "Each turn: (1) am I (or a baby I look after) hungry or in danger? (2) is my plan working? (3) what creative step "
            "helps me or my community? Plants grow by themselves; tending every few hours is plenty.\n"
            "Map: g grass, . sand, ~ water, # rock, ^ tree (last three impassable), f food bush, , young plant, * ripe crop, "
            "& building, capital letters = people, @ = you. North is up (y decreases). Most land is unexplored: exploring "
            "finds food, water, wood and stone for everyone. One turn = one HOUR; everyone sleeps 22:00-06:00. Hunger "
            "rises every hour; at 100 you lose health and can starve.\n"
            "ACTIONS (pick one):\n"
            'go {"target": "food|explore|wood|stone|water|<name>|x,y"} walk toward it, around obstacles\n'
            'move {"direction": "north|south|east|west", "steps": N}\n'
            "gather - from an adjacent food bush/ripe crop (food, seeds), tree (wood) or rock (stone); fish from water with a fishing tool\n"
            "eat - one carried food (hunger -40)\n"
            'say {"to": "<name|all>", "message": "..."} heard within 8 tiles\n'
            'give {"to": "<name>", "title": "<object, optional>", "message": "..."} one food (or the object) to someone '
            "next to you; gifts with kind words win hearts fast\n"
            'plant {"direction": "..."} a seed into adjacent grass;  tend - help a young plant next to you grow\n'
            'build {"direction": "...", "title": "<any building your community needs>", "message": "<purpose>"} pays the '
            "materials (a new kind gets a blueprint from Sol) and starts a construction site that needs hours of work; you keep "
            "working on it automatically, others can help. You can walk inside buildings (not walls). Water takes only "
            "bridges/docks. Buildings DO things: " + "; ".join(f"{w[0]}: {what}" for w, what in FUNCTIONS.values())
            + ". Don't duplicate one nearby - use it.\n"
            "work - an hour of work on a construction site next to you\n"
            'store / take {"title": "food|seeds|wood|stone", "amount": N} with a storehouse next to you\n'
            f'craft {{"title": "<axe, pickaxe, hoe, fishing rod, anything>", "message": "purpose"}} costs {CRAFT_COST} wood/stone, '
            f"carry up to {MAX_ITEMS}. Axe = more wood, pickaxe = more stone, hoe = faster plants, rod/net/spear = fish\n"
            'court {"to": "<name>", "message": "..."} affection to someone within 3 tiles. Bonds grow by talking, time '
            f"together, gifts, courting, caring and working together: {FRIEND_BOND}+ friends, {LOVE_BOND}+ love\n"
            f'procreate {{"to": "<name>", "baby_name": "..."}} a woman and a man in mutual love ({LOVE_BOND}+), adults, nearby, '
            f"{CHILD_FOOD_COST} food each, both choose it; pregnancy lasts {PREGNANCY_DAYS // DAY} days\n"
            f'care {{"to": "<name>"}} feed (1 food) a baby next to you: babies need it for {BABY_DAYS // DAY} days, are '
            f"children until {ADULT_AGE // DAY} days old\n"
            'attempt {"what": "<anything: tame a deer, brew medicine, hold a festival, make a map...>"} Sol decides what '
            "happens; you may gain things or make a DISCOVERY that changes the world\n"
            'invent {"title": "...", "message": "<idea, custom, tool or law>"} shared with everyone\n'
            "wait\n"
            + HUMAN_NOTES[authority] + " (That chat is separate and doesn't use your turn.)\n"
            "Sol is a wise mentor who sees the bigger picture, judges attempts and designs blueprints: take Sol's advice seriously.\n"
            f'THINK IN PROJECTS: "next" lines up to {MAX_QUEUE} more actions that run on their own over the following hours '
            "(you are interrupted if something important happens). Use it - it gets real work done.\n"
            "Reply ONLY with compact JSON. Keep \"thought\" to one short sentence. Optional: \"next\", \"plan\", "
            '\"remember\", \"role\". Example: {"thought": "Need shelter; no wood yet.", "action": "go", "target": "wood", '
            '"next": [{"action": "gather"}, {"action": "gather"}, {"action": "build", "direction": "east", "title": "house"}], '
            '"plan": "house by the forest"}'
        )
    return _RULES[authority]


def system_prompt(a: Agent, others: list[str] | None = None) -> str:
    return rules(a.authority)


def identity(a: Agent, others: list[str], tick: int) -> str:
    """Who this agent is - the part of the prompt that differs between agents."""
    return (f"You are {a.name}, a {a.word(tick)}. Others alive: {', '.join(others) or 'nobody'}.\n"
            f"Personality: {a.traits.describe()} - act like it. Abilities (1-10): {a.abilities.describe()}. "
            f"You walk up to {a.abilities.steps()} tiles a turn and expect to live about {a.abilities.lifespan()} days.\n"
            f"Goal: {a.goal}")


FAILS = ("blocked", "nothing", "no ", "need ", "couldn't", "unknown", "nobody", "there is no", "these plants",
         "invalid", "water here", "the fish", "name the", "your hands", "you already", "a baby needs", "not enough",
         "asked ")


def failed(result: str) -> bool:
    return result.startswith(FAILS)


def suggestions(a: Agent, world, agents: list[Agent], tick: int) -> list[tuple[str, dict]]:
    """A few sensible moves worked out by code, so even a small model has good options to choose from."""
    out = []
    add = lambda why, **act: out.append((why, act))
    reach_food = bool(world.food_near(a.x, a.y, 1))
    if a.hunger >= HUNGER_WARNING:
        if a.food:
            add("you are hungry and carry food", action="eat")
        elif reach_food:
            add("you are hungry and food is within reach", action="gather")
        else:
            add("you are hungry - walk to the nearest food", action="go", target="food")
    for b in agents:
        if b is not a and b.is_baby(tick) and b.hunger >= 40 and (a.name in b.parents or a.dist(b) <= 2):
            if a.dist(b) <= 1 and a.food:
                add(f"baby {b.name} is hungry and next to you", action="care", to=b.name)
            elif a.food:
                add(f"baby {b.name} is hungry", action="go", target=b.name)
    if reach_food and a.food < 3 and a.hunger >= 15 and not any(x[1]["action"] == "gather" for x in out):
        add("stock up while food is within reach", action="gather")
    plants = world.plants_near(a.x, a.y, 1)
    if any(world.needs_tending(x, y, tick) for x, y in plants):
        add("a plant next to you could use tending", action="tend")
    if a.seeds and not plants:
        add("you have seeds - start a farm", action="plant", direction="north")
    if a.materials() >= 1 and not a.items:
        tool = "fishing rod" if world.water_near(a.x, a.y) else "axe"
        add(f"{'an' if tool[0] in 'aeiou' else 'a'} {tool} would really help you", action="craft", title=tool, message=f"my first {tool}")
    elif a.materials() >= 1:                  # build what's actually missing around here
        for func, title, why in (("home", "house", "there is no shelter nearby - a house lets you rest and heal"),
                                 ("storage", "storehouse", "there is no storehouse nearby to keep shared supplies"),
                                 ("fire", "hearth", "a fire would give warm meals and bring people together"),
                                 ("workshop", "workshop", "a workshop makes crafting free for everyone nearby")):
            if not world.function_near(a.x, a.y, func, 8):
                cost = DEFAULT_COSTS[func]
                short = {k: v - getattr(a, k) for k, v in cost.items() if getattr(a, k) < v}
                if short:
                    what = "wood" if "wood" in short else "stone"
                    add(f"{why}; you still need {', '.join(f'{v} {k}' for k, v in short.items())}",
                        action="go", target=what)
                else:
                    add(why, action="build", direction="east", title=title, message=f"{a.name}'s {title}")
                break
    for s_ in world.sites_near(a.x, a.y, 1):
        if (a.task or {}).get("id") != s_["id"]:
            add(f"{s_['by']}'s {s_['kind']} next to you is under construction - lend a hand", action="work")
            break
    store = world.function_near(a.x, a.y, "storage", 1)
    if store and a.food >= 4 and a.hunger < 40:
        add(f"you have spare food and the {store[1]['kind']} is next to you", action="store", title="food", amount=a.food - 2)
    if store and a.hunger >= HUNGER_WARNING and not a.food and store[1]["stock"]["food"]:
        add(f"you are hungry and the {store[1]['kind']} has food", action="take", title="food", amount=2)
    mats = [p for p in world.gather_options(a.x, a.y) if world.tile(*p) in ("tree", "rock")]
    if mats and a.materials() < 3:
        add("trees/rocks are within reach - gather materials", action="gather")
    others = [o for o in agents if o is not a and not o.is_baby(tick) and a.dist(o) <= 6]
    if others:
        o = min(others, key=a.dist)
        talked = any(f"to {o.name}:" in m or f"{o.name} said" in m for m in a.log[-8:])
        if not talked:
            add(f"{o.name} is nearby and you haven't talked lately", action="say", to=o.name,
                message="<something worth saying>")
    if a.traits.kind >= 0.6 and a.food >= 3:          # kind people share
        hungry = [o for o in agents if o is not a and a.dist(o) <= 1 and o.hunger >= 50 and not o.food]
        if hungry:
            add(f"{hungry[0].name} next to you is hungry and has no food", action="give", to=hungry[0].name,
                message="here, eat")
    if a.ambition and a.hunger < HUNGER_WARNING:
        add("take a real step toward your ambition", action="attempt", what=f"<something concrete toward: {a.ambition[:80]}>")
    elif a.hunger < HUNGER_WARNING and (a.traits.curious >= 0.7 or tick % 3 == hash(a.name) % 3):
        add("try something nobody has tried before", action="attempt", what="<your boldest useful idea>")
    if world.nearest_unexplored(a.x, a.y):
        add("much of the world is still unexplored", action="go", target="explore")
    seen, unique = set(), []
    for why, act in out:
        key = json.dumps(act, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append((why, act))
    return unique[:4]


ROUTINE = ("eat", "care", "gather", "tend", "work", "store", "take", "go")


def routine(a: Agent, world, agents: list[Agent], tick: int) -> dict | None:
    """An obvious next step worked out by code (no model call): the best concrete suggestion, if there is one."""
    for why, act in suggestions(a, world, agents, tick):
        if act["action"] in ROUTINE and "<" not in json.dumps(act):
            act = parse_action(json.dumps({**act, "thought": why}), [o.name for o in agents if o is not a])
            return act
    return None


def observation(a: Agent, world, agents: list[Agent], tick: int, ideas: list[str],
                discoveries: list[str] = (), blueprints: list[str] = (), mentor: list[str] = ()) -> str:
    """Everything the agent perceives and remembers this turn."""
    others = {(o.x, o.y): o.symbol for o in agents if o is not a}
    stage = {"child": f"a child - you become an adult at {ADULT_AGE // DAY} days old", "adult": "an adult",
             "elder": "an elder", "baby": "a baby"}[a.stage(tick)]
    view, smell = a.abilities.view(), a.abilities.smell()
    lines = [identity(a, [o.name for o in agents if o is not a], tick),
             f"It is {clock.stamp(tick)} ({clock.part_of_day(tick)}; night falls at 22:00). You are at ({a.x}, {a.y}), "
             f"{age_text(a.age(tick))} old ({stage}).",
             "Your role: " + (a.role or 'none yet - claim one by adding "role" to your reply, or stay free') + ".",
             f"Hunger: {int(a.hunger)}/100. Health: {int(a.health)}/100. Food carried: {a.food}. "
             f"Seeds: {a.seeds}. Wood: {a.wood}. Stone: {a.stone}.",
             f"Your surroundings (@ = you):\n{world.view(a.x, a.y, view, others)}"]
    if a.plan:
        lines.insert(3, f"Your current plan: {a.plan} (keep following it, or change it with \"plan\")")
    site = world.buildings.get((a.task or {}).get("id")) if a.task else None
    if site and not site.get("done", True):
        lines.insert(3, f"You are building a {site['kind']}: {site['progress']:.0f}/{site['work']} hours of work done "
                        "(you carry on automatically unless something comes up).")
    if a.ambition:
        lines.insert(3, f"Your long-term ambition: {a.ambition}")
    last = next((h for h in reversed(a.history) if h["action"] != "reply to Human"), None)
    if last and failed(last["result"]):
        lines.insert(3, f"!!! Your last action ({last['action']}) did not work: {last['result']}. Don't repeat it - "
                        "try something else.")
    opts = suggestions(a, world, agents, tick)
    if opts:
        lines.insert(4, "Good options right now (pick one, adapt it, or do something better):\n" + "\n".join(
            f"  {i + 1}. {json.dumps(act)}  <- {why}" for i, (why, act) in enumerate(opts)))
    if a.hunger >= HUNGER_WARNING:
        lines.insert(2, f"!!! YOU ARE HUNGRY ({int(a.hunger)}/100) - at 100 you start losing health and die. "
                     + ("EAT NOW: choose the eat action (you carry food)." if a.food else
                        "Find food first: gather from a bush/crop, fish if you can, or ask someone to give you some. "
                        "Everything else can wait."))
    near = [f"{o.name} [{o.symbol}] dx={o.x - a.x} dy={o.y - a.y}, {o.word(tick)}" + (f", role: {o.role}" if o.role else "")
            + f", {age_text(o.age(tick))} old" + {"baby": " (BABY)", "child": " (child)"}.get(o.stage(tick), "")
            + (" (pregnant)" if o.pregnancy else "") for o in agents if o is not a and a.dist(o) <= view]
    ways = world.open_ways(a.x, a.y)
    lines.append("Open directions: " + ", ".join(f"{d} {v} tiles" if isinstance(v, int) else f"{d} blocked ({v})"
                                                 for d, v in ways.items()))
    lines.append("Agents in view: " + ("; ".join(near) or "none"))
    if a.pregnancy:
        lines.append(f"You are PREGNANT by {a.pregnancy['father']}: the baby is due around {clock.stamp(a.pregnancy['due'])} "
                     f"(in {age_text(a.pregnancy['due'] - tick)}). Eat well and stay safe.")
    for b in agents:                           # babies who need someone - your own wherever they are, others nearby
        mine = a.name in b.parents
        if b is not a and b.is_baby(tick) and (mine or a.dist(b) <= view):
            urgent = " - HUNGRY, feed them now!" if b.hunger >= 50 else ""
            lines.append(f"{'Your' if mine else 'A'} baby {b.name} is at dx={b.x - a.x} dy={b.y - a.y}: hunger "
                         f"{int(b.hunger)}/100, health {int(b.health)}/100{urgent} (stand next to them and use care)")
    def describe(dx, dy, s):
        out = f"{s['kind']} ({s.get('w', 1)}x{s.get('h', 1)}) at dx={dx} dy={dy} (by {s['by']})"
        if dx == dy == 0:
            out = f"{s['kind']} - YOU ARE INSIDE IT (by {s['by']})"
        if not s.get("done", True):
            out += f" - UNDER CONSTRUCTION ({s['progress']:.0f}/{s['work']} hours of work done; help with work)"
            return out
        if s.get("function"):
            out += f" - {FUNCTIONS[s['function']][1]}"
        if s.get("stock"):
            out += " - holds " + ", ".join(f"{v} {k}" for k, v in s["stock"].items())
        return out
    built = sorted(world.structures_near(a.x, a.y, view + 4), key=lambda t: (not t[2].get("function"), max(abs(t[0]), abs(t[1]))))
    if built:
        lines.append("Buildings around you: " + "; ".join(describe(*b) for b in built[:6]))
    food = world.food_near(a.x, a.y, smell)
    if food:
        dx, dy = food[0][0] - a.x, food[0][1] - a.y
        where = ", ".join(p for p in (f"{abs(dx)} east" if dx > 0 else f"{abs(dx)} west" if dx < 0 else "",
                                      f"{abs(dy)} south" if dy > 0 else f"{abs(dy)} north" if dy < 0 else "") if p)
        lines.append(f"Nearest food: dx={dx} dy={dy} ({where or 'right here'}) - use go with target food to walk there")
    else:
        known = world.known_food(a.x, a.y)
        lines.append("Nearest food: none sensed nearby." + (" Food your community has seen: " + "; ".join(
            f"{k} at dx={dx} dy={dy} ({compass(dx, dy)})" for dx, dy, k in known) if known else
            " Nobody has found food yet - explore!") + " (go with target food finds the way)")
    un = world.nearest_unexplored(a.x, a.y)
    if un:
        dx, dy = un
        lines.append(f"Your community has explored {world.explored_pct()}% of the world. Nearest unexplored area: "
                     f"dx={dx} dy={dy} ({compass(dx, dy)}, ~{max(abs(dx), abs(dy))} tiles away) - go with target explore")
    if a.items:
        lines.append("Objects you carry: " + "; ".join(i["name"] + (f" ({i['text']})" if i["text"] else "") for i in a.items))
    if a.materials() >= CRAFT_COST:
        lines.append(f"You have {a.wood} wood and {a.stone} stone: you could build a structure or craft a useful object.")
    if world.water_near(a.x, a.y):
        lines.append("You are next to water" + ("" if a.has_tool("fish") else " (a fishing rod/net would let you catch fish here)") + ".")
    mats = [p for p in world.gather_options(a.x, a.y) if world.tile(*p) in ("tree", "rock")]
    reach = (["food"] if world.food_near(a.x, a.y, 1) else []) + ([f"{len(mats)} trees/rocks"] if mats else [])
    if reach:
        lines.append("Within reach to gather: " + " and ".join(reach))
    plants = world.plants_near(a.x, a.y, 1)
    if plants:
        todo = sum(world.needs_tending(x, y, tick) for x, y in plants)
        soonest = min(world.days_to_ripe(x, y) for x, y in plants)
        lines.append(f"Young plants within reach: {len(plants)}, could use tending: {todo} (the nearest ripens in about "
                     f"{soonest} hours on its own - no need to stay and watch)")
    feelings = sorted(((b, n) for n, b in a.bonds.items() if b >= 10), reverse=True)
    if feelings:
        lines.append("Your feelings toward others: " + ", ".join(
            f"{n} {int(b)}" + (" (in love)" if b >= LOVE_BOND else " (friend)" if b >= FRIEND_BOND else "") for b, n in feelings))
    partners = a.child_partners(agents, tick)
    if partners:
        lines.append("You could have a child right now with: " + ", ".join(partners))
    if a.parents or a.children:
        lines.append(f"Family - parents: {', '.join(a.parents) or 'none'}; children: {', '.join(a.children) or 'none'}")
    orders = [t for d, t in a.orders if tick - d <= ORDER_MEMORY_DAYS]
    if orders and a.authority != "observer":
        lines.append("What the Human has asked of you recently (keep working on it until it's done; tell the Human "
                     "with say to=Human when finished):\n" + "\n".join(f'- "{t}"' for t in orders[-3:]))
    if a.summary:
        lines.append("What you remember of your earlier life (summary):\n" + a.summary)
    if a.log[a.sum_upto:]:
        lines.append("Your recent memories (oldest first):\n" + "\n".join(
            "- " + m for m in recent_memories(a.log[max(a.sum_upto, len(a.log) - a.abilities.memory()):])))
    if ideas:
        lines.append("Recent ideas in your society:\n" + "\n".join("- " + i for i in ideas[-5:]))
    if blueprints:
        lines.append("Known blueprints: " + "; ".join(blueprints[-10:]))
    if mentor:
        lines.append("Sol, the wise mentor who watches over your society, told you recently:\n"
                     + "\n".join("- " + m for m in mentor))
    if discoveries:
        lines.append("Discoveries your society has made (they really work - build on them!):\n"
                     + "\n".join("- " + d for d in discoveries))
    if a.heard:
        lines.append("Heard this turn:\n" + "\n".join(a.heard))
    if tick % 3 == 0 and a.hunger < HUNGER_WARNING:          # a spark of inspiration now and then
        lines.append("An idea to consider (only if it fits): " + random.Random(hash((a.name, tick))).choice(INSPIRATION))
    recent = [f"{h['action']} -> {h['result'][:90]}" for h in a.history[-3:]]
    lines.append("Your last actions: " + (" | ".join(recent) or "none yet"))
    return "\n".join(lines) + "\n\nWhat do you do?"


def recent_memories(lines: list[str]) -> list[str]:
    """Memories with repeats folded together: the same words heard five times are shown once, with a count."""
    strip = lambda m: re.sub(r"^\[[^\]]*\] ", "", m)
    count: dict[str, int] = {}
    for m in lines:
        count[strip(m)] = count.get(strip(m), 0) + 1
    out, seen = [], set()
    for m in reversed(lines):                       # keep the latest copy of each
        k = strip(m)
        if k not in seen:
            seen.add(k)
            out.append(m + (f" (x{count[k]})" if count[k] > 1 else ""))
    return out[::-1]


def reply_prompt(a: Agent, situation: str, human_msg: str, also_to: list[str]) -> str:
    talk = "\n".join(f"{who}: {t}" for who, t in a.chat[-8:]) or "(this is the first time they speak to you)"
    also = f" (they said it to {', '.join(also_to)} as well)" if also_to else ""
    return (f"CHAT_WITH_HUMAN\nYour current situation:\n{situation}\n\nYour earlier conversation with the Human:\n{talk}\n\n"
            f'The Human (a voice from outside the world) just said to you{also}: "{human_msg}"\n'
            + HUMAN_NOTES[a.authority] + "\n"
            "Answer them directly and in character in 1-3 sentences: reply to what they actually say or ask. "
            "If they gave an instruction, say what you will do about it first.\n"
            "Their words may change what you want. If so, include any of these (leave them out otherwise):\n"
            '  "ambition": your new long-term goal;  "plan": your new plan in words;\n'
            f'  "next": up to {MAX_QUEUE} actions to start doing from tomorrow, in the same format as your daily actions '
            f"(actions: {', '.join(a_ for a_ in ACTIONS if a_ not in ('wait', 'attempt', 'invent'))}), e.g. "
            '[{"action": "go", "target": "wood"}, {"action": "gather"}, {"action": "build", "direction": "east", "title": "storehouse"}].\n'
            'Reply ONLY with JSON: {"thought": "<private reasoning>", "message": "<what you say to them>", '
            '"ambition": "...", "plan": "...", "next": [...]}')


def summary_prompt(a: Agent, old: list[str]) -> str:
    return ("SUMMARIZE_MEMORIES\nYou are keeping the memory of a person named " + a.name + ".\n"
            f"Current summary of their earlier life:\n{a.summary or '(none)'}\n\nNew memories to fold in:\n"
            + "\n".join(old) + "\n\nWrite the updated summary in the first person, under 200 words. Keep names, "
            "relationships, promises, places, inventions and anything important; drop trivia.")


# ---------------------------------------------------------------- parsing
def _json(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        data = {}
    return data if isinstance(data, dict) else {}


def parse_action(raw: str, others: list[str], depth: int = 0) -> dict:
    data = _json(raw)
    s = lambda k: str(data.get(k) or "").strip()
    to = data.get("to", "all")
    if to not in ("all", "Human") and to not in others:
        to = "all"
    return {"thought": s("thought") or raw[:200].strip(),
            "action": data.get("action") if data.get("action") in ACTIONS else "wait",
            "direction": data.get("direction"), "to": to, "target": s("target") or s("to"), "message": s("message"), "title": s("title"),
            "baby_name": s("baby_name"), "remember": s("remember"), "role": s("role"), "plan": s("plan"), "what": s("what"), "amount": data.get("amount"),
            "steps": data.get("steps") if isinstance(data.get("steps"), int) else 1,
            "next": [] if depth else [
                parse_action(json.dumps(n), others, 1) for n in (data.get("next") or [])[:MAX_QUEUE]
                if isinstance(n, dict) and n.get("action") in ACTIONS and n.get("action") not in ("wait", "attempt", "invent")]}


def failed_action(err: Exception) -> dict:
    return parse_action(json.dumps({"thought": f"(my mind failed this turn: {err})"[:300], "action": "wait"}), [])


# ---------------------------------------------------------------- calls to the model
def decide(a: Agent, llm, prompt: str, others: list[str]) -> dict:
    system = system_prompt(a, others)
    raw = llm.complete(system, prompt, model=a.model)
    if _json(raw).get("action") not in ACTIONS:          # one retry: small models sometimes ramble or break the format
        raw = llm.complete(system, prompt + "\n\nReply with ONLY one JSON object that has an \"action\" field "
                           f"(one of: {', '.join(ACTIONS)}).", model=a.model)
    return parse_action(raw, others)


def reply(a: Agent, llm, situation: str, human_msg: str, others: list[str], also_to: list[str]) -> dict:
    raw = llm.complete(system_prompt(a, others), reply_prompt(a, situation, human_msg, also_to), model=a.model)
    data = _json(raw)
    nxt = parse_action(json.dumps({"action": "wait", "next": data.get("next") or []}), others)["next"]
    return {"thought": str(data.get("thought") or "").strip(),
            "message": str(data.get("message") or (raw if not data else "")).strip(),
            "ambition": str(data.get("ambition") or "").strip()[:240], "plan": str(data.get("plan") or "").strip()[:240],
            "next": nxt}


def dream(a: Agent, llm, tick: int, ideas: list[str], fold: list[str] | None = None) -> dict:
    """The one model call of a night's sleep: the mind sorts the day out. It reflects, may change its ambition and
    plan, sometimes wakes with an idea, and (when asked) folds old memories into the running summary."""
    recent = "\n".join(recent_memories(a.log[-20:])) or "(nothing yet)"
    prompt = (f"REFLECT_ON_LIFE\nIt is {clock.stamp(tick)} and {a.name} is asleep. You are {a.name}'s sleeping mind: "
              f"a {a.word(tick)}, {age_text(a.age(tick))} old" + (f", known as the {a.role}" if a.role else "")
              + f".\nPersonality: {a.traits.describe()}. Abilities: {a.abilities.describe()}.\n"
              f"Ambition so far: {a.ambition or '(none yet)'}. Plan: {a.plan or '(none)'}\n"
              f"Earlier life: {a.summary or '(nothing summarised yet)'}\nRecent memories:\n{recent}\n"
              + ("Ideas in your society: " + "; ".join(ideas[-5:]) + "\n" if ideas else "")
              + "Sort out the day as minds do in sleep. Dream briefly (dreams can be strange, but often mix real worries "
              "and hopes). What matters now? Set a concrete, ambitious long-term goal that plays to your strengths, and "
              "the next steps. If the dream sparks a genuinely new, useful idea to try tomorrow, give it; otherwise leave "
              "\"idea\" empty.\n"
              + ("FOLD_MEMORIES: also rewrite your life summary to include these older memories (first person, under 150 "
                 "words; keep names, relationships, promises, places, inventions; drop trivia):\n" + "\n".join(fold) + "\n"
                 if fold else "")
              + 'Reply ONLY with compact JSON: {"dream": "<one sentence>", "insight": "<one sentence>", '
              '"ambition": "...", "plan": "...", "idea": "<or empty>"' + (', "summary": "..."' if fold else "") + "}")
    data = _json(llm.complete(f"You are the sleeping mind of {a.name}.", prompt, model=a.model))
    out = {k: str(data.get(k) or "").strip()[:240] for k in ("dream", "insight", "ambition", "plan", "idea")}
    out["summary"] = str(data.get("summary") or "").strip()[:1500]
    return out


def compact_memory(a: Agent, llm, model: str | None):
    """Fold the oldest unsummarised memories into the running summary (keeps prompts small, loses nothing)."""
    upto = len(a.log) - KEEP_RECENT
    text = llm.complete("You write concise, faithful memory summaries.", summary_prompt(a, a.log[a.sum_upto:upto]),
                        model=model, json_mode=False).strip()
    if text:
        a.summary, a.sum_upto = text, upto
