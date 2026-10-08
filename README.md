# Agent Society 🌱

A small world of AI agents that start with nothing but a personality. Two peoples who don't speak each other's
language explore, hunt, farm, build, trade, make promises (and break them), form groups, elect leaders, pass laws,
tell stories, discover fire and bronze, survive winters, fall in love, have children and grow old — and you can
watch, talk to them, lead them, scrub back through their history, and save their world to continue later.

## Quick start (Windows)
```
py -m pip install -r requirements.txt
py serve.py                         # then open http://127.0.0.1:8000
```
Useful options: `--resume` (continue from the last autosave), `--load NAME`, `--seed 42`, `--max-agents 20`,
`--local-concurrency 20`, `--interval 2` (minimum seconds per hour). `py serve.py --help` lists everything.
On Mac/Linux use `python` instead of `py`.

### Where the agents' brains come from
The hub auto-detects what is available and shows it in the top bar:
- **Local model (free)** through [Ollama](https://ollama.com) — see below.
- **Claude** (Haiku / Sonnet / Opus) when the `ANTHROPIC_API_KEY` environment variable is set.
- Neither? It falls back to a **scripted mock** (red banner): those agents can't really think or reply.

By default **everyone uses the local model.** Without an API key everyone
uses the local model; without a local server everyone uses Haiku. Change any agent's brain in their profile → *Brain*
(Local / Haiku / Sonnet / **Enlighten** = Opus, one agent at a time).

### Local model (RTX 5070 Ti, 16 GB)
Everyone uses one local model: **qwen2.5:14b-instruct** (smart, and it fits on a 16 GB card with room to spare).
1. Install Ollama, then `ollama pull qwen2.5:14b-instruct`.
2. Once: `setx OLLAMA_NUM_PARALLEL 4`, `setx OLLAMA_FLASH_ATTENTION 1`, `setx OLLAMA_KV_CACHE_TYPE q8_0`, then quit
   Ollama (tray icon → Quit) and start it again.
3. `py serve.py` (it uses 4 requests at once by default, matching `OLLAMA_NUM_PARALLEL`). `ollama ps` should show the
   model at `100% GPU`. If the local model gets overloaded the hub sends it fewer requests at once by itself, skips
   dreams until it has caught up, and tells you in the banner.
Another model: `--local-model NAME` (for example `qwen2.5:7b-instruct` for more speed on a smaller card).
LM Studio / llama.cpp / vLLM work too (`--local-api openai --local-url ...`). Claude models can still be chosen per
agent in their profile → Brain.

## Using the hub
| Where | What you can do |
|---|---|
| **Top bar** | The clock (month, day, year, hour; 🌅☀️🌇🌙), population, % explored, model calls (click for details). Pause / step one hour / speed. `?` = help. |
| **Map** | A sharp **isometric** world at any zoom (labels stay readable): trees, rocks, berry bushes, fields, walk-in buildings with roofs (see-through when someone is inside), construction sites that rise as people work, day and night with glowing fires. Scroll to zoom, drag to pan, click someone for their profile, double-click to follow, hover anything for details. Toggle 🌫️ fog, 💬 speech bubbles and 🎯 follow in the toolbar. Bars over heads: hunger (green→red) and task progress (gold). |
| **👥 People** | Everyone at a glance (hunger, food, age, what they're doing, construction progress, 💤 asleep). A **profile** has Overview, Thoughts (every decision), Memory, Relations (feelings & family) and Brain tabs, plus buttons to talk, find, follow or send a gift. |
| **💬 Talk** | Sol's card on top (latest review, next review, Talk / Review now), the conversation in the middle, and the composer at the bottom: pick everyone, Sol, one agent or any group; each answers right away in character. Choose whether they treat you as their **leader** (they obey), an advisor, or an observer. |
| **🌍 World** | The age and breakthroughs, groups with their leaders and laws, trades and promises, stories and place names, the animals, then discoveries, blueprints and a filterable feed of everything that happens. |
| **📜 History** | Sol's chronicle (a chapter a month), the family tree of everyone who ever lived, and a ⏪ replay slider that shows the map at any moment in the past. |
| **📈 Stats** | Population, hunger, food, exploration, structures, farms, objects and ideas over time (hover to read a day; table view available). |
| **⚙️ Settings** | Save / load worlds (also autosaved every day), start a new world, Sol's brain, available brains and usage per model, keyboard shortcuts. |

Keyboard: `Space` pause · `N` next hour · `+`/`−` zoom · `0` fit · `F` follow · `/` talk · `Esc` close · `1`–`6` tabs · `?` help.

**Art:** ground tiles, trees (green, autumn and bare), rocks, crops, tents, campfires and animals are CC0 sprites by
[Kenney](https://kenney.nl) (see `hub/static/assets/LICENSES.md`); people, buildings and effects are drawn in code.
People animate what they do: swinging an axe at a tree, a pickaxe at rock, hoeing, hammering at a building site,
fishing with a rod and float, hunting with a spear, picking berries, eating, talking, resting; they carry logs and
stones home, and little icons pop up when they get something done. Snow falls in winter and leaves in autumn.

## How the world works
### The living world
- **Seasons** (10-day months, 3 months each): spring grows crops fastest (rivers may flood fields), summer is long
  (dry woods can catch fire), autumn is harvest time, and in **winter** wild bushes are bare, crops stop growing,
  hunger rises faster and nights outside a home or away from a fire are freezing. Agents are warned as it approaches.
- **Animals** (deer, rabbits, boar, goats, sheep) roam, flee from people, breed in spring and summer and die back in
  winter. `hunt` them (spears and bows reach further; boar fight back) or `tame` goats and sheep, which follow their
  keeper and give food every day. Hunt an area out and it stays empty until animals wander back in.
- **Soil** tires with every harvest and recovers when rested, so farms have to move or rotate.
- **The tech tree is hidden**: 17 breakthroughs (fire, stone tools, agriculture, weaving, cooking, pottery, spears
  and bows, herbal medicine, irrigation, animal husbandry, masonry, boats, writing, the wheel, bronze, the calendar,
  iron) through five ages (Stone Age → Age of Fire → Farming Age → Bronze Age → Iron Age). Nobody is told what's
  possible: an `attempt` that clearly aims at something within reach unlocks it (Sol, as referee, knows the list), and
  three honest failures at the same thing get there anyway. Each one changes the rules (fires need fire; pots stop
  food rotting; weaving keeps you warm; masonry builds faster; writing lengthens memory...).

### Minds
- **Memory**: the whole life is kept; each turn the agent recalls the older memories that matter right now
  (promises, betrayals, births, deaths, laws, the people in front of them), not just the latest ones.
- **Beliefs**: short conclusions an agent holds ("the river floods in spring", "Dov can't be trusted"). They come
  from its decisions and dreams, can be wrong, and only spread through what people say.
- **Needs and moods**: rest, company, safety, respect and curiosity rise and fall with what happens; personality
  decides which is loudest, and that (or grief, or anger) sets the mood the agent is told about. Lonely agents seek
  company; humiliated ones hold grudges; exhausted ones work badly until they `rest`.
- **Skills** (farming, gathering, building, crafting, hunting) grow by doing, children learn twice as fast, and an
  expert can `teach` someone next to them.

### Society
- **Two peoples**, the Riverfolk and the Hillfolk, start on opposite sides of the map. Until someone has talked with
  the other people enough, their words come across as a few recognisable words and gestures. First contact is an
  event (and a story). Children of both peoples speak both.
- **Trade and promises**: `offer` a deal (give / want / within N hours), `accept` or `decline`, `promise`, and
  deliver with `give`. Kept promises build trust; broken ones turn feelings into grudges and get talked about.
  Everyone's reputation is visible. `steal` exists, and it's a crime.
- **Groups**: `found` one, `join`, `leave`, `vote` for a leader. Leaders set a shared plan, buildings belong to their
  builders' group, and the land around them is the group's territory (outlined on the map).
- **Laws**: leaders decree, members `propose` and `support`. Laws the game can read ("no stealing", "no taking from
  the granary at night", "no hunting in spring", "no cutting trees near the village") are checked: members nearby
  witness a breach and can `punish` (a fine), `forgive`, or the leader can `exile` someone for good. Other groups'
  laws apply on their land.
- **Stories and places**: memorable events become stories that Sol writes at its reviews and sometimes retells a
  little differently; they spread around the fire in the evening and when someone `tell`s one. Agents `name` places.
- **History**: Sol writes a monthly chapter of the chronicle; the hub keeps snapshots for the replay slider.

### Everyday life
- **Time:** one turn is one hour; 24 hours a day, 30 days a month, 12 months a year (Thawing … Deepwinter). Everyone sleeps
  from 22:00 to 06:00 (no model calls, slower hunger, a little healing).
- **Personality (0-1), four traits that each change the game:** *curious* (explores and tries bold attempts), *social*
  (others warm to them faster, time together bonds more), *kind* (easier to win over, nudged to share and care) and
  *driven* (builds faster, sticks to its plans instead of getting distracted). Children inherit a mix of their parents'.
- **Map:** 88×56 tiles of grass, sand, water, rock and forest. Trees give wood, rocks stone, berry bushes food (and seeds);
  bushes take about 4 days to regrow.
- **Survival:** hunger rises every hour; at 100 an agent loses health and can starve. Elders may die of old age.
- **Farming:** plants grow by themselves (about 20 hours, faster near water). Tending speeds them up once every few days,
  and a second farmer doubles it. Ripe crops give 3 food and replant.
- **Buildings take time and space:** a building is 1×1 up to 3×3 tiles (Sol decides with the blueprint), people can walk
  inside, and it starts as a construction site that needs hours of `work` (several workers go faster; strong or driven
  people too). The site, its progress bar and the builders' gold task bars are on the map.
- **Buildings do things:** storehouse/granary (`store` and `take` shared food, seeds, wood, stone), house/hut/shelter
  (rest next to it to heal), fire/hearth (cooked meals fill more, people near it bond faster), well (crops within 3
  tiles grow as if by water), workshop/forge (free crafting nearby). Nobody can build a second one of the same kind
  close to an existing one; anything else is decorative. Hover a building on the map to see what it does.
- **Making things:** `build` anything (houses, signs, bridges — bridges can cross water) and `craft` objects. Tools work:
  axe = more wood, pickaxe = more stone, hoe = faster crops, fishing rod/net = fish from water.
- **Abilities (1-10), four of them:** strength (extra wood & stone, faster building), speed (tiles per move), endurance
  (hunger rises slower, longer life) and wits (sight & smell range, better farming, longer memory). Settlers get a random
  mix; children inherit their parents' with a little variation.
- **Staying alive:** settlers arrive with some food; anyone carrying food eats by instinct when very hungry; starvation
  damage is slow; agents are told where the community has seen food.
- **Families:** a woman and a man in love can conceive; she is pregnant for 10 days. Newborns stay with their mother,
  don't think, and must be fed with `care` for 5 days; then they are children (on the local model) and adults at day 10.
- **Getting around:** `go` walks toward food, unexplored land, trees, rocks, water, a person or coordinates and finds the
  way around water and obstacles; agents can walk past each other and are told which directions are open.
- **Helping small models:** every turn an agent gets a few good options worked out from its situation (eat, feed a baby,
  gather, craft a first tool, talk to a neighbour, explore...), is warned when its last action failed, and a reply that
  isn't valid JSON is retried once.
- **Projects:** with `"next"` an agent lines up to 6 follow-up actions that run on the following turns without a model
  call (faster and free); it stops and rethinks when it's spoken to, gets hungry, a baby needs it, or a step fails.
- **Sleep & dreams:** nights cost nothing. On some nights (and at least every 3 days) an agent has one dream at a
  random hour (🌙 on the map): it looks back on its life, sets a long-term ambition and plan, may wake up with an idea,
  and tidies its memories into a summary - all in that single call.
- **Thinking:** each turn an agent runs a short checklist (danger/hunger first, then its plan, then something creative),
  keeps a plan from turn to turn, and gets one idea to consider for inspiration.
- **Society:** no roles or family at the start. Agents claim their own roles, `invent` ideas everyone hears about, build
  friendships by talking, giving and farming together, and when two adults love each other (50+ both ways) they can have
  a child, who inherits a mix of their personalities.
- **Memory:** everything notable goes into each agent's lifelong log; older memories are folded into a running summary
  so prompts stay small and nothing is forgotten.

## Anything is possible: Sol as referee
Agents can `attempt` anything they imagine — tame a deer, dig a well, brew medicine, build a boat, hold a festival.
**Sol** (the mentor, below) is also the referee and decides what
happens: success or failure with a short story, materials used or gained, a new object or building, or a
**discovery** that changes the rules for everyone (faster crops, slower hunger, healing, longer lives, faster travel,
more materials, friendship, fishing without tools, free building). Useful `invent`ions can become discoveries too.
Everything the referee grants is checked and capped by the engine, so it can't break the world. Discoveries are listed
in 🌍 World and every agent is told about them so they can build on each other's ideas.

## Blueprints: agents decide what to build
Agents can build anything they think their community needs. The first time someone tries a new kind of building, Sol
draws up a **blueprint**: what it costs (wood, stone, food) and what it does (storage, home, fire, well,
workshop, or decorative). If they don't have enough, they're told exactly what's missing. Blueprints are shared
knowledge (🌍 World → Blueprints); familiar buildings get sensible default costs.

## Sol, the mentor
Sol watches over the society from outside the world. Every few days at 07:00 — first after 3 days, then whenever Sol
decides (1-7 days), or when you press *Review now* in 💬 Talk — Sol
reviews everyone — who's doing pointless or repetitive things, what the community lacks — gives a short speech to
everyone, specific advice to individuals, and can line up next steps for people who are drifting. Talk to Sol by
picking 🧙 Sol in 💬 Talk (e.g. "Sol, get everyone working on a well") and Sol passes it on; you can still talk to
anyone directly. Sol starts on the local brain; choose another in ⚙️ Settings or with `--sol-model`.

## Project layout
```
serve.py / run.py        start the hub / run headless (`py run.py --days 240 --save test`; counts hours)
society/
  config.py              every tunable number (costs, ages, radii, regrowth...)
  world.py               map generation, resources, farming, structures, fog of war
  models.py              Agent, Traits (curious/social/kind/driven) and Abilities (strength/speed/endurance/wits)
  needs.py, memory.py    needs, moods and skills; recalling relevant memories, beliefs
  social.py, culture.py  trade, promises, groups, laws; stories, places, peoples and language
  ecology.py, tech.py    animals, soil, floods and wildfires; the hidden tech tree and ages
  history.py             snapshots for the replay, the chronicle, the family tree
  clock.py               hours, days, months, years; night and sleep
  mind.py                prompts, parsing the model's JSON, calling the model
  gm.py                  Sol as referee: judges attempts/inventions, designs blueprints, grants bounded outcomes
  sol.py                 Sol the mentor: periodic reviews, advice and conversations with the Human
  actions.py             what each action does (one function per action)
  engine.py              the hourly loop, life & death, the Human's interactions, stats, save state
  views.py               JSON sent to the hub
  persistence.py         save / load / list saves (./saves)
  llm.py, mock.py, cli.py  model backends (Claude, local, router), the offline mock, command-line options
hub/server.py            HTTP server + simulation thread
hub/static/              index.html, style.css, app.js (no build step)
tests/                   `python -m unittest`
```
**Adding an action:** write a function in `society/actions.py` decorated with `@action("name")`, add the name to
`ACTIONS` and a one-line description in `system_prompt` in `society/mind.py`.

## Saving money and time
- **Far from the camera, think less:** agents more than 30 tiles from where you're looking think three times less
  often (at least every 6 hours) - they carry on with their plans and routines meanwhile.
- **Thinking every few hours:** ⚙️ Settings → *Agents think* (every 1, 2, 3 or 6 hours; default 2). In between, agents
  follow the steps they planned or an obvious routine (eat, gather, tend, keep building) with no model call. Being spoken
  to, hunger, a baby or a failed step wakes their brain immediately.
- **Small prompts:** the rules every agent shares are one fixed text sent as the system prompt (Claude caches it, so it
  costs a tenth after the first call; local servers reuse it); each turn adds only what that agent sees and remembers,
  with repeated memories folded together. A 48-hour test went from 204 calls of ~2,900 tokens to 105 of ~2,000.
- **You go first:** your messages (and Sol's answers to you) skip the queue of routine thinking and use a short prompt,
  so replies come quickly even when everyone is busy.
- ⚙️ Settings shows calls, tokens per call and cached tokens per model.

## Speed
Hours don't wait for every brain. Each agent acts the moment its brain answers (at most once per hour); an hour ends
when everyone has answered or after a short wait (`--max-wait`, or the Slow / Normal / Fast buttons), so a slow brain
such as Opus only slows its own agent - it acts an hour or two later (💭 over its head) while everyone else carries on.
To go faster still: pick **Fast**, match `OLLAMA_NUM_PARALLEL` with `--local-concurrency`, use a smaller local model
(`--local-model qwen2.5:3b-instruct`), or cap the population (`--max-agents 8`).

## Cost
The top bar and ⚙️ Settings show calls and tokens per model. Local models are free. For a dollar estimate start with
`--price claude-haiku-5-5=IN,OUT` (USD per million tokens, from Anthropic's pricing page). Each agent makes at most one call per
waking hour, about every 2 hours by default (plus one per message you send it), so more agents and a shorter `--interval` cost more.
