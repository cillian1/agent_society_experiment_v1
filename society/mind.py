"""How an agent thinks: what it is told (prompts), how it answers (parsing) and calls to its model."""
import json
import re

from .config import (BUILD_COST, CHILD_FOOD_COST, COMPACT_AFTER, CRAFT_COST, FRIEND_BOND, HUNGER_WARNING,
                     KEEP_RECENT, LOVE_BOND, MAX_ITEMS, MAX_STEPS, ORDER_MEMORY_DAYS, SMELL_RADIUS, VIEW_RADIUS)
from .models import Agent

DIRS = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
ACTIONS = ("move", "gather", "eat", "say", "give", "plant", "tend", "build", "craft", "court", "procreate",
           "invent", "wait")

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
        f"You are {a.name}, one of {len(others) + 1} agents living in a 2D tile world "
        f"(the others: {', '.join(others) or 'nobody yet'}). Nobody has a job or a role until they invent one; "
        "nobody is anybody's family until children are born. You are free to do what you want: explore, "
        "talk, make friends (or enemies), plan together, farm, build, invent customs, tools, jobs and laws. "
        "Be creative and resourceful, and think about how to solve your problems in new ways. "
        "Talking is valuable: answer people who speak to you, share what you know, ask questions, make deals. "
        "You remember everything that has happened to you. Survival comes first: eat before you get very hungry, "
        "and keep some food on you. Don't repeat or echo what others just said, and don't repeat your own last action "
        "if it isn't working - try something new, specific and concrete.\n"
        f"Goal: {a.goal}\nPersonality: {a.traits.describe()}\n\n"
        "World: g grass, . sand, ~ water (impassable), # rock (impassable), ^ tree (impassable), f wild food bush "
        "(slow to regrow), , young plant, * ripe crop, & a structure someone built. North is up (y decreases), "
        "east is right. Uppercase letters are agents (you are @). "
        "Most of the world is unexplored: you only see a small area around you, and exploring finds new food, water, "
        "forests and rocks that your whole community can use. Be curious. Building and crafting make life better. "
        "Hunger rises every day; at 100 you take damage and can starve. Eating food lowers hunger. "
        "Life lasts roughly 500-700 days; one turn is one day.\n"
        "Each turn pick ONE action:\n"
        f'  move    - {{"direction": "north|south|east|west", "steps": 1-{MAX_STEPS}}} walk several tiles (stops at obstacles)\n'
        "  gather  - take from an adjacent/own-tile food bush or ripe crop (food, sometimes seeds), tree (wood) or rock "
        "(stone); next to water with a fishing tool you catch fish (food)\n"
        "  eat     - eat one carried food (hunger -40)\n"
        '  say     - {"to": "<name or all>", "message": "..."} heard within 8 tiles; talk to people!\n'
        '  give    - {"to": "<name>", "title": "<object name, optional>"} hand one food (or that object) to an adjacent agent\n'
        '  plant   - {"direction": "..."} put a carried seed into an adjacent grass tile\n'
        "  tend    - work on a young plant within reach to help it grow (faster with a helper)\n"
        f'  build   - {{"direction": "...", "title": "<house, wall, bridge, sign, anything>", "message": "<description or sign text>"}} '
        f"costs {BUILD_COST} wood/stone; bridges/paths/floors can be walked on, everything else blocks. Water only takes bridges/docks.\n"
        f'  craft   - {{"title": "<axe, pickaxe, hoe, fishing rod, basket, anything>", "message": "what it is for"}} costs '
        f"{CRAFT_COST} wood/stone; you carry it (max {MAX_ITEMS}). Objects matter: an axe/hatchet gets extra wood, a "
        "pickaxe/hammer extra stone, a hoe/shovel/rake speeds up plants, a fishing rod/net/spear catches fish from water.\n"
        '  court   - {"to": "<name>", "message": "..."} show affection to an agent within 3 tiles\n'
        f'  procreate - {{"to": "<name>", "baby_name": "..."}} both partners must choose it (needs mutual love >= {LOVE_BOND}, '
        f"adults, nearby, each pays {CHILD_FOOD_COST} food)\n"
        '  invent  - {"title": "...", "message": "describe your idea, custom, tool or law"} shared with the whole society\n'
        "  wait\n"
        + HUMAN_NOTES[a.authority] + " (Talking with the Human happens in a separate chat, so it does not use up your turn.)\n"
        "Reply ONLY with JSON. Optional extra fields: \"remember\" (a note to your future self) and \"role\" "
        "(claim or change your own role/title whenever you like), e.g.\n"
        '{"thought": "<1-2 sentences of private reasoning>", "action": "say", "to": "Ada", "message": "Want to farm together?", "role": "farmer"}'
    )


def observation(a: Agent, world, agents: list[Agent], tick: int, ideas: list[str]) -> str:
    """Everything the agent perceives and remembers this turn."""
    others = {(o.x, o.y): o.symbol for o in agents if o is not a}
    stage = "adult" if a.adult(tick) else "child - you can't have children yet"
    lines = [f"Day {tick}. You are at ({a.x}, {a.y}). You are {a.age(tick)} days old ({stage}).",
             "Your role: " + (a.role or 'none yet - claim one by adding "role" to your reply, or stay free') + ".",
             f"Hunger: {int(a.hunger)}/100. Health: {int(a.health)}/100. Food carried: {a.food}. "
             f"Seeds: {a.seeds}. Wood: {a.wood}. Stone: {a.stone}.",
             f"Your surroundings (@ = you):\n{world.view(a.x, a.y, VIEW_RADIUS, others)}"]
    if a.hunger >= HUNGER_WARNING:
        lines.insert(1, f"!!! YOU ARE HUNGRY ({int(a.hunger)}/100) - at 100 you start losing health and die. "
                     + ("EAT NOW: choose the eat action (you carry food)." if a.food else
                        "Find food first: gather from a bush/crop, fish if you can, or ask someone to give you some. "
                        "Everything else can wait."))
    near = [f"{o.name} [{o.symbol}] dx={o.x - a.x} dy={o.y - a.y}" + (f", role: {o.role}" if o.role else "")
            + f", {o.age(tick)} days old" for o in agents if o is not a and a.dist(o) <= VIEW_RADIUS]
    lines.append("Agents in view: " + ("; ".join(near) or "none"))
    built = [f"{s['kind']} at dx={dx} dy={dy}" + (f' ("{s["text"]}")' if s["text"] else "") + f" built by {s['by']}"
             for dx, dy, s in world.structures_near(a.x, a.y, VIEW_RADIUS)][:6]
    if built:
        lines.append("Structures in view: " + "; ".join(built))
    food = world.food_near(a.x, a.y, SMELL_RADIUS)
    if food:
        dx, dy = food[0][0] - a.x, food[0][1] - a.y
        where = ", ".join(p for p in (f"{abs(dx)} east" if dx > 0 else f"{abs(dx)} west" if dx < 0 else "",
                                      f"{abs(dy)} south" if dy > 0 else f"{abs(dy)} north" if dy < 0 else "") if p)
        lines.append(f"Nearest food: dx={dx} dy={dy} ({where or 'right here'})")
    else:
        lines.append("Nearest food: none sensed")
    un = world.nearest_unexplored(a.x, a.y)
    if un:
        dx, dy = un
        lines.append(f"Your community has explored {world.explored_pct()}% of the world. Nearest unexplored area: "
                     f"dx={dx} dy={dy} ({compass(dx, dy)}, ~{max(abs(dx), abs(dy))} tiles away)")
    if a.items:
        lines.append("Objects you carry: " + "; ".join(i["name"] + (f" ({i['text']})" if i["text"] else "") for i in a.items))
    if a.materials() >= CRAFT_COST:
        lines.append(f"You have {a.wood} wood and {a.stone} stone: you could build a structure or craft a useful object.")
    if world.water_near(a.x, a.y):
        lines.append("You are next to water" + ("" if a.has_tool("fish") else " (a fishing rod/net would let you catch fish here)") + ".")
    lines.append(f"Food within reach to gather: {'yes' if world.food_near(a.x, a.y, 1) else 'no'}")
    mats = [p for p in world.gather_options(a.x, a.y) if world.tile(*p) in ("tree", "rock")]
    lines.append(f"Materials (trees/rocks) within reach: {len(mats)}")
    lines.append(f"Young plants within reach to tend: {len(world.plants_near(a.x, a.y, 1))}")
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
            "- " + m for m in a.log[max(a.sum_upto, len(a.log) - KEEP_RECENT - COMPACT_AFTER):]))
    if ideas:
        lines.append("Ideas invented by the society so far:\n" + "\n".join("- " + i for i in ideas))
    lines.append("Messages heard this turn:\n" + ("\n".join(a.heard) or "(none)"))
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
            "If they gave an instruction, say what you will do about it first. Reply ONLY with JSON: "
            '{"thought": "<private reasoning>", "message": "<what you say to them>"}')


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


def parse_action(raw: str, others: list[str]) -> dict:
    data = _json(raw)
    s = lambda k: str(data.get(k) or "").strip()
    to = data.get("to", "all")
    if to not in ("all", "Human") and to not in others:
        to = "all"
    return {"thought": s("thought") or raw[:200].strip(),
            "action": data.get("action") if data.get("action") in ACTIONS else "wait",
            "direction": data.get("direction"), "to": to, "message": s("message"), "title": s("title"),
            "baby_name": s("baby_name"), "remember": s("remember"), "role": s("role"),
            "steps": data.get("steps") if isinstance(data.get("steps"), int) else 1}


def failed_action(err: Exception) -> dict:
    return parse_action(json.dumps({"thought": f"(my mind failed this turn: {err})"[:300], "action": "wait"}), [])


# ---------------------------------------------------------------- calls to the model
def decide(a: Agent, llm, prompt: str, others: list[str]) -> dict:
    return parse_action(llm.complete(system_prompt(a, others), prompt, model=a.model), others)


def reply(a: Agent, llm, situation: str, human_msg: str, others: list[str], also_to: list[str]) -> dict:
    raw = llm.complete(system_prompt(a, others), reply_prompt(a, situation, human_msg, also_to), model=a.model)
    data = _json(raw)
    return {"thought": str(data.get("thought") or "").strip(),
            "message": str(data.get("message") or (raw if not data else "")).strip()}


def compact_memory(a: Agent, llm, model: str | None):
    """Fold the oldest unsummarised memories into the running summary (keeps prompts small, loses nothing)."""
    upto = len(a.log) - KEEP_RECENT
    text = llm.complete("You write concise, faithful memory summaries.", summary_prompt(a, a.log[a.sum_upto:upto]),
                        model=model, json_mode=False).strip()
    if text:
        a.summary, a.sum_upto = text, upto
