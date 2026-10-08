"""2D tile world: generation, walkability, resources, farming, structures and the explored map."""
import random

GRASS, WATER, SAND, ROCK, FOOD, SPROUT, CROP = "grass", "water", "sand", "rock", "food", "sprout", "crop"
TREE, STRUCTURE = "tree", "structure"
GLYPH = {GRASS: "g", WATER: "~", SAND: ".", ROCK: "#", FOOD: "f", SPROUT: ",", CROP: "*", TREE: "^", STRUCTURE: "&"}
from .config import FOOD_REGROW_DAYS, GROW_NEEDED, TEAMWORK_WINDOW, TREE_REGROW_DAYS, WORLD_H, WORLD_W

WALKABLE = (GRASS, SAND, FOOD, SPROUT, CROP)
WALK_WORDS = ("bridge", "path", "road", "floor", "gate", "door", "bed", "bench", "dock", "stair", "plaza", "carpet")
WATER_OK_WORDS = ("bridge", "dock", "pier", "raft", "path")


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
        self.irrigated = {(x, y) for y in range(self.height) for x in range(self.width)
                          if any(self.in_bounds(x + dx, y + dy) and self.tiles[y + dy][x + dx] == WATER
                                 for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2))}

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
        """Work a sprout. A second farmer within TEAMWORK_WINDOW turns doubles the effect."""
        p = self.plants[(x, y)]
        partners = [n for n, t in p["tended"].items() if n != who and tick - t <= TEAMWORK_WINDOW]
        p["growth"] += 2 if partners else 1
        p["tended"][who] = tick
        if p["growth"] >= GROW_NEEDED:
            self.tiles[y][x] = CROP
        return p["growth"], partners

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
        self.structures[(x, y)] = {"kind": kind, "text": text, "by": who, "tick": tick, "under": t,
                                   "walkable": any(w in k for w in WALK_WORDS)}
        self.tiles[y][x] = STRUCTURE
        return True, ""

    def structures_near(self, x: int, y: int, radius: int):
        return [(sx - x, sy - y, s) for (sx, sy), s in self.structures.items()
                if max(abs(sx - x), abs(sy - y)) <= radius]

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
    def update(self, tick: int):
        for pos, (t, tile) in list(self.regrow.items()):
            if tick >= t:
                if self.tiles[pos[1]][pos[0]] == GRASS:
                    self.tiles[pos[1]][pos[0]] = tile
                del self.regrow[pos]
        for (x, y), p in self.plants.items():
            if self.tiles[y][x] == SPROUT:
                p["growth"] += 0.2 if (x, y) in self.irrigated else 0.05   # nature helps a little
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
        w.explored = {pos(k) for k in d["explored"]}
        w._find_irrigated()
        return w
