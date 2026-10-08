"""Scripted stand-in for a model so the simulation can run offline. It does NOT think - it pattern-matches the prompt."""
import json
import random
import re

from .llm import UsageMixin


class MockLLM(UsageMixin):
    """Offline stand-in: seeks food, eats when hungry, wanders and chats a little. NOT real thinking."""

    LINES = ["Found some berries over here!", "Anyone seen water nearby?",
             "Let's stick together.", "I'll look around the east side.", "Careful, rocks ahead."]

    def __init__(self, seed: int = 0):
        self._init_usage()
        self.rng = random.Random(seed)

    def complete(self, system: str, prompt: str, model: str | None = None, json_mode: bool = True) -> str:
        self._record("mock", 0, 0)
        rng = self.rng
        if "SUMMARIZE_MEMORIES" in prompt:
            lines = prompt.split("New memories to fold in:\n", 1)[-1].split("\n\nWrite the updated")[0].splitlines()
            return "I remember: " + " ".join(l.split(": ", 1)[-1] for l in lines)[:600]
        if "SOL_REVIEW" in prompt or "SOL_CHAT" in prompt:
            names = re.findall(r"^- (\w+) \(", prompt, re.M)
            who = names[0] if names else None
            d = dict(speech="Work together: store spare food and build what is missing.", next_review_in_days=2,
                     note_to_human="They are surviving; farming and storage need work.",
                     advice={who: {"message": "Stop chatting and gather wood for a storehouse.",
                                   "next": [{"action": "go", "target": "wood"}, {"action": "gather"}]}} if who else {})
            if "SOL_CHAT" in prompt:
                d["message"] = "[MOCK] I'll pass that on to everyone."
            seed = re.search(r"STORYTELLER: these happened recently:\n- [^\n]*?\d\d:\d\d: (.+)", prompt)
            if seed:
                d["story"] = {"title": "The Tale of " + seed.group(1)[:30], "text": f"Long ago, {seed.group(1)}. The elders still speak of it.",
                              "about": re.findall(r"\b([A-Z][a-z]+)\b", seed.group(1))[:2]}
            if "CHRONICLE:" in prompt:
                d["chapter"] = {"title": "A month of toil", "text": "The people gathered, built and argued, and the world turned."}
            return json.dumps(d)
        if "GAME_MASTER_BLUEPRINT" in prompt:
            return json.dumps(dict(cost={"wood": rng.randint(1, 4), "stone": rng.randint(0, 3)},
                                   function=rng.choice(["home", "fire", "none"]), description="a mock blueprint"))
        if "GAME_MASTER" in prompt:
            ideas = [("Smoked Fish", "hunger"), ("Irrigation Ditches", "growth"), ("Herbal Medicine", "health"),
                     ("The Wheel", "speed"), ("Stone Tools", "materials"), ("Harvest Festival", "friendship")]
            name, effect = rng.choice(ideas)
            ok = rng.random() < 0.7
            return json.dumps(dict(success=ok, story="After some effort, it " + ("worked!" if ok else "fell apart."),
                                   gain={"food": 1 if ok else 0}, cost={"wood": 1},
                                   discovery={"name": name, "description": "a mock discovery", "effect": effect,
                                              "amount": 1} if ok and rng.random() < 0.4 else None))
        if "REFLECT_ON_LIFE" in prompt:
            goal = rng.choice(["build a village by the lake", "become the best farmer around", "map the whole world",
                               "raise a big family", "make tools for everyone"])
            d = dict(insight="I have survived so far, but I want more.", ambition=goal, plan=f"start working toward: {goal}",
                     beliefs=[rng.choice(["the east has the most berries", "the river floods in spring", "strangers can't be trusted"])],
                     dream=rng.choice(["I flew over the lake.", "The forest was singing.", "I was lost in fog, then found a path."]),
                     idea=rng.choice(["", "", "a raft to cross the water"]))
            if "FOLD_MEMORIES" in prompt:
                d["summary"] = "I remember: " + prompt.split("FOLD_MEMORIES", 1)[1][:400]
            return json.dumps(d)
        if "CHAT_WITH_HUMAN" in prompt:
            who = re.search(r"You are (\w+),", system)
            asked = re.search(r'just said to you[^:]*: "([^"]*)"', prompt)
            d = dict(thought="The human spoke to me, I should answer.",
                     message=f"[MOCK MODE - scripted, not a real reply] This is {who.group(1) if who else 'me'}.")
            if asked and "wood" in asked.group(1).lower():
                d.update(plan="fetch wood for the Human", next=[{"action": "go", "target": "wood"}, {"action": "gather"}])
            if asked and "ambition" in asked.group(1).lower():
                d.update(ambition=asked.group(1))
            return json.dumps(d)
        hunger = int(re.search(r"Hunger: (\d+)", prompt).group(1))
        carried = int(re.search(r"Food carried: (\d+)", prompt).group(1))
        seeds = int(re.search(r"Seeds: (\d+)", prompt).group(1))
        reach = bool(re.search(r"Within reach to gather: food", prompt))
        mats = int((re.search(r"(\d+) trees/rocks", prompt) or [0, 0])[1])
        mat_have = sum(int(x) for x in re.findall(r"(?:Wood|Stone): (\d+)", prompt))
        friend = re.search(r"Agents in view: (\w+) \[", prompt)
        unexp = re.search(r"Nearest unexplored area: dx=(-?\d+) dy=(-?\d+)", prompt)
        tendable = int((re.search(r"could use tending: (\d+)", prompt) or [0, 0])[1])
        m = re.search(r"Nearest food: dx=(-?\d+) dy=(-?\d+)", prompt) or re.search(r"seen: [\w ]+ at dx=(-?\d+) dy=(-?\d+)", prompt)
        partner = re.search(r"have a child right now with: (\w+)", prompt)
        asked = re.search(r"Choose procreate with to=(\w+)", prompt)
        me = "woman" if re.search(r"You are \w+, a (woman|girl)", prompt) else "man"
        mates = [n for n, sex in re.findall(r"(\w+) \[\w\] dx=-?\d+ dy=-?\d+, (woman|man)\b", prompt) if sex != me]
        near = re.match(r"(\w+)", mates[0]) if mates else None
        if partner or asked:
            return json.dumps(dict(thought="We love each other; let's have a child.", action="procreate",
                                   to=(partner or asked).group(1), baby_name=rng.choice(["Tiko", "Mara", "Bo", "Lio"])))
        social_move = self._society(prompt, rng, hunger, carried)
        if social_move:
            return json.dumps(social_move)
        baby = re.search(r"baby (\w+) is at dx=(-?\d+) dy=(-?\d+): hunger (\d+)", prompt)
        if baby and int(baby.group(4)) >= 40 and carried and not (hunger > 70):
            dx, dy = int(baby.group(2)), int(baby.group(3))
            if max(abs(dx), abs(dy)) <= 1:
                return json.dumps(dict(thought=f"{baby.group(1)} is hungry, I'll feed them.", action="care", to=baby.group(1)))
            dirn = ("east" if dx > 0 else "west") if abs(dx) >= abs(dy) and dx else ("south" if dy > 0 else "north")
            return json.dumps(dict(thought=f"I must get to baby {baby.group(1)}.", action="move", direction=dirn, steps=3))
        if hunger > 55 and not carried and not reach:          # hungry: food first, like the prompt says
            return json.dumps(dict(thought="I'm hungry - food first.", action="go", target="food"))
        if carried and hunger > 45:
            d = dict(thought="I'm getting hungry, time to eat.", action="eat")
        elif reach and hunger > 20:
            d = dict(thought="Food is right here, grabbing it.", action="gather")
        elif mat_have >= 2 and rng.random() < 0.25:
            d = dict(thought="I have materials; let me build something useful.", action="build",
                     direction=rng.choice(["north", "south", "east", "west"]),
                     title=rng.choice(["shelter", "sign", "storage hut", "bridge"]),
                     message=rng.choice(["Meet here to share news.", "A safe place to rest.", "Free food storage."]))
        elif mat_have >= 1 and rng.random() < 0.2:
            d = dict(thought="A tool would help me; I'll craft one.", action="craft",
                     title=rng.choice(["axe", "pickaxe", "hoe", "fishing rod", "basket"]), message="a useful tool")
        elif mats and mat_have < 4 and rng.random() < 0.5:
            d = dict(thought="A project: gather materials, then build a house.", action="gather",
                     next=[{"action": "gather"}, {"action": "build", "direction": rng.choice(["north", "south", "east", "west"]),
                            "title": "house", "message": "a home"}])
        elif friend and rng.random() < 0.3:
            d = dict(thought=f"Let me chat with {friend.group(1)}.", action="say", to=friend.group(1),
                     message=rng.choice(self.LINES), role=rng.choice(["", "", "farmer", "builder", "storyteller"]))
        elif tendable and rng.random() < 0.8:
            d = dict(thought="This plant needs tending.", action="tend")
        elif seeds and rng.random() < 0.5:
            d = dict(thought="I'll plant a seed and start a little farm.", action="plant",
                     direction=rng.choice(["north", "south", "east", "west"]))
        elif near and rng.random() < 0.5:
            d = dict(thought=f"I like {near.group(1)}; let me show it.", action="court", to=near.group(1),
                     message="You make this world brighter.")
        elif unexp and rng.random() < 0.45:
            d = dict(thought="Time to explore somewhere new.", action="go", target="explore")
        elif m and rng.random() < 0.9:
            d = dict(thought="I can sense food nearby, heading for it.", action="go", to="food")
        elif rng.random() < 0.06:
            d = dict(thought="Let me try something new.", action="attempt",
                     what=rng.choice(["dig a well", "smoke fish to keep it longer", "build a raft", "hold a feast",
                                      "strike flint stones together to make fire", "knap sharp stone tools",
                                      "weave plant fibre into cloth", "shape clay pots and fire them", "plow and sow a field",
                                      "make a spear for hunting", "herd and tame goats"]))
        elif rng.random() < 0.05:
            d = dict(thought="An idea!", action="invent", title="Shared Harvest",
                     message="Everyone brings extra food to the middle of the map.")
        elif rng.random() < 0.2:
            d = dict(thought="Let me tell the others something.", action="say", to="all", message=rng.choice(self.LINES))
        else:
            d = dict(thought="Nothing in sight, wandering.", action="move", direction=rng.choice(["north", "south", "east", "west"]))
        return json.dumps(d)

    def _society(self, prompt, rng, hunger, carried):
        """The mock's take on the newer systems, so offline runs and tests exercise them."""
        offer = re.search(r"Offer from (\w+) \(deal (\d+)\)", prompt)
        if offer:
            return dict(thought="A fair trade.", action=rng.choice(["accept", "accept", "decline"]), target=offer.group(2))
        owe = re.search(r"You promised (\w+) (\d+) (food|wood|stone|seeds)", prompt)
        if owe and rng.random() < 0.5:
            return dict(thought="I keep my word.", action="give", to=owe.group(1), title=owe.group(3), amount=int(owe.group(2)))
        if "You feel exhausted" in prompt and rng.random() < 0.7:
            return dict(thought="I need a rest.", action="rest")
        beast = re.search(r"Animals nearby: (deer|rabbit|boar|goat|sheep) dx=(-?\d+) dy=(-?\d+)", prompt)
        if beast and hunger > 30 and rng.random() < 0.5:
            near = max(abs(int(beast.group(2))), abs(int(beast.group(3)))) <= 1
            if near:
                kind = beast.group(1)
                return dict(thought=f"A {kind}!", action="tame" if kind in ("goat", "sheep") and carried and rng.random() < 0.4 else "hunt", target=kind)
            return dict(thought="Game nearby - let's hunt.", action="go", target=beast.group(1))
        friend = re.search(r"Agents in view: (\w+) \[", prompt)
        roll = rng.random()
        if "Your group:" not in prompt and roll < 0.04:
            grp = re.search(r'Groups: "([^"]+)"', prompt)
            if grp and friend:
                return dict(thought="I'll join them.", action="join", title=grp.group(1))
            return dict(thought="We should band together.", action="found", title=rng.choice(["The Hearth", "Stone Circle", "The Free Folk"]),
                        message="look after each other")
        if "You lead it" in prompt and roll < 0.03:
            return dict(thought="We need rules.", action="propose", title=rng.choice(["No stealing", "No taking from the granary at night",
                                                                                     "No hunting in spring"]))
        if "Proposed law (id" in prompt and roll < 0.3:
            return dict(thought="Good law.", action="support", target=re.search(r"Proposed law \(id (\d+)\)", prompt).group(1))
        if friend and roll < 0.03 and carried >= 2:
            return dict(thought="Let's trade.", action="offer", to=friend.group(1), give="1 food", want="1 wood", within=12)
        if roll < 0.01:
            return dict(thought="This place needs a name.", action="name", title=rng.choice(["Mossy Hollow", "Lake Mira", "Windy Ridge", "Elder Rock"]))
        if "Stories you know:" in prompt and friend and roll < 0.03:
            return dict(thought="Let me tell a story.", action="tell", to="all", title=re.search(r'Stories you know: "([^"]+)"', prompt).group(1))
        if friend and roll < 0.005:
            return dict(thought="I want what they have.", action="steal", to=friend.group(1), title="food")
        return None
