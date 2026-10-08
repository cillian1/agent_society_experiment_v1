"""Every tunable number of the simulation, in one place."""

# ---- models ----
HAIKU, SONNET, OPUS = "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"
LOCAL = "local"                       # whatever local model the server was started with
TIERS = {"local": LOCAL, "haiku": HAIKU, "sonnet": SONNET, "opus": OPUS}

# ---- world ----
WORLD_W, WORLD_H = 64, 40
FOOD_REGROW_DAYS = 100                # wild bushes come back slowly
TREE_REGROW_DAYS = 300
GROW_NEEDED = 8.0                     # growth points for a planted sprout to ripen
PLANT_GROWTH_PER_DAY = 0.4            # plants grow by themselves (~20 days)...
IRRIGATED_GROWTH_PER_DAY = 0.6        # ...faster near water (~13 days)
TEND_COOLDOWN = 3                     # tending helps at most once every few days - then it just needs time
TEAMWORK_WINDOW = 6                   # days within which a second farmer counts as "working together"

# ---- senses ----
VIEW_RADIUS = 6                       # agents see a (2r+1)^2 window
SMELL_RADIUS = 10                     # how far they sense the nearest food
HEARING_RADIUS = 8

# ---- body & life ----
HUNGER_PER_DAY = 1.5
EAT_RELIEF = 40
STARVE_DAMAGE = 2                     # health lost per day at hunger 100 (50 days to die)
INSTINCT_EAT_AT = 75                  # agents carrying food eat by reflex at this hunger (no turn used)
START_FOOD = 3                        # settlers arrive with a little food
HUNGER_WARNING = 55
BABY_DAYS = 5                         # newborns can't think or feed themselves; others must care for them
ADULT_AGE = 10                        # child from BABY_DAYS, adult from ADULT_AGE (days since birth)
OLD_AGE = 600                         # elders from this age; actual lifespan grows with longevity (see models.py)
OLD_AGE_DEATH_CHANCE = 0.005          # per day once past one's lifespan

# ---- relationships & family ----
LOVE_BOND = 50
FRIEND_BOND = 25
BOND_DECAY = 0.998
CHILD_FOOD_COST = 2                   # each parent pays this at conception
CHILD_COOLDOWN = 50
PREGNANCY_DAYS = 10
BABY_START_HUNGER = 30
BABY_HUNGER_PER_DAY = 20              # babies get hungry fast...
BABY_STARVE_DAMAGE = 25               # ...and suffer quickly when nobody feeds them
CARE_RELIEF = 50                      # hunger removed when someone feeds a baby
DEFAULT_MAX_AGENTS = 14

# ---- making things ----
MAX_STEPS = 3                         # tiles per move
BUILD_COST = 1                        # wood/stone per structure
CRAFT_COST = 1                        # wood/stone per object
MAX_ITEMS = 8
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
ORDER_MEMORY_DAYS = 30                # how long a request from the Human stays on an agent's mind
MAX_IDEAS_IN_PROMPT = 10
MAX_QUEUE = 4                         # follow-up actions an agent may line up (run without a model call)
REFLECT_EVERY = 20                    # days between an agent's reflections on its life and ambition

# ---- bookkeeping ----
AUTOSAVE_EVERY = 25                   # days
MAX_EVENTS = 300
MAX_STATS_POINTS = 2000

# ---- the Game Master: judges free-form attempts and turns ideas into real discoveries ----
DISCOVERY_COOLDOWN = 10               # days between discoveries by the same agent
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

