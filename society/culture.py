"""Culture: stories that change as they're retold, place names, and peoples who don't (yet) speak each other's
language.

Notable events leave story seeds; at each review Sol turns one into a story, or retells an old one a little
differently. Stories spread for free around the fire on evenings, and when someone tells one. They're part of what
agents know about their world (and themselves).

Two peoples start far apart. Until someone has talked with the other people enough, their words come across only as
a few recognisable words and gestures."""
import re

from . import clock

PEOPLES = {"Riverfolk": "#4d96ff", "Hillfolk": "#e76f51"}
FLUENT = 8                      # exchanges with a people before you understand them
LEXICON = ("food", "water", "friend", "help", "danger", "wood", "stone", "fire", "home", "come", "give", "trade",
           "yes", "no", "love", "baby", "eat", "hungry", "hello", "thank", "deer", "fish", "berries", "house", "here")
FIRESIDE_HOURS = (19, 20, 21)
PLACE_GAP = 6                   # two named places can't be closer than this


# ================================================================ peoples & language
def understands(listener, speaker) -> bool:
    if not speaker.people or not listener.people or speaker.people == listener.people:
        return True
    return (listener.fluency.get(speaker.people, 0) >= FLUENT or speaker.fluency.get(listener.people, 0) >= FLUENT)


def garble(msg: str) -> str:
    words = [w for w in LEXICON if re.search(rf"\b{w}", msg.lower())]
    return ("speaks in a strange tongue" + (f" - you make out: {', '.join(repr(w) for w in words[:3])}" if words
                                             else ", gesturing") + ".")


def exchange(a, b):
    """Talking (or trading) with someone of another people teaches a little of their language."""
    if a.people and b.people and a.people != b.people:
        a.fluency[b.people] = a.fluency.get(b.people, 0) + 1
        b.fluency[a.people] = b.fluency.get(a.people, 0) + 1


def contact(sim, tick):
    """First meetings between peoples (and between individual strangers)."""
    alive = [a for a in sim.agents.values() if a.people and not a.is_baby(tick)]
    for a in alive:
        for b in alive:
            if b.people == a.people or b.people in a.met or a.dist(b) > a.abilities.view() + 3:
                continue
            a.met.append(b.people)
            a.remember(tick, f"I met {b.name}, a stranger of the {b.people}. Their words sound strange to me.")
            a.heard.append(f"You see {b.name}, a stranger of the {b.people}! They don't speak your language yet.")
            pair = "|".join(sorted((a.people, b.people)))
            if pair not in sim.contacts:
                sim.contacts.append(pair)
                sim.event(tick, a, f"FIRST CONTACT: the {a.people} met the {b.people} ({a.name} and {b.name})", "contact")
                sim.seed_story(tick, f"The day the {a.people} first met the {b.people}: {a.name} and {b.name}", [a.name, b.name])


# ================================================================ stories
def learn(a, sid) -> bool:
    if sid in a.stories:
        return False
    a.stories.append(sid)
    return True


def story(sim, sid):
    return next((s for s in sim.stories if s["id"] == sid), None)


def find_story(sim, a, title: str):
    t = str(title or "").lower().strip()
    mine = [story(sim, i) for i in a.stories if story(sim, i)]
    return next((s for s in mine if t and (t in s["title"].lower() or s["title"].lower() in t)), None)


def add_story(sim, title: str, text: str, about: list[str], tick: int, by: str = "Sol") -> dict | None:
    title, text = str(title or "").strip()[:60], str(text or "").strip()[:500]
    if not title or not text:
        return None
    old = next((s for s in sim.stories if s["title"].lower() == title.lower()), None)
    if old:                                         # retold: it changes a little every time
        old.update(text=text, version=old["version"] + 1, tick=tick)
        return old
    s = {"id": sim.next_id("story"), "title": title, "text": text, "about": [n for n in about if isinstance(n, str)][:4],
         "tick": tick, "version": 1, "by": by}
    sim.stories.append(s)
    knowers = set(s["about"]) | {by}
    for name in list(knowers):
        a = sim.agents.get(name)
        if a and a.group and a.group in sim.groups:
            knowers |= set(sim.groups[a.group]["members"])
    for name in knowers:
        if name in sim.agents:
            learn(sim.agents[name], s["id"])
    return s


def tell(sim, a, title: str, words: str, to: str, tick: int) -> str:
    s = find_story(sim, a, title)
    if not s:
        if len(words or "") < 20:
            return "tell which story? (title of one you know - or tell a new one in message)"
        s = add_story(sim, title or f"{a.name}'s tale", words, [a.name], tick, a.name)
        if not s:
            return "that story has no words"
        learn(a, s["id"])
        sim.event(tick, a, f'made up a new story: "{s["title"]}"', "story")
    listeners = [o for o in sim.agents.values() if o is not a and a.dist(o) <= 8 and not o.is_baby(tick)
                 and to in ("all", o.name, "", None)]
    new = 0
    for o in listeners:
        if understands(o, a):
            new += learn(o, s["id"])
            o.remember(tick, f'{a.name} told me the story of "{s["title"]}".')
            sim.bond(o, a, 2)
    return f'told the story of "{s["title"]}" to {len(listeners)} (new to {new})'


def fireside(sim, tick):
    """Evenings: people around a fire share a story (no model call)."""
    if clock.when(tick)["hour"] not in FIRESIDE_HOURS:
        return
    for b in sim.world.buildings.values():
        if b.get("function") != "fire" or not b.get("done", True):
            continue
        around = [a for a in sim.agents.values() if not a.is_baby(tick) and sim.world._gap(b, a.x, a.y) <= 3]
        if len(around) < 2:
            continue
        known = {sid for a in around for sid in a.stories}
        teller = max(around, key=lambda a: (len(a.stories), a.traits.social))
        fresh = [sid for sid in teller.stories if any(sid not in o.stories for o in around)]
        if not fresh:
            continue
        s = story(sim, sim.rng.choice(fresh))
        if not s:
            continue
        for o in around:
            o.needs["belonging"] = max(0, o.needs.get("belonging", 30) - 10)
            if o is not teller and understands(o, teller) and learn(o, s["id"]):
                o.remember(tick, f'Around the fire {teller.name} told the story of "{s["title"]}".')
        del known


def stories_for(sim, a, k=2) -> list[str]:
    mine = [story(sim, i) for i in a.stories[-6:]]
    return [f'"{s["title"]}": {s["text"][:160]}' for s in mine if s][-k:]


# ================================================================ places
def name_place(sim, a, title: str, tick: int) -> str:
    title = re.sub(r"\s+", " ", str(title or "")).strip()[:30]
    if len(title) < 3:
        return "give the place a name (title)"
    if any(p["name"].lower() == title.lower() for p in sim.places):
        return f"there is already a place called {title} - choose another name"
    near = nearest_place(sim, a.x, a.y, PLACE_GAP)
    if near and near["by"] != a.name:
        return f'this area is already called {near["name"]} (named by {near["by"]})'
    if near:
        near["name"] = title
    else:
        sim.places.append({"name": title, "x": a.x, "y": a.y, "by": a.name, "tick": tick})
    a.remember(tick, f"I named the place around ({a.x}, {a.y}) {title}.")
    sim.event(tick, a, f"named the place around ({a.x}, {a.y}) {title}", "story")
    return f"named this place {title}"


def nearest_place(sim, x, y, radius=12):
    best = min(sim.places, key=lambda p: max(abs(p["x"] - x), abs(p["y"] - y)), default=None)
    return best if best and max(abs(best["x"] - x), abs(best["y"] - y)) <= radius else None
