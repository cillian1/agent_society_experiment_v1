"""2D tile world: generation, walkability, resources, farming, structures and the explored map."""
import random

GRASS, WATER, SAND, ROCK, FOOD, SPROUT, CROP = "grass", "water", "sand", "rock", "food", "sprout", "crop"
TREE, STRUCTURE = "tree", "structure"
GLYPH = {GRASS: "g", WATER: "~", SAND: ".", ROCK: "#", FOOD: "f", SPROUT: ",", CROP: "*", TREE: "^", STRUCTURE: "&"}
from .config import (FUNCTIONS, SAME_KIND_RADIUS, FOOD_REGROW_DAYS, GROW_NEEDED, IRRIGATED_GROWTH_PER_DAY, PLANT_GROWTH_PER_DAY, TEAMWORK_WINDOW,
                     TEND_COOLDOWN, TREE_REGROW_DAYS, WORLD_H, WORLD_W)

WALKABLE = (GRASS, SAND, FOOD, SPROUT, CROP)
BLOCK_WORDS = ("wall", "fence", "barrier", "palisade", "barricade")   # everything else can be walked into/over
WATER_OK_WORDS = ("bridge", "dock", "pier", "raft", "path")


def function_of(kind: str):
    k = kind.lower()
    return next((f for f, (words, _) in FUNCTIONS.items() if any(w in k for w in words)), None)


class World:
    def __init__(self, width: int = WORLD_W, height: int = WORLD_H, seed: int | None = None):
        self.width, self.height = width, height
        self.rng = random.Random(seed)
        self.tiles = self._generate()
        self.regrow: dict[tuple[int, int], tuple[int, str]] = {}  # (x, y) -> (tick it returns, tile type)
        self.plants: dict[tuple[int, int], dict] = {}  # (x, y) -> {"growth": float, "tended": {name: tick}}
        self.structures: dict[tuple[int, int], dict] = {}  # (x, y) -> {kind, text, by, tick, walkable, under}
        self.explored: set[tuple[int, int]] = set()    # tiles any agent has seen (the community's shared map)
        self._find_irrigated()

    def _find_irrigated(self):
        wells = [p for p, s in getattr(self, "structures", {}).items() if s.get("function") == "well"]
        self.irrigated = {(x, y) for y in range(self.height) for x in range(self.width)
                          if any(self.in_bounds(x + dx, y + dy) and self.tiles[y + dy][x + dx] == WATER
                                 for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2))}
        self.irrigated |= {(x + dx, y + dy) for x, y in wells for dx in range(-3, 4) for dy in range(-3, 4)}

    def _noise(self, cells=(12, 4), weights=(0.75, 0.25)) -> list[list[float]]:
        """Smooth value noise: bilinear-interpolated coarse grids at two scales."""
        def layer(cell):
            cw, ch = self.width // cell + 2, self.height // cell + 2
            g = [[self.rng.random() for _ in range(cw)] for _ in range(ch)]
            out = []
            for y in range(self.height):
                row = []
                for x in range(self.width):
                    fx, fy = x / cell, y / cell
                    x0, y0 = int(fx), int(fy)
                    tx, ty = fx - x0, fy - y0
                    top = g[y0][x0] * (1 - tx) + g[y0][x0 + 1] * tx
                    bot = g[y0 + 1][x0] * (1 - tx) + g[y0 + 1][x0 + 1] * tx
                    row.append(top * (1 - ty) + bot * ty)
                out.append(row)
            return out
        big, small = layer(cells[0]), layer(cells[1])
        return [[weights[0] * big[y][x] + weights[1] * small[y][x] for x in range(self.width)]
                for y in range(self.height)]

    def _generate(self) -> list[list[str]]:
        elev, forest = self._noise(), self._noise((9, 3))
        flat = sorted(v for row in elev for v in row)
        n = len(flat)
        water_t, sand_t, rock_t = flat[int(n * 0.20)], flat[int(n * 0.26)], flat[int(n * 0.90)]
        fflat = sorted(v for row in forest for v in row)
        forest_t = fflat[int(n * 0.80)]
        tiles = []
        for y in range(self.height):
            row = []
            for x in range(self.width):
                e = elev[y][x]
                row.append(WATER if e < water_t else SAND if e < sand_t else ROCK if e > rock_t else GRASS)
            tiles.append(row)
        for y in range(self.height):  # forests, then berry bushes (denser near water)
            for x in range(self.width):
                if tiles[y][x] == GRASS:
                    if forest[y][x] > forest_t and self.rng.random() < 0.6:
                        tiles[y][x] = TREE
                        continue
                    near_water = any(self.in_bounds(x + dx, y + dy) and tiles[y + dy][x + dx] == WATER
                                     for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2))
                    if self.rng.random() < (0.12 if near_water else 0.045):
                        tiles[y][x] = FOOD
        return tiles

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def tile(self, x: int, y: int) -> str:
        return self.tiles[y][x]

    def walkable(self, x: int, y: int) -> bool:
        if not self.in_bounds(x, y):
            return False
        t = self.tiles[y][x]
        return t in WALKABLE or (t == STRUCTURE and self.structures[(x, y)]["walkable"])

    # ---- gathering ----
    def gather_options(self, x: int, y: int):
        """Resource tiles within reach, best first: food/crops, then trees (wood), then rocks (stone)."""
        prio = {FOOD: 0, CROP: 0, TREE: 1, ROCK: 2}
        found = [(prio[self.tiles[fy][fx]], max(abs(fx - x), abs(fy - y)), fx, fy)
                 for fy in range(max(0, y - 1), min(self.height, y + 2))
                 for fx in range(max(0, x - 1), min(self.width, x + 2)) if self.tiles[fy][fx] in prio]
        return [(fx, fy) for _, _, fx, fy in sorted(found)]

    def harvest(self, x: int, y: int, tick: int):
        """Returns {"what", "food", "seeds", "wood", "stone"} or None."""
        if not self.in_bounds(x, y):
            return None
        t = self.tiles[y][x]
        if t == FOOD:
            self.tiles[y][x] = GRASS
            self.regrow[(x, y)] = (tick + FOOD_REGROW_DAYS, FOOD)
            return {"what": "a wild bush", "food": 1, "seeds": 1 if self.rng.random() < 0.5 else 0, "wood": 0, "stone": 0}
        if t == CROP:
            self.tiles[y][x] = SPROUT
            self.plants[(x, y)] = {"growth": 0.0, "tended": {}}
            return {"what": "a ripe crop", "food": 3, "seeds": 1, "wood": 0, "stone": 0}
        if t == TREE:
            self.tiles[y][x] = GRASS
            self.regrow[(x, y)] = (tick + TREE_REGROW_DAYS, TREE)
            return {"what": "a tree", "food": 0, "seeds": 0, "wood": 2, "stone": 0}
        if t == ROCK:
            return {"what": "a rock", "food": 0, "seeds": 0, "wood": 0, "stone": 1}
        return None

    # ---- farming ----
    def plant(self, x: int, y: int) -> bool:
        if self.in_bounds(x, y) and self.tiles[y][x] == GRASS and (x, y) not in self.regrow:
            self.tiles[y][x] = SPROUT
            self.plants[(x, y)] = {"growth": 0.0, "tended": {}}
            return True
        return False

    def tend(self, x: int, y: int, who: str, tick: int):
        """Work a sprout -> (growth, partners, helped). Helps at most once every TEND_COOLDOWN days; a different
        farmer having tended it within TEAMWORK_WINDOW days doubles the effect."""
        p = self.plants[(x, y)]
        if tick - p.get("last", -99) < TEND_COOLDOWN:
            return p["growth"], [], False
        partners = [n for n, t in p["tended"].items() if n != who and tick - t <= TEAMWORK_WINDOW]
        p["growth"] += 2 if partners else 1
        p["tended"][who] = p["last"] = tick
        if p["growth"] >= GROW_NEEDED:
            self.tiles[y][x] = CROP
        return p["growth"], partners, True

    def needs_tending(self, x: int, y: int, tick: int) -> bool:
        return tick - self.plants.get((x, y), {}).get("last", -99) >= TEND_COOLDOWN

    def days_to_ripe(self, x: int, y: int) -> int:
        p = self.plants[(x, y)]
        rate = IRRIGATED_GROWTH_PER_DAY if (x, y) in self.irrigated else PLANT_GROWTH_PER_DAY
        return max(0, round((GROW_NEEDED - p["growth"]) / rate))

    def known_food(self, x: int, y: int, limit: int = 3):
        """Nearest food anyone has seen (the community's shared map) -> [(dx, dy, kind)]."""
        spots = [(max(abs(fx - x), abs(fy - y)), fx - x, fy - y, self.tiles[fy][fx]) for fx, fy in self.explored
                 if self.tiles[fy][fx] in (FOOD, CROP)]
        return [(dx, dy, "ripe crop" if t == CROP else "berry bush") for _, dx, dy, t in sorted(spots)[:limit]]

    def boost(self, x: int, y: int, amount: float) -> float:
        """Extra growth (e.g. from a hoe); returns the new growth."""
        p = self.plants[(x, y)]
        p["growth"] += amount
        if p["growth"] >= GROW_NEEDED and self.tiles[y][x] == SPROUT:
            self.tiles[y][x] = CROP
        return p["growth"]

    def plants_near(self, x: int, y: int, reach: int = 1):
        return [(fx, fy) for fy in range(max(0, y - reach), min(self.height, y + reach + 1))
                for fx in range(max(0, x - reach), min(self.width, x + reach + 1))
                if self.tiles[fy][fx] == SPROUT]

    # ---- building ----
    def build(self, x: int, y: int, kind: str, text: str, who: str, tick: int):
        """Place a free-form structure. Returns (ok, reason)."""
        if not self.in_bounds(x, y):
            return False, "outside the world"
        t, k = self.tiles[y][x], kind.lower()
        if t == WATER and not any(w in k for w in WATER_OK_WORDS):
            return False, "water: only a bridge/dock/path-like structure can go there"
        if t not in (GRASS, SAND, WATER):
            return False, f"can't build on {t}"
        func = function_of(kind)
        for dx, dy, s in self.structures_near(x, y, SAME_KIND_RADIUS if func else 3):
            if (func and s.get("function") == func) or s["kind"].lower() == k:
                return False, (f"there is already a {s['kind']} close by (dx={dx} dy={dy} from the spot) - use it, "
                               "or build something different")
        self.structures[(x, y)] = {"kind": kind, "text": text, "by": who, "tick": tick, "under": t,
                                   "walkable": not any(w in k for w in BLOCK_WORDS), "function": func}
        if func == "storage":
            self.structures[(x, y)]["stock"] = {"food": 0, "seeds": 0, "wood": 0, "stone": 0}
        if func == "well":                       # waters the fields around it
            self.irrigated |= {(x + dx, y + dy) for dx in range(-3, 4) for dy in range(-3, 4)}
        self.tiles[y][x] = STRUCTURE
        return True, ""

    def function_near(self, x: int, y: int, func: str, radius: int):
        """Nearest building with this function within radius -> ((sx, sy), structure) or None."""
        found = [(max(abs(sx - x), abs(sy - y)), (sx, sy), s) for (sx, sy), s in self.structures.items()
                 if s.get("function") == func and max(abs(sx - x), abs(sy - y)) <= radius]
        return min(found, key=lambda f: f[0])[1:] if found else None

    def structures_near(self, x: int, y: int, radius: int):
        return [(sx - x, sy - y, s) for (sx, sy), s in self.structures.items()
                if max(abs(sx - x), abs(sy - y)) <= radius]

    # ---- finding the way ----
    def path(self, start, goal, max_nodes: int = 4000) -> list | None:
        """Shortest walkable route from start to the first tile where goal(x, y) is true (breadth-first).
        Returns the steps after start (empty if start already qualifies), or None if unreachable."""
        from collections import deque
        if goal(*start):
            return []
        prev, todo = {start: None}, deque([start])
        while todo and len(prev) < max_nodes:
            x, y = todo.popleft()
            for nx, ny in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
                if (nx, ny) in prev or not self.walkable(nx, ny):
                    continue
                prev[(nx, ny)] = (x, y)
                if goal(nx, ny):
                    out, p = [], (nx, ny)
                    while p != start:
                        out.append(p)
                        p = prev[p]
                    return out[::-1]
                todo.append((nx, ny))
        return None

    def open_ways(self, x: int, y: int, look: int = 4) -> dict:
        """How many tiles you can walk straight in each direction (stops at water, rock, trees, walls)."""
        out = {}
        for name, (dx, dy) in (("north", (0, -1)), ("east", (1, 0)), ("south", (0, 1)), ("west", (-1, 0))):
            n = 0
            while n < look and self.walkable(x + dx * (n + 1), y + dy * (n + 1)):
                n += 1
            blocked = self.tiles[y + dy][x + dx] if n == 0 and self.in_bounds(x + dx, y + dy) else "edge"
            out[name] = n if n else blocked
        return out

    # ---- exploration ----
    def reveal(self, x: int, y: int, radius: int) -> dict:
        """Mark tiles around (x, y) as explored; returns counts of what was newly revealed."""
        new = {"tiles": 0, "water": 0, "tree": 0, "food": 0, "rock": 0}
        for yy in range(max(0, y - radius), min(self.height, y + radius + 1)):
            for xx in range(max(0, x - radius), min(self.width, x + radius + 1)):
                if (xx, yy) not in self.explored:
                    self.explored.add((xx, yy))
                    new["tiles"] += 1
                    t = self.tiles[yy][xx]
                    if t in new:
                        new[t] += 1
                    elif t == CROP:
                        new["food"] += 1
        return new

    def explored_pct(self) -> int:
        return round(100 * len(self.explored) / (self.width * self.height))

    def nearest_unexplored(self, x: int, y: int, cell: int = 6):
        """(dx, dy) to the middle of the closest mostly-unexplored area, or None when it's all known."""
        best = None
        for sy in range(0, self.height, cell):
            for sx in range(0, self.width, cell):
                cx, cy = min(sx + cell // 2, self.width - 1), min(sy + cell // 2, self.height - 1)
                total = (min(sx + cell, self.width) - sx) * (min(sy + cell, self.height) - sy)
                seen = sum((xx, yy) in self.explored for yy in range(sy, min(sy + cell, self.height))
                           for xx in range(sx, min(sx + cell, self.width)))
                if seen / total < 0.5:
                    d = max(abs(cx - x), abs(cy - y))
                    if best is None or d < best[0]:
                        best = (d, cx - x, cy - y)
        return best[1:] if best else None

    def explored_rows(self) -> list[str]:
        return ["".join("1" if (x, y) in self.explored else "0" for x in range(self.width)) for y in range(self.height)]

    def water_near(self, x: int, y: int) -> bool:
        return any(self.in_bounds(x + dx, y + dy) and self.tiles[y + dy][x + dx] == WATER
                   for dx in (-1, 0, 1) for dy in (-1, 0, 1))

    # ---- time ----
    def update(self, tick: int, growth_bonus: float = 0.0):
        for pos, (t, tile) in list(self.regrow.items()):
            if tick >= t:
                if self.tiles[pos[1]][pos[0]] == GRASS:
                    self.tiles[pos[1]][pos[0]] = tile
                del self.regrow[pos]
        for (x, y), p in self.plants.items():
            if self.tiles[y][x] == SPROUT:
                p["growth"] += (IRRIGATED_GROWTH_PER_DAY if (x, y) in self.irrigated else PLANT_GROWTH_PER_DAY) + growth_bonus
                if p["growth"] >= GROW_NEEDED:
                    self.tiles[y][x] = CROP

    def food_near(self, x: int, y: int, reach: int = 1):
        """Food tiles (wild bushes or ripe crops) within chebyshev distance `reach`, nearest first."""
        found = [(max(abs(fx - x), abs(fy - y)), fx, fy)
                 for fy in range(max(0, y - reach), min(self.height, y + reach + 1))
                 for fx in range(max(0, x - reach), min(self.width, x + reach + 1))
                 if self.tiles[fy][fx] in (FOOD, CROP)]
        return [(fx, fy) for _, fx, fy in sorted(found)]

    def view(self, x: int, y: int, radius: int, others: dict[tuple[int, int], str]) -> str:
        """ASCII window around (x, y); '@' is you, uppercase letters are other agents."""
        lines = []
        for yy in range(y - radius, y + radius + 1):
            row = ""
            for xx in range(x - radius, x + radius + 1):
                if (xx, yy) == (x, y):
                    row += "@"
                elif (xx, yy) in others:
                    row += others[(xx, yy)]
                elif not self.in_bounds(xx, yy):
                    row += " "
                else:
                    row += GLYPH[self.tiles[yy][xx]]
            lines.append(row)
        return "\n".join(lines)

    # ---- saving ----
    def to_dict(self) -> dict:
        key = lambda p: f"{p[0]},{p[1]}"
        return {"width": self.width, "height": self.height, "tiles": self.tiles,
                "regrow": {key(p): list(v) for p, v in self.regrow.items()},
                "plants": {key(p): v for p, v in self.plants.items()},
                "structures": {key(p): v for p, v in self.structures.items()},
                "explored": sorted(key(p) for p in self.explored)}

    @classmethod
    def from_dict(cls, d: dict) -> "World":
        pos = lambda k: tuple(int(v) for v in k.split(","))
        w = cls.__new__(cls)
        w.width, w.height, w.tiles = d["width"], d["height"], d["tiles"]
        w.rng = random.Random()
        w.regrow = {pos(k): tuple(v) for k, v in d["regrow"].items()}
        w.plants = {pos(k): v for k, v in d["plants"].items()}
        w.structures = {pos(k): v for k, v in d["structures"].items()}
        for s in w.structures.values():                     # saves from before buildings had functions
            s.setdefault("function", function_of(s["kind"]))
            if s["function"] == "storage":
                s.setdefault("stock", {"food": 0, "seeds": 0, "wood": 0, "stone": 0})
        w.explored = {pos(k) for k in d["explored"]}
        w._find_irrigated()
        return w
