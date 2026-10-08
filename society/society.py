import json
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .agent import DIRS, HEARING_RADIUS, Agent, Traits
from .world import World

PALETTE = ["#ff6b6b", "#ffd93d", "#6bcB77", "#4d96ff", "#c77dff", "#ff9f45", "#2ec4b6", "#f15bb5"]
HUNGER_PER_TICK = 1.5
EAT_RELIEF = 40


def default_agents() -> list[Agent]:
    return [
        Agent("Ada", "Leader", "Organise the group and keep everyone working toward a shared plan.",
              Traits(0.6, 0.8, 0.9, 0.6, 0.2), ["planning", "persuasion"]),
        Agent("Brix", "Builder", "Stay near the group's food and keep it well supplied.",
              Traits(0.4, 0.9, 0.4, 0.5, 0.3), ["construction", "engineering"]),
        Agent("Cleo", "Explorer", "Discover new areas of the map and report what you find.",
              Traits(0.95, 0.3, 0.7, 0.6, 0.4), ["scouting", "mapping"]),
        Agent("Dov", "Trader", "Accumulate food through deals; trade for advantage.",
              Traits(0.5, 0.6, 0.7, 0.2, 0.5), ["negotiation", "accounting"]),
        Agent("Eli", "Skeptic", "Question plans, find flaws, and protect the group from bad decisions.",
              Traits(0.7, 0.7, 0.3, 0.2, 0.7), ["critical thinking", "history"]),
        Agent("Fenn", "Mediator", "Resolve conflicts, find common ground, and steer the group toward long-term wellbeing.",
              Traits(0.85, 0.7, 0.5, 0.9, 0.2), ["diplomacy", "ethics", "synthesis"],
              model="claude-opus-5-5"),
    ]


def load_agents(path: str) -> list[Agent]:
    """Load agents from a JSON list of {name, role, goal, traits{...}, skills[], model}."""
    out = []
    for d in json.loads(Path(path).read_text()):
        d["traits"] = Traits(**d.get("traits", {}))
        out.append(Agent(**d))
    return out


class Society:
    def __init__(self, agents: list[Agent], llm, world: World | None = None, seed: int | None = None):
        self.rng = random.Random(seed)
        self.world = world or World(seed=seed)
        self.agents = {a.name: a for a in agents}
        self.llm = llm
        self.tick = 0
        self.events: list[dict] = []
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

    # ---- simulation ----
    def step(self):
        with self.lock:
            self.tick += 1
            tick = self.tick
            agents = list(self.agents.values())
            names = list(self.agents)
            jobs = [(a, a.observe(self.world, agents, tick), [n for n in names if n != a.name]) for a in agents]
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
                agent.hunger = min(100.0, agent.hunger + HUNGER_PER_TICK)
                result = self._apply(agent, act, tick)
                agent.history.append({"tick": tick, "x": agent.x, "y": agent.y, "hunger": int(agent.hunger),
                                      "thought": act["thought"], "action": act["action"], "result": result,
                                      "heard": heard_by[agent.name]})

    def _event(self, tick, agent, text):
        self.events.append({"tick": tick, "agent": agent.name, "text": text, "color": agent.color})
        del self.events[:-200]

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
            if any(o is not a and (o.x, o.y) == (nx, ny) for o in self.agents.values()):
                return "blocked: another agent"
            a.x, a.y = nx, ny
            return f"moved {act['direction']} to ({nx}, {ny})"
        if kind == "gather":
            for fx, fy in w.food_near(a.x, a.y, 1):
                if w.take_food(fx, fy, tick):
                    a.food += 1
                    self._event(tick, a, f"gathered food at ({fx}, {fy})")
                    return f"gathered food at ({fx}, {fy})"
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
            o.heard.append(f"{a.name} gave you one food.")
            self._event(tick, a, f"gave food to {o.name}")
            return f"gave food to {o.name}"
        return "waited"

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

    def run(self, ticks: int):
        for _ in range(ticks):
            self.step()
            for a in self.agents.values():
                h = a.history[-1]
                print(f"[{h['tick']}] {a.name:5} {h['action']:6} {h['result']}  | {h['thought']}")

    # ---- views for the hub ----
    def snapshot(self) -> dict:
        with self.lock:
            return {
                "tick": self.tick,
                "agents": [{
                    "name": a.name, "role": a.role, "goal": a.goal, "color": a.color, "model": a.model,
                    "x": a.x, "y": a.y, "hunger": int(a.hunger), "food": a.food, "skills": a.skills,
                    "traits": vars(a.traits), "say": a.last_say if self.tick - a.last_say_tick <= 3 else "",
                    "latest": a.history[-1] if a.history else None,
                } for a in self.agents.values()],
                "events": self.events[-60:],
                "usage": self.llm.usage(),
            }

    def world_data(self) -> dict:
        return {"width": self.world.width, "height": self.world.height, "tiles": self.world.tiles}

    def tiles_now(self) -> list[list[str]]:
        with self.lock:
            return [row[:] for row in self.world.tiles]

    def history(self, name: str) -> list[dict]:
        with self.lock:
            return list(self.agents[name].history) if name in self.agents else []

    def save_log(self, path: str):
        with self.lock:
            Path(path).write_text(json.dumps({n: a.history for n, a in self.agents.items()}, indent=2))
