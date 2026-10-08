"""Every tunable number of the simulation, in one place."""

# ---- models ----
HAIKU, SONNET, OPUS = "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"
LOCAL = "local"                       # whatever local model the server was started with
TIERS = {"local": LOCAL, "haiku": HAIKU, "sonnet": SONNET, "opus": OPUS}

# ---- world ----
WORLD_W, WORLD_H = 64, 40
FOOD_REGROW_DAYS = 150                # wild bushes come back slowly
TREE_REGROW_DAYS = 300
GROW_NEEDED = 8.0                     # growth points for a planted sprout to ripen
TEAMWORK_WINDOW = 6                   # days within which a second farmer counts as "working together"

# ---- senses ----
VIEW_RADIUS = 6                       # agents see a (2r+1)^2 window
SMELL_RADIUS = 10                     # how far they sense the nearest food
HEARING_RADIUS = 8

# ---- body & life ----
HUNGER_PER_DAY = 1.5
EAT_RELIEF = 40
STARVE_DAMAGE = 4
HUNGER_WARNING = 55
ADULT_AGE = 40
OLD_AGE = 500
OLD_AGE_DEATH_CHANCE = 0.015

# ---- relationships & family ----
LOVE_BOND = 50
FRIEND_BOND = 25
BOND_DECAY = 0.998
CHILD_FOOD_COST = 2
CHILD_COOLDOWN = 50
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

# ---- bookkeeping ----
AUTOSAVE_EVERY = 25                   # days
MAX_EVENTS = 300
MAX_STATS_POINTS = 2000
