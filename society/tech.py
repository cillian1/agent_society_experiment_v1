"""The hidden tech tree. Agents never see it: they find it by experimenting (attempt / invent). Sol, as referee, is
told which breakthroughs are within reach, and an attempt that clearly aims at one can unlock it - straight away if
it succeeds, or after a few honest failures (people learn by trying). Each breakthrough changes the rules and moves
the society through its ages."""

# id: name, what it needs first, words that suggest someone is working on it, what it does (shown once discovered),
# and its effects: numbers add to the same effects as Sol's discoveries (see config.EFFECTS); flags switch things on.
TECHS = {
    "fire": ("Fire making", [], ("fire", "flint", "spark", "kindl", "friction", "ember"),
             "fires and hearths can be built; cooked meals fill you up more", {}, {"fire"}),
    "stone_tools": ("Stone tools", [], ("knap", "stone tool", "flint", "sharp stone", "blade", "chipp", "hand axe"),
                    "+1 wood or stone from every gather", {"materials": 1}, set()),
    "agriculture": ("Agriculture", [], ("farm", "plow", "plough", "sow", "cultivat", "field", "crop rotation", "till"),
                    "crops grow faster", {"growth": 0.15}, set()),
    "weaving": ("Weaving", [], ("weav", "cloth", "fiber", "fibre", "loom", "sew", "clothes", "garment", "blanket"),
                "warm clothes: winter nights hurt half as much", {}, {"warm"}),
    "cooking": ("Cooking", ["fire"], ("cook", "roast", "stew", "smok", "bake", "boil"),
                "hunger rises 15% slower", {"hunger": 15}, set()),
    "pottery": ("Pottery", ["fire"], ("pot", "clay", "kiln", "jar", "ceramic", "vessel"),
                "food no longer spoils, carried or stored", {}, {"no_spoil"}),
    "hunting_weapons": ("Spears and bows", ["stone_tools"], ("spear", "bow", "arrow", "sling", "trap", "javelin", "hunt"),
                        "hunting succeeds far more often, even from a distance", {}, {"weapons"}),
    "herbal_medicine": ("Herbal medicine", ["agriculture"], ("herb", "medicin", "heal", "remedy", "poultice", "salve"),
                        "+1 health recovered per hour", {"health": 1}, set()),
    "irrigation": ("Irrigation", ["agriculture"], ("irrigat", "canal", "ditch", "channel", "aqueduct"),
                   "crops grow faster again, and wells water a wider area", {"growth": 0.15}, {"irrigation"}),
    "husbandry": ("Animal husbandry", ["agriculture", "hunting_weapons"], ("tame", "herd", "pen", "domestic", "breed", "pasture", "shepherd"),
                  "animals can be tamed easily; tame goats and sheep give food every day", {}, {"husbandry"}),
    "masonry": ("Masonry", ["stone_tools"], ("mason", "brick", "mortar", "cut stone", "stone wall", "quarry"),
                "building goes 50% faster", {}, {"masonry"}),
    "boats": ("Boats", ["weaving", "stone_tools"], ("boat", "raft", "canoe", "paddle", "oar", "sail"),
              "anyone can fish, and catches are bigger", {"fishing": 1}, {"boats"}),
    "writing": ("Writing", ["pottery"], ("writ", "symbol", "record", "tablet", "script", "letter", "glyph", "tally"),
                "people remember more, and laws and stories are never lost", {}, {"writing"}),
    "wheel": ("The wheel", ["pottery", "masonry"], ("wheel", "cart", "axle", "wagon"),
              "+1 tile per move", {"speed": 1}, set()),
    "bronze": ("Bronze working", ["fire", "masonry"], ("bronze", "copper", "smelt", "metal", "furnace", "ore", "tin"),
               "+1 wood or stone from every gather; better tools", {"materials": 1}, set()),
    "calendar": ("The calendar", ["writing"], ("calendar", "star", "season", "astronom", "moon", "solstice"),
                 "everyone knows exactly when each season comes", {}, {"calendar"}),
    "iron": ("Iron working", ["bronze"], ("iron", "forge", "steel", "smith", "anvil"),
             "+1 wood or stone from every gather; hunting is easier", {"materials": 1}, {"weapons"}),
}
AGES = [("iron", "Iron Age"), ("bronze", "Bronze Age"), ("agriculture+pottery", "Farming Age"), ("fire", "Age of Fire")]
FAILS_TO_LEARN = 3          # honest failed attempts at the same breakthrough before it clicks anyway


def name(tid: str) -> str:
    return TECHS[tid][0]


def age(known) -> str:
    for need, label in AGES:
        if all(t in known for t in need.split("+")):
            return label
    return "Stone Age"


def within_reach(known) -> list[str]:
    return [t for t, (_, req, *_r) in TECHS.items() if t not in known and all(r in known for r in req)]


def match(text: str, known) -> str | None:
    """The breakthrough within reach that an attempt is clearly aiming at, if any."""
    text = (text or "").lower()
    best, hits = None, 0
    for t in within_reach(known):
        n = sum(w in text for w in TECHS[t][2])
        if n > hits:
            best, hits = t, n
    return best


def effect(known, key: str) -> float:
    return sum(TECHS[t][4].get(key, 0) for t in known)


def flag(known, key: str) -> bool:
    return any(key in TECHS[t][5] for t in known)


def describe(tid: str) -> str:
    return f"{TECHS[tid][0]}: {TECHS[tid][3]}"


def hints(known) -> str:
    """For Sol only: what could be discovered next and what it would take."""
    return "; ".join(f"{t} = {TECHS[t][0]} (e.g. {', '.join(TECHS[t][2][:3])})" for t in within_reach(known))
