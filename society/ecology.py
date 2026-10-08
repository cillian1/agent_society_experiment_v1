"""A living world: animals that roam, flee, breed and die back in winter; soil that tires when farmed too hard;
spring floods and summer wildfires. The world pushes back, so people have to adapt."""
import random

from . import clock

# kind: food when hunted, how fast it breeds, can it be tamed (and then gives food every day), fights back
ANIMALS = {
    "deer": {"food": 5, "breed": 0.10, "tame": False, "milk": 0, "fights": False, "flee": 3},
    "rabbit": {"food": 2, "breed": 0.30, "tame": False, "milk": 0, "fights": False, "flee": 2},
    "boar": {"food": 4, "breed": 0.10, "tame": False, "milk": 0, "fights": True, "flee": 1},
    "goat": {"food": 3, "breed": 0.12, "tame": True, "milk": 1, "fights": False, "flee": 2},
    "sheep": {"food": 3, "breed": 0.12, "tame": True, "milk": 1, "fights": False, "flee": 1},
}
PER_TILES = 160            # one wild animal per this many tiles at the start
CAP_FACTOR = 1.6           # wild population cap = start population x this
GROUND = ("grass", "sand", "food")
SOIL_TIRE = 0.22           # fertility lost by every harvest of a crop
SOIL_REST = 0.03           # fertility regained per day by soil that isn't farmed (0.01 if it is)
FLOOD_CHANCE = 0.08        # per spring day
FIRE_CHANCE = 0.04         # per summer day
FIRE_SPREAD = 0.3          # per burning tree per hour, to each neighbouring tree
FIRE_HOURS = 3             # a tree burns this long


class Ecology:
    def __init__(self, world, seed=None, fresh=True):
        self.world, self.rng = world, random.Random(seed)
        self.animals: dict[int, dict] = {}
        self.next_id = 1
        self.fertility: dict[tuple[int, int], float] = {}     # only tiles that aren't at full fertility
        self.burning: dict[tuple[int, int], int] = {}          # tree tile -> hour it burns out
        self.floods: list[dict] = []                           # recent floods (for the map): {x, y, r, tick}
        self.start_pop = 0
        if fresh:
            self._populate()

    # ---- animals ----
    def _spot(self, near=None, radius=6):
        w = self.world
        for _ in range(200):
            if near:
                x, y = near[0] + self.rng.randint(-radius, radius), near[1] + self.rng.randint(-radius, radius)
            else:
                x, y = self.rng.randrange(w.width), self.rng.randrange(w.height)
            if w.in_bounds(x, y) and w.tiles[y][x] in GROUND and (x, y) not in w.structures:
                return x, y
        return None

    def spawn(self, kind, near=None):
        p = self._spot(near)
        if not p:
            return None
        a = {"id": self.next_id, "kind": kind, "x": p[0], "y": p[1], "owner": None, "born": 0}
        self.animals[self.next_id] = a
        self.next_id += 1
        return a

    def _populate(self):
        n = max(8, self.world.width * self.world.height // PER_TILES)
        kinds = list(ANIMALS)
        for i in range(n):
            herd = self.spawn(kinds[i % len(kinds)])
            if herd and self.rng.random() < 0.5:                 # animals come in little herds
                self.spawn(herd["kind"], (herd["x"], herd["y"]))
        self.start_pop = len(self.animals)

    def near(self, x, y, reach=1, kind=None, wild=None):
        out = [a for a in self.animals.values() if max(abs(a["x"] - x), abs(a["y"] - y)) <= reach
               and (kind is None or kind in a["kind"]) and (wild is None or (a["owner"] is None) == wild)]
        return sorted(out, key=lambda a: max(abs(a["x"] - x), abs(a["y"] - y)))

    def counts(self) -> dict:
        c = {}
        for a in self.animals.values():
            k = a["kind"] + (" (tame)" if a["owner"] else "")
            c[k] = c.get(k, 0) + 1
        return c

    def remove(self, aid):
        self.animals.pop(aid, None)

    def _step_animal(self, a, people):
        w = self.world
        owner = people.get(a["owner"]) if a["owner"] else None
        if a["owner"] and not owner:                            # its keeper died: it goes wild again
            a["owner"] = None
        if owner:                                               # tame animals stay close to their keeper
            if max(abs(owner.x - a["x"]), abs(owner.y - a["y"])) <= 2 and self.rng.random() < 0.6:
                return
            dx, dy = (owner.x > a["x"]) - (owner.x < a["x"]), (owner.y > a["y"]) - (owner.y < a["y"])
        else:
            threat = next((p for p in people.values()
                           if max(abs(p.x - a["x"]), abs(p.y - a["y"])) <= ANIMALS[a["kind"]]["flee"]), None)
            if threat:                                          # run away from people
                dx, dy = (a["x"] > threat.x) - (a["x"] < threat.x), (a["y"] > threat.y) - (a["y"] < threat.y)
            elif self.rng.random() < 0.35:
                dx, dy = self.rng.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
            else:
                return
        for nx, ny in ((a["x"] + dx, a["y"] + dy), (a["x"] + dx, a["y"]), (a["x"], a["y"] + dy)):
            if (nx, ny) != (a["x"], a["y"]) and w.in_bounds(nx, ny) and w.tiles[ny][nx] in GROUND:
                a["x"], a["y"] = nx, ny
                return

    def _daily(self, tick, season, people, report):
        wild = [a for a in self.animals.values() if not a["owner"]]
        cap = max(8, int(self.start_pop * CAP_FACTOR))
        if season in ("spring", "summer") and len(wild) < cap:
            for a in list(wild):
                mate = any(b is not a and b["kind"] == a["kind"] and abs(b["x"] - a["x"]) + abs(b["y"] - a["y"]) <= 5 for b in wild)
                if mate and self.rng.random() < ANIMALS[a["kind"]]["breed"]:
                    self.spawn(a["kind"], (a["x"], a["y"]))
        tame = [a for a in self.animals.values() if a["owner"]]
        if season in ("spring", "summer"):
            for a in tame:                                      # kept animals breed too
                if self.rng.random() < ANIMALS[a["kind"]]["breed"] / 2 and \
                        sum(b["owner"] == a["owner"] and b["kind"] == a["kind"] for b in tame) >= 2:
                    baby = self.spawn(a["kind"], (a["x"], a["y"]))
                    if baby:
                        baby["owner"] = a["owner"]
        if season == "winter":
            for a in wild:
                if self.rng.random() < 0.03:
                    self.remove(a["id"])
        for kind in ANIMALS:                                    # newcomers wander in if a kind was hunted out
            if sum(a["kind"] == kind for a in self.animals.values()) < 2 and self.rng.random() < 0.1:
                edge = self.rng.choice([(0, self.rng.randrange(self.world.height)), (self.world.width - 1, self.rng.randrange(self.world.height))])
                if self.spawn(kind, edge, 3):
                    report(None, f"a few {kind}s have wandered in from beyond the known land", "nature")
        for pos, f in list(self.fertility.items()):            # tired soil recovers
            farmed = self.world.tiles[pos[1]][pos[0]] in ("sprout", "crop")
            self.fertility[pos] = min(1.0, f + (0.01 if farmed else SOIL_REST))
            if self.fertility[pos] >= 1.0:
                del self.fertility[pos]

    # ---- soil ----
    def soil(self, x, y) -> float:
        return self.fertility.get((x, y), 1.0)

    def tire(self, x, y):
        self.fertility[(x, y)] = max(0.1, self.soil(x, y) - SOIL_TIRE)

    # ---- disasters ----
    def _flood(self, tick, report):
        w = self.world
        shore = [(x, y) for (x, y), p in w.plants.items() if w.water_near(x, y)]
        if not shore:
            return []
        x, y = self.rng.choice(shore)
        hit = []
        for yy in range(y - 3, y + 4):
            for xx in range(x - 3, x + 4):
                if w.in_bounds(xx, yy) and w.tiles[yy][xx] in ("sprout", "crop") and w.water_near(xx, yy):
                    w.tiles[yy][xx] = "grass"
                    w.plants.pop((xx, yy), None)
                    hit.append((xx, yy))
        if hit:
            self.floods.append({"x": x, "y": y, "r": 3, "tick": tick})
            del self.floods[:-5]
            report((x, y), f"the river flooded near ({x}, {y}) and washed away {len(hit)} young crop{'s' if len(hit) > 1 else ''}", "nature")
        return hit

    def _ignite(self, tick, report):
        w = self.world
        trees = [(x, y) for y in range(w.height) for x in range(w.width) if w.tiles[y][x] == "tree"]
        if trees:
            x, y = self.rng.choice(trees)
            self.burning[(x, y)] = tick + FIRE_HOURS
            report((x, y), f"a wildfire broke out in the woods near ({x}, {y})", "nature")

    def _burn(self, tick):
        w = self.world
        for (x, y), out in list(self.burning.items()):
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if w.in_bounds(nx, ny) and w.tiles[ny][nx] == "tree" and (nx, ny) not in self.burning \
                        and self.rng.random() < FIRE_SPREAD:
                    self.burning[(nx, ny)] = tick + FIRE_HOURS
            if tick >= out:
                del self.burning[(x, y)]
                w.tiles[y][x] = "grass"                     # burnt out: open land, regrows slowly
                w.regrow[(x, y)] = (tick + 600, "tree")

    def update(self, tick, people: dict, report):
        """One hour. `report(pos, text, kind)` tells the society about anything notable."""
        season = clock.season(tick)
        for a in list(self.animals.values()):
            self._step_animal(a, people)
        if self.burning:
            self._burn(tick)
        if clock.when(tick)["hour"] == 6:
            self._daily(tick, season, people, report)
            if season == "spring" and self.rng.random() < FLOOD_CHANCE:
                self._flood(tick, report)
            if season == "summer" and self.rng.random() < FIRE_CHANCE:
                self._ignite(tick, report)

    # ---- saving ----
    def to_dict(self) -> dict:
        return {"animals": list(self.animals.values()), "next_id": self.next_id, "start_pop": self.start_pop,
                "fertility": [[x, y, f] for (x, y), f in self.fertility.items()],
                "burning": [[x, y, t] for (x, y), t in self.burning.items()], "floods": self.floods}

    @classmethod
    def from_dict(cls, world, d: dict | None, seed=None) -> "Ecology":
        if not d:
            return cls(world, seed)
        e = cls(world, seed, fresh=False)
        e.animals = {a["id"]: a for a in d.get("animals", [])}
        e.next_id, e.start_pop = d.get("next_id", len(e.animals) + 1), d.get("start_pop", len(e.animals))
        e.fertility = {(x, y): f for x, y, f in d.get("fertility", [])}
        e.burning = {(x, y): t for x, y, t in d.get("burning", [])}
        e.floods = d.get("floods", [])
        return e
