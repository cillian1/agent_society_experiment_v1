"""The simulation: runs days, applies life (hunger, ageing, death), lets the Human interact, records statistics."""
import json
import random
import re
import string
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import actions, mind
from .config import (BOND_DECAY, DEFAULT_MAX_AGENTS, HAIKU, HUNGER_PER_DAY, LOCAL, MAX_EVENTS, MAX_IDEAS_IN_PROMPT,
                     MAX_STATS_POINTS, OLD_AGE, OLD_AGE_DEATH_CHANCE, OPUS, SONNET, STARVE_DAMAGE, TIERS, VIEW_RADIUS)
from .models import Agent, Traits
from .world import World

PALETTE = ["#ff6b6b", "#ffd93d", "#6bcB77", "#4d96ff", "#c77dff", "#ff9f45", "#2ec4b6", "#f15bb5"]
BABY_NAMES = ["Nova", "Pip", "Juno", "Kit", "Rue", "Sol", "Tove", "Wren", "Zed", "Lark", "Moss", "Ember",
              "Fig", "Sage", "Briar", "Onyx", "Dale", "Ivy", "Rook", "Tansy"]


def default_agents() -> list[Agent]:
    """Six settlers with nothing but a personality: no roles, no goals beyond surviving, no family.
    Two start on Haiku (the 'main characters'), the rest on a free local model."""
    return [
        Agent("Ada", Traits(0.6, 0.8, 0.9, 0.6, 0.2), model=HAIKU),
        Agent("Brix", Traits(0.4, 0.9, 0.4, 0.5, 0.3), model=LOCAL),
        Agent("Cleo", Traits(0.95, 0.3, 0.7, 0.6, 0.4), model=LOCAL),
        Agent("Dov", Traits(0.5, 0.6, 0.7, 0.2, 0.5), model=LOCAL),
        Agent("Eli", Traits(0.7, 0.7, 0.3, 0.2, 0.7), model=LOCAL),
        Agent("Fenn", Traits(0.85, 0.7, 0.5, 0.9, 0.2), model=HAIKU),
    ]


def load_agents(path: str) -> list[Agent]:
    """Agents from a JSON list of {name, traits{...}, goal?, role?, model?}."""
    return [Agent.from_dict(d) for d in json.loads(Path(path).read_text())]


def tier_of(model: str | None) -> str:
    if model in (None, LOCAL) or model.startswith("local:"):
        return "local"
    return {OPUS: "opus", SONNET: "sonnet", HAIKU: "haiku"}.get(model, "custom")


def _mix(c1: str, c2: str) -> str:
    a, b = (tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (c1, c2))
    return "#" + "".join(f"{(x + y) // 2:02x}" for x, y in zip(a, b))


class Society:
    def __init__(self, agents: list[Agent], llm, world: World | None = None, seed: int | None = None,
                 max_agents: int = DEFAULT_MAX_AGENTS, baby_model: str = LOCAL, spawn: bool = True):
        self.seed = seed
        self.rng = random.Random(seed)
        self.world = world or World(seed=seed)
        self.agents: dict[str, Agent] = {a.name: a for a in agents}
        self.dead: dict[str, dict] = {}            # name -> {"agent", "tick", "cause"}
        self.llm = llm
        self.max_agents = max_agents
        self.baby_model = baby_model
        self.human_authority = "leader"            # leader | advisor | observer
        self.tick = 0
        self.tick_seconds = 0.0
        self.events: list[dict] = []
        self.inventions: list[dict] = []
        self.chat: list[dict] = []                 # the Human <-> agents
        self.talk: list[dict] = []                 # agents <-> agents
        self.errors: list[dict] = []
        self.stats: list[dict] = []
        self.lock = threading.RLock()
        if spawn:
            self._spawn()
            self._record_stats()

    # ================================================================ setup
    def _spawn(self):
        cx, cy = self.world.width // 2, self.world.height // 2
        spots = sorted(((x, y) for y in range(self.world.height) for x in range(self.world.width)
                        if self.world.walkable(x, y)),
                       key=lambda p: abs(p[0] - cx) + abs(p[1] - cy) + self.rng.random() * 14)
        for i, (a, (x, y)) in enumerate(zip(self.agents.values(), spots)):
            a.x, a.y = x, y
            if a.color == "#ffffff":
                a.color = PALETTE[i % len(PALETTE)]
            a.symbol = self._symbol_for(a.name)
            if a.born == -999:
                a.born = -self.rng.randint(60, 140)    # settlers start as adults of varied age
            self.world.reveal(a.x, a.y, VIEW_RADIUS)

    def _symbol_for(self, name: str) -> str:
        used = {a.symbol for a in self.agents.values()} | {d["agent"].symbol for d in self.dead.values()}
        for ch in name.upper() + string.ascii_uppercase:
            if ch.isalpha() and ch not in used:
                return ch
        return "?"

    # ================================================================ one day
    # A day has four parts. step() runs them in lockstep (headless runs, tests); the hub's scheduler runs
    # them asynchronously so a slow brain never holds up everyone else (see hub/server.py).
    def begin_day(self) -> int:
        """Advance the clock: the world grows, everyone gets hungrier and older (some may die)."""
        with self.lock:
            self.tick += 1
            self.world.update(self.tick)
            for a in list(self.agents.values()):
                a.authority = self.human_authority
                self._live_a_day(a, self.tick)
            return self.tick

    def prepare(self, a: Agent) -> dict | None:
        """What the agent perceives right now (consumes the messages it has heard)."""
        with self.lock:
            if a.name not in self.agents:
                return None
            agents = list(self.agents.values())
            job = {"prompt": mind.observation(a, self.world, agents, self.tick, self._ideas()),
                   "others": [o.name for o in agents if o is not a], "heard": a.heard}
            a.heard = []
            return job

    def think(self, a: Agent, job: dict) -> dict:
        """Ask the agent's brain (no lock held; runs in parallel with everyone else)."""
        try:
            act = mind.decide(a, self.llm, job["prompt"], job["others"])
        except Exception as e:                        # one broken brain must not stop everyone else
            self._error(a, e)
            act = mind.failed_action(e)
        if a.needs_compaction():
            try:
                mind.compact_memory(a, self.llm, self._summary_model())
            except Exception as e:
                self._error(a, e, "memory summary failed")
        return act

    def apply_decision(self, a: Agent, act: dict, job: dict):
        with self.lock:
            if a.name in self.agents:
                self._act(a, act, self.tick, job["heard"])

    def end_day(self, seconds: float):
        with self.lock:
            self.tick_seconds = round(seconds, 1)
            self._record_stats()

    def step(self):
        """One whole day in lockstep: everyone thinks, then everyone acts (in random order)."""
        if not self.agents:
            return
        t0 = time.time()
        self.begin_day()
        agents = list(self.agents.values())
        jobs = [(a, self.prepare(a)) for a in agents]
        jobs = [(a, j) for a, j in jobs if j]
        with ThreadPoolExecutor(max_workers=max(1, len(jobs))) as pool:
            acts = list(pool.map(lambda aj: self.think(*aj), jobs))
        order = list(zip(jobs, acts))
        self.rng.shuffle(order)
        for (a, job), act in order:
            self.apply_decision(a, act, job)
        self.end_day(time.time() - t0)

    def _live_a_day(self, a: Agent, tick: int) -> bool:
        """Hunger, health, fading feelings, old age. False if the agent died."""
        a.hunger = min(100.0, a.hunger + HUNGER_PER_DAY)
        for k in list(a.bonds):
            a.bonds[k] *= BOND_DECAY
            if a.bonds[k] < 1:
                del a.bonds[k]
        if a.hunger >= 100:
            a.health -= STARVE_DAMAGE
        elif a.hunger < 50:
            a.health = min(100.0, a.health + 1)
        if a.health <= 0:
            self.die(a, tick, "starvation")
            return False
        if a.age(tick) >= OLD_AGE and self.rng.random() < OLD_AGE_DEATH_CHANCE:
            self.die(a, tick, "old age")
            return False
        return True

    def _act(self, a: Agent, act: dict, tick: int, heard: list[str]):
        result = actions.apply(self, a, act, tick)
        if act["role"] and act["role"][:40] != a.role:
            a.role = act["role"][:40]
            self.event(tick, a, f'took on a new role: "{a.role}"', "role")
            a.remember(tick, f'I decided my role is "{a.role}".')
        if act["remember"]:
            a.remember(tick, "(note to self) " + act["remember"][:200])
        a.history.append({"tick": tick, "x": a.x, "y": a.y, "hunger": int(a.hunger), "thought": act["thought"],
                          "action": act["action"], "result": result, "heard": heard})

    def run(self, days: int):
        """Headless: print every agent's day."""
        for _ in range(days):
            self.step()
            for a in self.agents.values():
                if a.history:
                    h = a.history[-1]
                    print(f"[{h['tick']}] {a.name:6} {h['action']:9} {h['result']}  | {h['thought']}")

    # ================================================================ helpers used by actions
    def event(self, tick: int, a: Agent, text: str, kind: str = "misc"):
        self.events.append({"tick": tick, "agent": a.name, "text": text, "color": a.color, "kind": kind})
        del self.events[:-MAX_EVENTS]

    def bond(self, a: Agent, b: Agent, amount: float):
        """Raise a's feeling toward b."""
        a.bonds[b.name] = min(100.0, a.bonds.get(b.name, 0) + amount)

    def occupied(self, x: int, y: int, ignore: Agent | None = None) -> bool:
        return any(o is not ignore and (o.x, o.y) == (x, y) for o in self.agents.values())

    def free_spot_near(self, a: Agent):
        for dx, dy in [(0, -1), (0, 1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)]:
            x, y = a.x + dx, a.y + dy
            if self.world.walkable(x, y) and not self.occupied(x, y):
                return x, y
        return None

    def explore(self, a: Agent, tick: int):
        """Reveal the map around an agent; enough new land becomes a memory and an event."""
        new = self.world.reveal(a.x, a.y, VIEW_RADIUS)
        a.discoveries += new["tiles"]
        for k, v in new.items():
            a.unreported[k] = a.unreported.get(k, 0) + v
        if a.unreported.get("tiles", 0) >= 45:
            u, a.unreported = a.unreported, {}
            found = ", ".join(f"{u[k]} {k}" for k in ("water", "tree", "food", "rock") if u.get(k, 0) >= 3) or "open grassland"
            pct = self.world.explored_pct()
            a.remember(tick, f"I explored new land around ({a.x}, {a.y}): {found}. We have explored {pct}% of the world.")
            self.event(tick, a, f"explored new land near ({a.x}, {a.y}): {found} - {pct}% of the world known", "explore")

    def make_baby(self, a: Agent, b: Agent, spot, name: str, tick: int) -> Agent:
        taken = set(self.agents) | set(self.dead)
        if not name or name in taken:
            free = [n for n in BABY_NAMES if n not in taken]
            name = self.rng.choice(free) if free else f"Baby{len(taken)}"
        mix = lambda x, y: min(1.0, max(0.0, (x + y) / 2 + self.rng.gauss(0, 0.1)))
        traits = Traits(**{k: mix(getattr(a.traits, k), getattr(b.traits, k)) for k in vars(a.traits)})
        baby = Agent(name, traits, model=self.baby_model, color=_mix(a.color, b.color), x=spot[0], y=spot[1],
                     hunger=10.0, born=tick, parents=[a.name, b.name], bonds={a.name: 60.0, b.name: 60.0},
                     authority=self.human_authority)
        baby.symbol = self._symbol_for(name)
        baby.heard.append(f"You were just born to {a.name} and {b.name}.")
        baby.remember(tick, f"I was born to {a.name} and {b.name}.")
        self.agents[name] = baby
        for p in (a, b):
            p.children.append(name)
        a.heart_tick = b.heart_tick = tick
        for o in self.agents.values():
            if o is baby:
                continue
            o.heard.append(f"{a.name} and {b.name} had a baby named {name}.")
            o.remember(tick, f"{a.name} and {b.name} had a baby, {name}." if o not in (a, b)
                       else f"{b.name if o is a else a.name} and I had a baby, {name}!")
        self.event(tick, a, f"and {b.name} had a baby: {name}!", "birth")
        return baby

    def die(self, a: Agent, tick: int, cause: str):
        self.dead[a.name] = {"agent": a, "tick": tick, "cause": cause}
        del self.agents[a.name]
        a.history.append({"tick": tick, "x": a.x, "y": a.y, "hunger": int(a.hunger), "thought": "(died)",
                          "action": "died", "result": cause, "heard": []})
        self.event(tick, a, f"died of {cause} at age {a.age(tick)}", "death")
        for o in self.agents.values():
            o.heard.append(f"{a.name} has died ({cause}).")
            o.remember(tick, f"{a.name} died of {cause}" + (" - my own child." if a.name in o.children else "."))

    def _ideas(self) -> list[str]:
        return [f"{i['title']} (by {i['by']}): {i['text']}" for i in self.inventions[-MAX_IDEAS_IN_PROMPT:]]

    def _summary_model(self):
        """Memory summaries use Haiku when a Claude key exists (cheap, better), else the local model."""
        info = self.llm.info() if hasattr(self.llm, "info") else {}
        return HAIKU if info.get("claude") else (LOCAL if info.get("local") else None)

    def _error(self, a: Agent, e: Exception, what: str = "brain error"):
        with self.lock:
            self.errors.append({"tick": self.tick, "agent": a.name, "model": a.model or "default", "error": f"{what}: {e}"[:300]})
            del self.errors[:-30]
        print(f"[{a.name} / {a.model}] {what}: {e}")

    def _record_stats(self):
        alive = list(self.agents.values())
        n = len(alive) or 1
        self.stats.append({
            "day": self.tick, "population": len(alive), "deaths": len(self.dead),
            "hunger": round(sum(a.hunger for a in alive) / n, 1), "food": sum(a.food for a in alive),
            "explored": self.world.explored_pct(), "structures": len(self.world.structures),
            "objects": sum(len(a.items) for a in alive), "ideas": len(self.inventions),
            "farms": sum(t in ("sprout", "crop") for row in self.world.tiles for t in row),
        })
        if len(self.stats) > MAX_STATS_POINTS:             # keep history bounded: halve resolution of the old half
            half = len(self.stats) // 2
            self.stats = self.stats[:half:2] + self.stats[half:]

    # ================================================================ the Human
    def human_say(self, targets, message: str) -> list[str]:
        """The Human talks to agents anywhere in the world; each answers right away in the chat."""
        message = message.strip()[:600]
        with self.lock:
            chosen = list(self.agents.values()) if targets in ("all", None) else \
                [self.agents[n] for n in targets if n in self.agents]
            if not message or not chosen:
                return []
            names = [a.name for a in chosen]
            to = "everyone" if len(chosen) == len(self.agents) else ", ".join(names)
            self.chat.append({"from": "You", "to": to, "text": message, "tick": self.tick})
            slots = []
            for a in chosen:
                a.authority = self.human_authority
                if a.authority != "observer":
                    a.orders.append([self.tick, message[:300]])
                    del a.orders[:-5]
                slot = {"from": a.name, "text": "", "pending": True, "tick": self.tick, "color": a.color}
                self.chat.append(slot)
                slots.append((a, slot))
            del self.chat[:-150]
            ideas, alive = self._ideas(), list(self.agents.values())
            for a, slot in slots:
                situation = mind.observation(a, self.world, alive, self.tick, ideas)
                others = [n for n in self.agents if n != a.name]
                threading.Thread(target=self._reply, daemon=True,
                                 args=(a, slot, situation, message, others, [n for n in names if n != a.name])).start()
            return names

    def _reply(self, a: Agent, slot: dict, situation: str, message: str, others: list[str], also_to: list[str]):
        try:
            out, err = mind.reply(a, self.llm, situation, message, others, also_to), None
            text = out["message"] or "..."
        except Exception as e:                       # tell the Human instead of failing silently
            out, text, err = {"thought": ""}, f"(couldn't answer: {e})", e
        with self.lock:
            slot["text"], slot["pending"] = text, False
            if err is None:
                a.chat += [["Human", message], ["You", text]]
                del a.chat[:-16]
                a.last_say, a.last_say_to, a.last_say_tick = text, "Human", self.tick
                a.remember(self.tick, f'The Human said to me: "{message}" and I answered: "{text}"')
            verb = {"leader": "(your leader) ORDERED you", "advisor": "advised you", "observer": "said to you"}[a.authority]
            a.heard.append(f'The Human {verb}: "{message}"' + (f' - you replied: "{text}"' if err is None else "")
                           + (" - now carry it out." if a.authority == "leader" else ""))
            a.history.append({"tick": self.tick, "x": a.x, "y": a.y, "hunger": int(a.hunger), "thought": out.get("thought", ""),
                              "action": "reply to Human", "result": text, "heard": [f'The Human says: "{message}"']})

    def gift(self, name: str, what: str) -> str | None:
        """The Human drops a gift from the sky: food, seeds or materials."""
        amounts = {"food": ("food", 3), "seeds": ("seeds", 3), "wood": ("wood", 3), "stone": ("stone", 3)}
        with self.lock:
            a = self.agents.get(name)
            if not a or what not in amounts:
                return None
            attr, n = amounts[what]
            setattr(a, attr, getattr(a, attr) + n)
            a.heard.append(f"A gift from the Human appeared in your hands: {n} {attr}.")
            a.remember(self.tick, f"The Human gave me {n} {attr}.")
            self.event(self.tick, a, f"received {n} {attr} from the Human", "gift")
            return f"{n} {attr}"

    def set_model(self, name: str, spec: str) -> str | None:
        """Any brain: local / haiku / sonnet / opus, or any model id ('local:<name>' for another local model).
        Opus ('enlighten') is limited to one agent at a time; the previous one drops to Sonnet."""
        spec = (spec or "").strip()
        model = TIERS.get(spec.lower(), spec)
        if not model or len(model) > 80 or not re.fullmatch(r"[\w.:\-/]+", model):
            return None
        with self.lock:
            a = self.agents.get(name)
            if not a:
                return None
            if model == OPUS:
                for o in self.agents.values():
                    if o is not a and o.model == OPUS:
                        o.model = SONNET
                        o.heard.append("The enlightenment has passed to someone else; you are now at the Sonnet level.")
                a.heard.append("You have been ENLIGHTENED: your mind is now sharper than anyone else's.")
            a.model = model
            label = {"local": "now thinks with the free local model", "haiku": "now thinks with Haiku",
                     "sonnet": "was upgraded to Sonnet", "opus": "was ENLIGHTENED (Opus)"}
            self.event(self.tick, a, label.get(tier_of(model), f"now thinks with {model}"), "brain")
            return model

    # ================================================================ saving
    def to_dict(self) -> dict:
        with self.lock:
            return {
                "version": 2, "seed": self.seed, "tick": self.tick, "max_agents": self.max_agents,
                "baby_model": self.baby_model, "human_authority": self.human_authority,
                "world": self.world.to_dict(),
                "agents": [a.to_dict() for a in self.agents.values()],
                "dead": [{"agent": d["agent"].to_dict(), "tick": d["tick"], "cause": d["cause"]} for d in self.dead.values()],
                "events": self.events, "inventions": self.inventions, "talk": self.talk, "stats": self.stats,
                "chat": [c for c in self.chat if not c.get("pending")],
            }

    @classmethod
    def from_dict(cls, d: dict, llm) -> "Society":
        s = cls([Agent.from_dict(a) for a in d["agents"]], llm, World.from_dict(d["world"]), d.get("seed"),
                d.get("max_agents", DEFAULT_MAX_AGENTS), d.get("baby_model", LOCAL), spawn=False)
        s.tick, s.human_authority = d["tick"], d.get("human_authority", "leader")
        s.dead = {x["agent"]["name"]: {"agent": Agent.from_dict(x["agent"]), "tick": x["tick"], "cause": x["cause"]}
                  for x in d.get("dead", [])}
        for k in ("events", "inventions", "talk", "stats", "chat"):
            setattr(s, k, d.get(k, []))
        return s
