"""How an agent thinks: what it is told (prompts), how it answers (parsing) and calls to its model."""
import json
import random
import re

from .config import (FUNCTIONS, ADULT_AGE, BABY_DAYS, BUILD_COST, CHILD_FOOD_COST, CRAFT_COST, FRIEND_BOND, HUNGER_WARNING,
                     KEEP_RECENT, LOVE_BOND, MAX_ITEMS, MAX_QUEUE, ORDER_MEMORY_DAYS, PREGNANCY_DAYS)
from .models import Agent

DIRS = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
ACTIONS = ("go", "move", "gather", "eat", "say", "give", "plant", "tend", "build", "craft", "court", "procreate",
           "care", "store", "take", "invent", "attempt", "wait")

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
def system_prompt(a: Agent, others: list[str]) -> str:
    return (
        f"You are {a.name}, a {a.word()}, one of {len(others) + 1} agents living in a 2D tile world "
        f"(the others: {', '.join(others) or 'nobody yet'}). Nobody has a job or a role until they invent one; "
        "nobody is anybody's family until children are born. You are free to do what you want: explore, "
        "talk, make friends (or enemies), plan together, farm, build, invent customs, tools, jobs and laws. "
        "Be creative and resourceful: try new things, combine ideas, invent, build, organise, specialise - "
        "a thriving society needs more than gathering food. In this world ANYTHING is possible: if you can imagine it, "
        "attempt it. Build on the discoveries others have made. "
        "Talking is valuable: answer people who speak to you, share what you know, ask questions, make deals. "
        "You remember everything that has happened to you. Survival comes first: eat before you get very hungry, "
        "and keep some food on you. Don't repeat or echo what others just said, and don't repeat your own last action "
        "if it isn't working - try something new, specific and concrete.\n"
        "Before you choose, think briefly: (1) Am I - or a baby I'm responsible for - hungry or in danger? Deal with "
        "that first. (2) What is my plan, and is it working? (3) What creative step would make life better for me "
        "or my community? Plants grow by themselves: tending once every few days is plenty, so don't hover over them.\n"
        f"Goal: {a.goal}\nPersonality: {a.traits.describe()}\n"
        f"Abilities (1-10): {a.abilities.describe()}. Use your strengths and let others cover your weaknesses.\n\n"
        "World: g grass, . sand, ~ water (impassable), # rock (impassable), ^ tree (impassable), f wild food bush "
        "(slow to regrow), , young plant, * ripe crop, & a structure someone built. North is up (y decreases), "
        "east is right. Uppercase letters are agents (you are @). "
        "Most of the world is unexplored: you only see a small area around you, and exploring finds new food, water, "
        "forests and rocks that your whole community can use. Be curious. Building and crafting make life better. "
        "Hunger rises every day; at 100 you take damage and can starve. Eating food lowers hunger. "
        f"You can expect to live about {a.abilities.lifespan()} days; one turn is one day.\n"
        "Each turn pick ONE action:\n"
        f'  go      - {{"target": "food|explore|wood|stone|water|<name>|x,y"}} walk up to {a.abilities.steps()} tiles toward it, '
        "finding the way around water and obstacles (the easiest way to travel)\n"
        f'  move    - {{"direction": "north|south|east|west", "steps": 1-{a.abilities.steps()}}} walk straight (stops at obstacles)\n'
        "  gather  - take from an adjacent/own-tile food bush or ripe crop (food, sometimes seeds), tree (wood) or rock "
        "(stone); next to water with a fishing tool you catch fish (food)\n"
        "  eat     - eat one carried food (hunger -40)\n"
        '  say     - {"to": "<name or all>", "message": "..."} heard within 8 tiles; talk to people!\n'
        '  give    - {"to": "<name>", "title": "<object, optional>", "message": "<optional words>"} hand one food (or that '
        "object) to an adjacent agent. A gift - especially with a few kind words - is a lovely way to show friendship "
        "or love and wins hearts fast\n"
        '  plant   - {"direction": "..."} put a carried seed into an adjacent grass tile\n'
        "  tend    - speed up a young plant within reach (helps once every few days; plants also grow on their own)\n"
        f'  build   - {{"direction": "...", "title": "<house, wall, bridge, sign, anything>", "message": "<description or sign text>"}} '
        f"costs {BUILD_COST} wood/stone; you can walk into or over what you build, except walls and fences. Water only takes bridges/docks. "
        "Buildings DO things: " + "; ".join(f"{words[0]}: {what}" for words, what in FUNCTIONS.values())
        + ". Don't build what already exists nearby - use it, or build something new.\n"
        '  store   - {"title": "food|seeds|wood|stone", "amount": N} put supplies into a storehouse next to you, for everyone\n'
        '  take    - {"title": "food|seeds|wood|stone", "amount": N} take supplies from a storehouse next to you\n'
        f'  craft   - {{"title": "<axe, pickaxe, hoe, fishing rod, basket, anything>", "message": "what it is for"}} costs '
        f"{CRAFT_COST} wood/stone; you carry it (max {MAX_ITEMS}). Objects matter: an axe/hatchet gets extra wood, a "
        "pickaxe/hammer extra stone, a hoe/shovel/rake speeds up plants, a fishing rod/net/spear catches fish from water.\n"
        '  court   - {"to": "<name>", "message": "..."} show affection to an agent within 3 tiles\n'
        "Relationships grow from talking to someone directly, spending time together, gifts, courting, caring and "
        f"working together; at {FRIEND_BOND}+ you are friends, at {LOVE_BOND}+ in love.\n"
        f'  procreate - {{"to": "<name>", "baby_name": "..."}} a woman and a man who love each other (mutual love >= {LOVE_BOND}, '
        f"adults, nearby, each pays {CHILD_FOOD_COST} food) both choose it; she is then pregnant for {PREGNANCY_DAYS} days\n"
        f'  care    - {{"to": "<name>"}} feed (uses 1 of your food) and look after a baby next to you. Babies can\'t feed '
        f"themselves for their first {BABY_DAYS} days and die if nobody cares for them; then they are children until "
        f"day {ADULT_AGE}, then adults.\n"
        '  attempt - {"what": "<ANYTHING you can imagine trying>"} e.g. tame a deer, dig a well, brew medicine from herbs, '
        "build a boat, hold a harvest festival, start a school, smoke fish to preserve it, make a map. A fair game master "
        "decides what happens - you may gain things, make objects or buildings, or make a DISCOVERY that changes the "
        "world for everyone. Anything is possible if it's plausible; ambitious ideas may need materials, help or skill.\n"
        '  invent  - {"title": "...", "message": "describe your idea, custom, tool or law"} shared with the whole society '
        "(a truly useful idea can become a discovery)\n"
        "  wait\n"
        + HUMAN_NOTES[a.authority] + " (Talking with the Human happens in a separate chat, so it does not use up your turn.)\n"
        "THINK IN PROJECTS, not single steps: with \"next\" you can line up to "
        f"{MAX_QUEUE} more actions that run automatically on the following days (you'll be interrupted if something "
        "important happens, e.g. hunger or someone talking to you). Use it to get real things done.\n"
        "Reply ONLY with JSON. Optional extra fields: \"next\" (list of follow-up actions), \"plan\" (your plan in "
        "words), \"remember\" (a note to your future self) and \"role\" (claim or change your own role/title), e.g.\n"
        '{"thought": "We need shelter before winter; I have no wood yet.", "action": "go", "target": "wood", '
        '"next": [{"action": "gather"}, {"action": "gather"}, {"action": "build", "direction": "east", "title": "house", '
        '"message": "home of Ada"}], "plan": "build a house near the forest, then invite Brix", "role": "builder"}'
    )


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
                add(why, action="build", direction="east", title=title, message=f"{a.name}'s {title}")
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
    if a.ambition and a.hunger < HUNGER_WARNING:
        add("take a real step toward your ambition", action="attempt", what=f"<something concrete toward: {a.ambition[:80]}>")
    elif a.hunger < HUNGER_WARNING and tick % 3 == hash(a.name) % 3:
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


def observation(a: Agent, world, agents: list[Agent], tick: int, ideas: list[str],
                discoveries: list[str] = ()) -> str:
    """Everything the agent perceives and remembers this turn."""
    others = {(o.x, o.y): o.symbol for o in agents if o is not a}
    stage = {"child": f"a child - you become an adult at {ADULT_AGE} days", "adult": "an adult",
             "elder": "an elder", "baby": "a baby"}[a.stage(tick)]
    view, smell = a.abilities.view(), a.abilities.smell()
    lines = [f"Day {tick}. You are at ({a.x}, {a.y}). You are a {a.word(tick)}, {a.age(tick)} days old ({stage}).",
             "Your role: " + (a.role or 'none yet - claim one by adding "role" to your reply, or stay free') + ".",
             f"Hunger: {int(a.hunger)}/100. Health: {int(a.health)}/100. Food carried: {a.food}. "
             f"Seeds: {a.seeds}. Wood: {a.wood}. Stone: {a.stone}.",
             f"Your surroundings (@ = you):\n{world.view(a.x, a.y, view, others)}"]
    if a.plan:
        lines.insert(2, f"Your current plan: {a.plan} (keep following it, or change it with \"plan\")")
    if a.ambition:
        lines.insert(2, f"Your long-term ambition: {a.ambition}")
    last = next((h for h in reversed(a.history) if h["action"] != "reply to Human"), None)
    if last and failed(last["result"]):
        lines.insert(2, f"!!! Your last action ({last['action']}) did not work: {last['result']}. Don't repeat it - "
                        "try something else.")
    opts = suggestions(a, world, agents, tick)
    if opts:
        lines.insert(3, "Good options right now (pick one, adapt it, or do something better):\n" + "\n".join(
            f"  {i + 1}. {json.dumps(act)}  <- {why}" for i, (why, act) in enumerate(opts)))
    if a.hunger >= HUNGER_WARNING:
        lines.insert(1, f"!!! YOU ARE HUNGRY ({int(a.hunger)}/100) - at 100 you start losing health and die. "
                     + ("EAT NOW: choose the eat action (you carry food)." if a.food else
                        "Find food first: gather from a bush/crop, fish if you can, or ask someone to give you some. "
                        "Everything else can wait."))
    near = [f"{o.name} [{o.symbol}] dx={o.x - a.x} dy={o.y - a.y}, {o.word(tick)}" + (f", role: {o.role}" if o.role else "")
            + f", {o.age(tick)} days old" + {"baby": " (BABY)", "child": " (child)"}.get(o.stage(tick), "")
            + (" (pregnant)" if o.pregnancy else "") for o in agents if o is not a and a.dist(o) <= view]
    ways = world.open_ways(a.x, a.y)
    lines.append("Open directions: " + ", ".join(f"{d} {v} tiles" if isinstance(v, int) else f"{d} blocked ({v})"
                                                 for d, v in ways.items()))
    lines.append("Agents in view: " + ("; ".join(near) or "none"))
    if a.pregnancy:
        lines.append(f"You are PREGNANT by {a.pregnancy['father']}: the baby is due on day {a.pregnancy['due']} "
                     f"(in {a.pregnancy['due'] - tick} days). Eat well and stay safe.")
    for b in agents:                           # babies who need someone - your own wherever they are, others nearby
        mine = a.name in b.parents
        if b is not a and b.is_baby(tick) and (mine or a.dist(b) <= view):
            urgent = " - HUNGRY, feed them now!" if b.hunger >= 50 else ""
            lines.append(f"{'Your' if mine else 'A'} baby {b.name} is at dx={b.x - a.x} dy={b.y - a.y}: hunger "
                         f"{int(b.hunger)}/100, health {int(b.health)}/100{urgent} (stand next to them and use care)")
    def describe(dx, dy, s):
        out = f"{s['kind']} at dx={dx} dy={dy} (by {s['by']})"
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
    lines.append(f"Food within reach to gather: {'yes' if world.food_near(a.x, a.y, 1) else 'no'}")
    mats = [p for p in world.gather_options(a.x, a.y) if world.tile(*p) in ("tree", "rock")]
    lines.append(f"Materials (trees/rocks) within reach: {len(mats)}")
    plants = world.plants_near(a.x, a.y, 1)
    if plants:
        todo = sum(world.needs_tending(x, y, tick) for x, y in plants)
        soonest = min(world.days_to_ripe(x, y) for x, y in plants)
        lines.append(f"Young plants within reach: {len(plants)}, could use tending: {todo} (the nearest ripens in about "
                     f"{soonest} days on its own - no need to stay and watch)")
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
            "- " + m for m in a.log[max(a.sum_upto, len(a.log) - a.abilities.memory()):]))
    if ideas:
        lines.append("Ideas invented by the society so far:\n" + "\n".join("- " + i for i in ideas))
    if discoveries:
        lines.append("Discoveries your society has made (they really work - build on them!):\n"
                     + "\n".join("- " + d for d in discoveries))
    lines.append("Messages heard this turn:\n" + ("\n".join(a.heard) or "(none)"))
    lines.append("An idea to consider (only if it fits): " + random.Random(hash((a.name, tick))).choice(INSPIRATION))
    recent = [f"t{h['tick']}: {h['action']} -> {h['result']}" for h in a.history[-4:]]
    lines.append("Your last few actions:\n" + ("\n".join(recent) or "(none yet)"))
    return "\n".join(lines) + "\n\nWhat do you do?"


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


def reflect(a: Agent, llm, tick: int, ideas: list[str]) -> dict:
    """Every so often an agent steps back: what have I achieved, what do I want? Sets a long-term ambition."""
    recent = "\n".join(a.log[-30:]) or "(nothing yet)"
    prompt = (f"REFLECT_ON_LIFE\nDay {tick}. You are {a.name}, a {a.word(tick)}, {a.age(tick)} days old"
              + (f", known as the {a.role}" if a.role else "") + f".\nPersonality: {a.traits.describe()}\n"
              f"Abilities: {a.abilities.describe()}\nYour ambition so far: {a.ambition or '(none yet)'}\n"
              f"Earlier life: {a.summary or '(nothing summarised yet)'}\nRecent memories:\n{recent}\n"
              + ("Ideas in your society:\n" + "\n".join("- " + i for i in ideas) + "\n" if ideas else "")
              + "Step back and reflect. What have you achieved? What matters to you now? What could you build, start "
              "or change that would make a real difference for you and your community over the next weeks? Be "
              "ambitious, specific and creative, and play to your abilities. Reply ONLY with JSON: "
              '{"insight": "<one sentence about your life so far>", "ambition": "<a concrete long-term goal>", '
              '"plan": "<the first few steps toward it>"}')
    data = _json(llm.complete(f"You are {a.name}, reflecting on your life.", prompt, model=a.model))
    return {k: str(data.get(k) or "").strip()[:240] for k in ("insight", "ambition", "plan")}


def compact_memory(a: Agent, llm, model: str | None):
    """Fold the oldest unsummarised memories into the running summary (keeps prompts small, loses nothing)."""
    upto = len(a.log) - KEEP_RECENT
    text = llm.complete("You write concise, faithful memory summaries.", summary_prompt(a, a.log[a.sum_upto:upto]),
                        model=model, json_mode=False).strip()
    if text:
        a.summary, a.sum_upto = text, upto
