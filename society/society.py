import json
import random
import re
import string
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .agent import (ADULT_AGE, CHILD_COOLDOWN, CHILD_FOOD_COST, DIRS, HEARING_RADIUS, LOVE_BOND,
                    Agent, Traits)
from .world import GRASS, GROW_NEEDED, World

PALETTE = ["#ff6b6b", "#ffd93d", "#6bcB77", "#4d96ff", "#c77dff", "#ff9f45", "#2ec4b6", "#f15bb5"]
HAIKU, SONNET, OPUS = "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"
TIERS = {"haiku": HAIKU, "sonnet": SONNET, "opus": OPUS}
BABY_NAMES = ["Nova", "Pip", "Juno", "Kit", "Rue", "Sol", "Tove", "Wren", "Zed", "Lark", "Moss", "Ember",
              "Fig", "Sage", "Briar", "Onyx", "Dale", "Ivy", "Rook", "Tansy"]
HUNGER_PER_TICK = 1.5
EAT_RELIEF = 40
STARVE_DAMAGE = 4
MAX_IDEAS_IN_PROMPT = 6


def default_agents() -> list[Agent]:
    return [
        Agent("Ada", "Leader", "Organise the group and keep everyone working toward a shared plan.",
              Traits(0.6, 0.8, 0.9, 0.6, 0.2), ["planning", "persuasion"], model=HAIKU),
        Agent("Brix", "Builder", "Stay near the group's food and find ways to make it more reliable.",
              Traits(0.4, 0.9, 0.4, 0.5, 0.3), ["construction", "engineering"], model=HAIKU),
        Agent("Cleo", "Explorer", "Discover new areas of the map and report what you find.",
              Traits(0.95, 0.3, 0.7, 0.6, 0.4), ["scouting", "mapping"], model=HAIKU),
        Agent("Dov", "Trader", "Accumulate food through deals; trade for advantage.",
              Traits(0.5, 0.6, 0.7, 0.2, 0.5), ["negotiation", "accounting"], model=HAIKU),
        Agent("Eli", "Skeptic", "Question plans, find flaws, and protect the group from bad decisions.",
              Traits(0.7, 0.7, 0.3, 0.2, 0.7), ["critical thinking", "history"], model=HAIKU),
        Agent("Fenn", "Mediator", "Resolve conflicts, find common ground, and steer the group toward long-term wellbeing.",
              Traits(0.85, 0.7, 0.5, 0.9, 0.2), ["diplomacy", "ethics", "synthesis"], model=OPUS),
    ]


def load_agents(path: str) -> list[Agent]:
    """Load agents from a JSON list of {name, role, goal, traits{...}, skills[], model}."""
    out = []
    for d in json.loads(Path(path).read_text()):
        d["traits"] = Traits(**d.get("traits", {}))
        out.append(Agent(**d))
    return out


def _mix(c1: str, c2: str) -> str:
    a, b = (tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (c1, c2))
    return "#" + "".join(f"{(x + y) // 2:02x}" for x, y in zip(a, b))


class Society:
    def __init__(self, agents: list[Agent], llm, world: World | None = None, seed: int | None = None,
                 max_agents: int = 14):
        self.rng = random.Random(seed)
        self.world = world or World(seed=seed)
        self.agents = {a.name: a for a in agents}
        self.dead: dict[str, dict] = {}   # name -> {"agent": Agent, "tick": int, "cause": str}
        self.llm = llm
        self.max_agents = max_agents
        self.tick = 0
        self.events: list[dict] = []
        self.inventions: list[dict] = []
        self.lock = threading.RLock()
        self._spawn()

    def _spawn(self):
        cx, cy = self.world.width // 2, self.world.height // 2
        spots = sorted(((x, y) for y in range(self.world.height) for x in range(self.world.width)
                        if self.world.walkable(x, y)),
                       key=lambda p: abs(p[0] - cx) + abs(p[1] - cy) + self.rng.random() * 6)
        for i, (agent, (x, y)) in enumerate(zip(self.agents.values(), spots)):
            agent.x, agent.y = x, y
            if agent.color == "#ffffff":
                agent.color = PALETTE[i % len(PALETTE)]
            agent.symbol = self._symbol_for(agent.name)

    def _symbol_for(self, name: str) -> str:
        used = {a.symbol for a in self.agents.values()} | {d["agent"].symbol for d in self.dead.values()}
        for ch in name.upper() + string.ascii_uppercase:
            if ch.isalpha() and ch not in used:
                return ch
        return "?"

    # ---- simulation ----
    def step(self):
        with self.lock:
            if not self.agents:
                return
            self.tick += 1
            tick = self.tick
            agents = list(self.agents.values())
            names = list(self.agents)
            ideas = [f"{i['title']} (by {i['by']}): {i['text']}" for i in self.inventions[-MAX_IDEAS_IN_PROMPT:]]
            jobs = [(a, a.observe(self.world, agents, tick, ideas), [n for n in names if n != a.name]) for a in agents]
            heard_by = {a.name: list(a.heard) for a in agents}
            for a in agents:
                a.heard = []
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:  # LLM calls run outside the lock
            acts = list(pool.map(lambda j: j[0].decide(self.llm, j[1], j[2]), jobs))
        with self.lock:
            self.world.update(tick)
            order = list(zip(agents, acts))
            self.rng.shuffle(order)
            for agent, act in order:
                if agent.name not in self.agents:
                    continue
                agent.hunger = min(100.0, agent.hunger + HUNGER_PER_TICK)
                for k in list(agent.bonds):                       # feelings fade slowly without contact
                    agent.bonds[k] *= 0.998
                    if agent.bonds[k] < 1:
                        del agent.bonds[k]
                if agent.hunger >= 100:
                    agent.health -= STARVE_DAMAGE
                elif agent.hunger < 50:
                    agent.health = min(100.0, agent.health + 1)
                if agent.health <= 0:
                    self._die(agent, tick, "starvation")
                    continue
                result = self._apply(agent, act, tick)
                if act["remember"]:
                    agent.memory.append(act["remember"][:200])
                    del agent.memory[:-10]
                agent.history.append({"tick": tick, "x": agent.x, "y": agent.y, "hunger": int(agent.hunger),
                                      "thought": act["thought"], "action": act["action"], "result": result,
                                      "heard": heard_by[agent.name]})

    def _die(self, a: Agent, tick: int, cause: str):
        self.dead[a.name] = {"agent": a, "tick": tick, "cause": cause}
        del self.agents[a.name]
        a.history.append({"tick": tick, "x": a.x, "y": a.y, "hunger": int(a.hunger), "thought": "(died)",
                          "action": "died", "result": cause, "heard": []})
        self._event(tick, a, f"died of {cause} at ({a.x}, {a.y})")
        for o in self.agents.values():
            o.heard.append(f"{a.name} has died ({cause}).")

    def _event(self, tick, agent, text, **extra):
        self.events.append({"tick": tick, "agent": agent.name, "text": text, "color": agent.color, **extra})
        del self.events[:-200]

    def _bond(self, a: Agent, b: Agent, amount: float):
        """a's feeling toward b."""
        a.bonds[b.name] = min(100.0, a.bonds.get(b.name, 0) + amount)

    def _occupied(self, x, y, ignore=None):
        return any(o is not ignore and (o.x, o.y) == (x, y) for o in self.agents.values())

    def _apply(self, a: Agent, act: dict, tick: int) -> str:
        w, kind = self.world, act["action"]
        if kind == "move":
            dx, dy = DIRS.get(act["direction"], (0, 0))
            nx, ny = a.x + dx, a.y + dy
            if (dx, dy) == (0, 0):
                return "invalid direction"
            if not w.in_bounds(nx, ny):
                return "blocked: edge of the world"
            if not w.walkable(nx, ny):
                return f"blocked: {w.tile(nx, ny)}"
            if self._occupied(nx, ny, a):
                return "blocked: another agent"
            a.x, a.y = nx, ny
            return f"moved {act['direction']} to ({nx}, {ny})"
        if kind == "gather":
            for fx, fy in w.food_near(a.x, a.y, 1):
                got = w.harvest(fx, fy, tick)
                if got:
                    food, seeds, tile = got
                    a.food += food
                    a.seeds += seeds
                    what = "a ripe crop" if tile == "crop" else "a wild bush"
                    msg = f"harvested {what} at ({fx}, {fy}): +{food} food" + (f", +{seeds} seed" if seeds else "")
                    self._event(tick, a, msg)
                    return msg
            return "no food within reach"
        if kind == "eat":
            if a.food <= 0:
                return "no food to eat"
            a.food -= 1
            a.hunger = max(0.0, a.hunger - EAT_RELIEF)
            self._event(tick, a, "ate some food")
            return "ate food"
        if kind == "say":
            if not act["message"]:
                return "said nothing"
            targets = [o for o in self.agents.values() if o is not a
                       and max(abs(o.x - a.x), abs(o.y - a.y)) <= HEARING_RADIUS
                       and act["to"] in ("all", o.name)]
            for o in targets:
                o.heard.append(f'{a.name} says{"" if act["to"] == "all" else " to you"}: "{act["message"]}"')
                if act["to"] == o.name:
                    self._bond(o, a, 2)
                    self._bond(a, o, 1)
            a.last_say, a.last_say_tick = act["message"], tick
            self._event(tick, a, f'to {act["to"]}: "{act["message"]}"')
            return f'said "{act["message"]}" to {act["to"]} ({len(targets)} heard)'
        if kind == "give":
            o = self.agents.get(act["to"])
            if not o or o is a or max(abs(o.x - a.x), abs(o.y - a.y)) > 1:
                return "no adjacent agent to give to"
            if a.food <= 0:
                return "no food to give"
            a.food -= 1
            o.food += 1
            self._bond(o, a, 10)
            self._bond(a, o, 3)
            o.heard.append(f"{a.name} gave you one food.")
            self._event(tick, a, f"gave food to {o.name}")
            return f"gave food to {o.name}"
        if kind == "plant":
            if a.seeds <= 0:
                return "no seeds to plant"
            spots = [DIRS[act["direction"]]] if act["direction"] in DIRS else list(DIRS.values())
            for dx, dy in spots:
                x, y = a.x + dx, a.y + dy
                if not self._occupied(x, y) and w.plant(x, y):
                    a.seeds -= 1
                    self._event(tick, a, f"planted a seed at ({x}, {y})")
                    return f"planted a seed at ({x}, {y}); it needs tending to ripen"
            return "nowhere to plant: needs an empty, adjacent grass tile"
        if kind == "tend":
            near = w.plants_near(a.x, a.y, 1)
            if not near:
                return "no young plants within reach"
            x, y = near[0]
            growth, partners = w.tend(x, y, a.name, tick)
            ripe = growth >= GROW_NEEDED
            if partners:
                for n in partners:
                    if n in self.agents:
                        self._bond(a, self.agents[n], 1)
                        self._bond(self.agents[n], a, 1)
                self._event(tick, a, f"and {', '.join(partners)} worked together on the plant at ({x}, {y})")
            if ripe:
                self._event(tick, a, f"the plant at ({x}, {y}) is ripe!")
            return (f"tended the plant at ({x}, {y}): growth {min(growth, GROW_NEEDED):.0f}/{GROW_NEEDED:.0f}"
                    + (f" - teamwork with {', '.join(partners)} doubled the effect!" if partners else "")
                    + (" It is now ripe!" if ripe else ""))
        if kind == "court":
            o = self.agents.get(act["to"])
            if not o or o is a or max(abs(o.x - a.x), abs(o.y - a.y)) > 3:
                return "nobody by that name close enough to court"
            self._bond(o, a, 8 * (0.5 + o.traits.agreeableness))
            self._bond(a, o, 3)
            a.heart_tick = o.heart_tick = tick
            o.heard.append(f'{a.name} is courting you' + (f': "{act["message"]}"' if act["message"] else "."))
            self._event(tick, a, f"is courting {o.name}" + (f': "{act["message"]}"' if act["message"] else ""), heart=True)
            return f"courted {o.name} (their feelings toward you: {int(o.bonds.get(a.name, 0))})"
        if kind == "procreate":
            return self._procreate(a, act, tick)
        if kind == "invent":
            if not act["title"] and not act["message"]:
                return "had no idea to share"
            idea = {"tick": tick, "by": a.name, "color": a.color, "title": act["title"] or "Untitled",
                    "text": act["message"] or act["title"]}
            self.inventions.append(idea)
            self._event(tick, a, f'invented "{idea["title"]}": {idea["text"]}', idea=True)
            return f'invented "{idea["title"]}"'
        return "waited"

    def _procreate(self, a: Agent, act: dict, tick: int) -> str:
        b = self.agents.get(act["to"])
        if not b or b is a:
            return "no such partner"
        if len(self.agents) >= self.max_agents:
            return "the world is at its population limit"
        if max(abs(b.x - a.x), abs(b.y - a.y)) > 2:
            return f"{b.name} is too far away"
        if a.related(b):
            return f"{b.name} is close family"
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
            return f"not enough mutual love (need {LOVE_BOND} each; yours {int(a.bonds.get(b.name, 0))}, theirs {int(b.bonds.get(a.name, 0))})"
        if not (b.pending and b.pending[0] == a.name and tick - b.pending[1] <= 3):
            a.pending = (b.name, tick)
            b.heard.append(f"{a.name} wants to have a child with you. Choose procreate with to={a.name} to agree.")
            a.heart_tick = tick
            return f"asked {b.name} to have a child; waiting for their consent"
        spot = next(((a.x + dx, a.y + dy) for dx, dy in list(DIRS.values()) + [(1, 1), (-1, -1), (1, -1), (-1, 1)]
                     if self.world.walkable(a.x + dx, a.y + dy) and not self._occupied(a.x + dx, a.y + dy)), None) \
            or next(((b.x + dx, b.y + dy) for dx, dy in DIRS.values()
                     if self.world.walkable(b.x + dx, b.y + dy) and not self._occupied(b.x + dx, b.y + dy)), None)
        if not spot:
            return "no room for a baby"
        for p in (a, b):
            p.food -= CHILD_FOOD_COST
            p.last_child_tick = tick
            p.pending = None
        baby = self._make_baby(a, b, spot, act["baby_name"], tick)
        a.children.append(baby.name)
        b.children.append(baby.name)
        a.heart_tick = b.heart_tick = tick
        self._event(tick, a, f"and {b.name} had a baby: {baby.name}!", heart=True)
        for o in self.agents.values():
            if o is not baby:
                o.heard.append(f"{a.name} and {b.name} had a baby named {baby.name}.")
        return f"had a baby with {b.name}: {baby.name}"

    def _make_baby(self, a: Agent, b: Agent, spot, name: str, tick: int) -> Agent:
        name = re.sub(r"[^A-Za-z]", "", name)[:12].capitalize()
        taken = set(self.agents) | set(self.dead)
        if not name or name in taken:
            free = [n for n in BABY_NAMES if n not in taken]
            name = self.rng.choice(free) if free else f"Baby{len(taken)}"
        mix = lambda x, y: min(1.0, max(0.0, (x + y) / 2 + self.rng.gauss(0, 0.1)))
        traits = Traits(**{k: mix(getattr(a.traits, k), getattr(b.traits, k)) for k in vars(a.traits)})
        baby = Agent(name, "Child", "Grow up, learn from your parents and find your own place in society.",
                     traits, skills=(a.skills[:1] + b.skills[:1]), model=HAIKU, color=_mix(a.color, b.color),
                     x=spot[0], y=spot[1], hunger=10.0, born=tick, parents=[a.name, b.name],
                     bonds={a.name: 60.0, b.name: 60.0})
        baby.symbol = self._symbol_for(name)
        baby.heard.append(f"You were just born to {a.name} and {b.name}.")
        self.agents[name] = baby
        return baby

    # ---- human controls ----
    def human_say(self, targets, message: str) -> list[str]:
        """The human speaks to agents (anywhere in the world); they hear it on their next turn."""
        message = message.strip()
        with self.lock:
            chosen = list(self.agents.values()) if targets in ("all", None) else \
                [self.agents[n] for n in targets if n in self.agents]
            if not message or not chosen:
                return []
            everyone = len(chosen) == len(self.agents)
            for a in chosen:
                a.heard.append(f'The Human says{" to everyone" if everyone else " to you"}: "{message}"')
            to = "everyone" if everyone else ", ".join(a.name for a in chosen)
            self.events.append({"tick": self.tick, "agent": "You", "text": f'to {to}: "{message}"',
                                "color": "#ffffff", "human": True})
            return [a.name for a in chosen]

    def set_tier(self, name: str, tier: str) -> str | None:
        """haiku (cheap) -> sonnet (upgrade) -> opus ('enlighten': only one agent at a time)."""
        with self.lock:
            a = self.agents.get(name)
            if not a or tier not in TIERS:
                return None
            if tier == "opus":
                for o in self.agents.values():
                    if o is not a and o.model == OPUS:
                        o.model = SONNET
                        o.heard.append("The enlightenment has passed to someone else; you are now at the Sonnet level.")
            a.model = TIERS[tier]
            if tier == "opus":
                a.heard.append("You have been ENLIGHTENED: your mind is now sharper than anyone else's.")
            self._event(self.tick, a, {"haiku": "was set to the Haiku tier", "sonnet": "was upgraded to Sonnet",
                                       "opus": "was ENLIGHTENED (Opus)"}[tier], tier=True)
            return a.model

    def run(self, ticks: int):
        for _ in range(ticks):
            self.step()
            for a in self.agents.values():
                if not a.history:
                    continue
                h = a.history[-1]
                print(f"[{h['tick']}] {a.name:6} {h['action']:9} {h['result']}  | {h['thought']}")

    # ---- views for the hub ----
    @staticmethod
    def _tier(model):
        return "opus" if model == OPUS else "sonnet" if model == SONNET else "haiku"

    def _agent_view(self, a: Agent, alive=True) -> dict:
        t = self.tick
        return {
            "name": a.name, "role": a.role, "goal": a.goal, "color": a.color, "symbol": a.symbol,
            "model": a.model, "tier": self._tier(a.model), "x": a.x, "y": a.y, "hunger": int(a.hunger),
            "health": int(a.health), "food": a.food, "seeds": a.seeds, "skills": a.skills,
            "traits": vars(a.traits), "age": a.age(t) if a.born > -999 else None, "adult": a.adult(t),
            "parents": a.parents, "children": a.children, "memory": a.memory[-10:],
            "bonds": {k: int(v) for k, v in sorted(a.bonds.items(), key=lambda kv: -kv[1]) if v >= 1},
            "heart": t - a.heart_tick <= 3,
            "say": a.last_say if t - a.last_say_tick <= 3 else "",
            "latest": a.history[-1] if a.history else None, "alive": alive,
        }

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "tick": self.tick,
                "agents": [self._agent_view(a) for a in self.agents.values()],
                "dead": [{**self._agent_view(d["agent"], False), "died": d["tick"], "cause": d["cause"]}
                         for d in self.dead.values()],
                "events": self.events[-60:],
                "inventions": self.inventions[-30:],
                "usage": self.llm.usage(),
                "limits": {"max_agents": self.max_agents, "adult_age": ADULT_AGE, "love": LOVE_BOND},
            }

    def world_data(self) -> dict:
        return {"width": self.world.width, "height": self.world.height, "tiles": self.world.tiles}

    def tiles_now(self) -> list[list[str]]:
        with self.lock:
            return [row[:] for row in self.world.tiles]

    def history(self, name: str) -> list[dict]:
        with self.lock:
            a = self.agents.get(name) or (self.dead.get(name) or {}).get("agent")
            return list(a.history) if a else []

    def save_log(self, path: str):
        with self.lock:
            allagents = {**{n: d["agent"] for n, d in self.dead.items()}, **self.agents}
            Path(path).write_text(json.dumps({"agents": {n: a.history for n, a in allagents.items()},
                                              "inventions": self.inventions}, indent=2))
