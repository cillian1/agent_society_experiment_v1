"""Every tunable number of the simulation, in one place. One turn is one HOUR (see clock.py); durations
written as N * DAY are in days."""
from .clock import DAY

# ---- models ----
HAIKU, SONNET, OPUS = "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"
LOCAL = "local"                       # whatever local model the server was started with
TIERS = {"local": LOCAL, "haiku": HAIKU, "sonnet": SONNET, "opus": OPUS}

# ---- world ----
WORLD_W, WORLD_H = 64, 40
FOOD_REGROW_DAYS = 100                # hours until a picked bush regrows (~4 days)
TREE_REGROW_DAYS = 300                # hours
GROW_NEEDED = 8.0                     # growth points for a planted sprout to ripen
PLANT_GROWTH_PER_DAY = 0.4            # per hour: plants grow by themselves (~20 hours)...
IRRIGATED_GROWTH_PER_DAY = 0.6        # ...faster near water (~13 hours)
TEND_COOLDOWN = 3                     # hours: tending helps at most once every few hours - then it just needs time
TEAMWORK_WINDOW = 6                   # hours within which a second farmer counts as "working together"

# ---- senses ----
VIEW_RADIUS = 6                       # agents see a (2r+1)^2 window
SMELL_RADIUS = 10                     # how far they sense the nearest food
HEARING_RADIUS = 8

# ---- body & life ----
HUNGER_PER_DAY = 1.2                  # per HOUR awake (half while asleep)
EAT_RELIEF = 40
STARVE_DAMAGE = 1                     # health lost per hour at hunger 100 (~4 days to die)
INSTINCT_EAT_AT = 75                  # agents carrying food eat by reflex at this hunger (no turn used)
START_FOOD = 3                        # settlers arrive with a little food
HUNGER_WARNING = 55
BABY_DAYS = 5 * DAY                   # newborns can't think or feed themselves; others must care for them
ADULT_AGE = 10 * DAY                  # child from BABY_DAYS, adult from ADULT_AGE (since birth)
OLD_AGE = 600 * DAY                   # elders from this age; actual lifespan grows with longevity (see models.py)
OLD_AGE_DEATH_CHANCE = 0.0003         # per hour once past one's lifespan

# ---- relationships & family ----
LOVE_BOND = 50
FRIEND_BOND = 25
BOND_DECAY = 0.9997                   # per hour: feelings fade slowly without contact
BOND = {                              # how much each kind of contact raises feelings (before social charm & discoveries)
    "talked_to": 5, "talked_back": 3,     # someone speaks to you directly / you speak to them
    "heard": 1,                           # you hear someone talking to everyone
    "gift": 15, "gave": 6,                # receiving / giving food or an object
    "love_gift": 12,                      # extra when a gift is a gesture of love (fond of them, or with a message)
    "court": 14, "courted": 5,            # being courted (scaled by your kindness) / courting
    "cared_for": 10, "carer": 8,
    "teamwork": 3,                        # farming the same plant
    "together": 0.3,                      # each waking hour spent within 2 tiles of each other
}
CHILD_FOOD_COST = 2                   # each parent pays this at conception
CHILD_COOLDOWN = 3 * DAY
PREGNANCY_DAYS = 10 * DAY
BABY_START_HUNGER = 30
BABY_HUNGER_PER_DAY = 3               # per hour: babies get hungry fast...
BABY_STARVE_DAMAGE = 6                # ...and suffer quickly when nobody feeds them (per hour)
CARE_RELIEF = 50                      # hunger removed when someone feeds a baby
DEFAULT_MAX_AGENTS = 14

# ---- making things ----
MAX_STEPS = 3                         # tiles per move
BUILD_COST = 1                        # wood/stone per structure
CRAFT_COST = 1                        # wood/stone per object
MAX_ITEMS = 8
FUNCTIONS = {                         # what a building does, recognised from words in its name
    "storage": (("storehouse", "storage", "granary", "barn", "pantry", "silo", "warehouse", "cellar"),
                "store/take shared food, seeds, wood and stone"),
    "home": (("house", "hut", "home", "shelter", "cabin", "lodge", "tent", "dwelling"),
             "spending the day next to it heals you (rest)"),
    "fire": (("fire", "hearth", "oven", "kitchen", "campfire", "bonfire"),
             "meals eaten nearby fill you up more, and people near it grow closer"),
    "well": (("well", "irrigation", "fountain", "canal", "reservoir"),
             "crops within 3 tiles grow as if beside water"),
    "workshop": (("workshop", "forge", "smithy", "workbench", "craft"),
                 "crafting within 2 tiles costs no materials"),
}
DEFAULT_COSTS = {                     # what familiar buildings take; new kinds get a blueprint from Sol
    "home": {"wood": 3}, "storage": {"wood": 4, "stone": 1}, "fire": {"wood": 2, "stone": 1},
    "well": {"stone": 4, "wood": 1}, "workshop": {"wood": 3, "stone": 2}, "wall": {"stone": 2},
    "bridge": {"wood": 3}, None: {"wood": 1},
}
MAX_BUILD_COST = 8
DEFAULT_SIZES = {"home": (2, 2), "storage": (2, 2), "workshop": (2, 2), "fire": (1, 1), "well": (1, 1), None: (1, 1)}
BIG_WORDS = ("hall", "temple", "school", "market", "palace", "castle", "church", "tavern", "inn", "library",
             "theater", "theatre", "arena", "longhouse", "town", "museum", "barracks", "monastery")
MAX_BUILDING_SIZE = 3
BLOCK_WORDS_COST = [(("wall", "fence", "palisade"), {"stone": 2}), (("bridge", "dock", "pier"), {"wood": 3})]                    # per material
SAME_KIND_RADIUS = 6                  # no second building with the same function this close
HOME_HEAL = 1                         # extra health per hour resting in/next to a home
FIRE_MEAL_BONUS = 15
FISH_COOLDOWN = 3
TOOLS = {                             # object-name keywords -> what they're good for
    "wood": ("axe", "hatchet", "saw"),
    "stone": ("pick", "hammer", "chisel"),
    "farm": ("hoe", "shovel", "rake", "spade", "plow", "trowel"),
    "fish": ("rod", "fish", "net", "spear", "harpoon", "trap"),
}

# ---- memory & prompts ----
KEEP_RECENT = 25                      # memory lines shown verbatim; older ones are summarised
COMPACT_AFTER = 20                    # this many unsummarised old lines trigger a summary
ORDER_MEMORY_DAYS = 3 * DAY           # how long a request from the Human stays on an agent's mind
MAX_IDEAS_IN_PROMPT = 10
SOL_EVERY = 3 * DAY                   # Sol's default gap between reviews; Sol picks the next one (1-7 days)
SOL_MIN_DAYS, SOL_MAX_DAYS = 1, 7
SOL_HOUR = 7
ADVICE_MEMORY = 2 * DAY
MAX_QUEUE = 4                         # follow-up actions an agent may line up (run without a model call)
REFLECT_EVERY = DAY                   # an agent reflects on its life and ambition once a day

# ---- bookkeeping ----
AUTOSAVE_EVERY = DAY
MAX_EVENTS = 300
MAX_STATS_POINTS = 2000

# ---- Sol as referee: judges free-form attempts and turns ideas into real discoveries ----
DISCOVERY_COOLDOWN = DAY              # between discoveries by the same agent
EFFECTS = {                           # what a discovery may do: key -> (meaning, max amount per discovery, max total)
    "harvest": ("+N extra food from every harvest", 1, 2),
    "growth": ("plants grow +N faster per day", 0.3, 0.8),
    "hunger": ("hunger rises N% slower", 20, 40),
    "health": ("+N health recovered per day when fed", 2, 4),
    "speed": ("+N tiles per move", 1, 2),
    "materials": ("+N extra wood/stone per gather", 1, 2),
    "friendship": ("friendships grow N% faster", 40, 100),
    "lifespan": ("+N days of life", 150, 400),
    "fishing": ("anyone can fish without a tool", 1, 1),
    "building": ("building and crafting cost nothing", 1, 1),
}

