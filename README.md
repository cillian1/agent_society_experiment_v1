# Agent Society 🌱

A small world of AI agents that start with nothing but a personality. They explore, talk, make friends, farm,
build, craft tools, invent customs, fall in love, have children and grow old — and you can watch, talk to them,
lead them, and save their world to continue later.

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

By default **Ada and Fenn use Haiku, everyone else and every baby uses the local model.** Without an API key everyone
uses the local model; without a local server everyone uses Haiku. Change any agent's brain in their profile → *Brain*
(Local / Haiku / Sonnet / **Enlighten** = Opus, one agent at a time, or any model id; `local:<name>` for another local model).

### Local models (RTX 5070 Ti, 16 GB)
Smarter agents = a bigger model. Easiest: keep the fast 7B for everyone and add a bigger one as **Smart local**:
`ollama pull qwen2.5:14b-instruct`, then `py serve.py --local-concurrency 20 --smart-local-model qwen2.5:14b-instruct`
and pick 🧠 Smart local in the Brain tab of the agents you care about (both models must fit in VRAM together).
Or switch everyone: `qwen2.5:7b-instruct` is the fast default; `ollama pull qwen2.5:14b-instruct` and start with
`--local-model qwen2.5:14b-instruct --local-concurrency 8` (and `OLLAMA_NUM_PARALLEL=8`) for noticeably better decisions at
roughly half the speed. Or give your favourite agents Haiku/Sonnet in their profile → Brain.

1. Install Ollama, then `ollama pull qwen2.5:7b-instruct`.
2. For many agents at once: `setx OLLAMA_NUM_PARALLEL 20`, `setx OLLAMA_FLASH_ATTENTION 1`, `setx OLLAMA_KV_CACHE_TYPE q8_0`,
   then quit and restart Ollama.
3. `py serve.py --local-concurrency 20`. Check `ollama ps` shows `100% GPU`; if not, lower `OLLAMA_NUM_PARALLEL`
   or use `qwen2.5:3b-instruct`. LM Studio / llama.cpp / vLLM work too (`--local-api openai --local-url ...`).

## Using the hub
| Where | What you can do |
|---|---|
| **Top bar** | The clock (month, day, year, hour; 🌅☀️🌇🌙), population, % explored, model calls (click for details). Pause / step one hour / speed. `?` = help. |
| **Map** | A sharp **isometric** world at any zoom (labels stay readable): trees, rocks, berry bushes, fields, walk-in buildings with roofs (see-through when someone is inside), construction sites that rise as people work, day and night with glowing fires. Scroll to zoom, drag to pan, click someone for their profile, double-click to follow, hover anything for details. Toggle 🌫️ fog, 💬 speech bubbles and 🎯 follow in the toolbar. Bars over heads: hunger (green→red) and task progress (gold). |
| **👥 People** | Everyone at a glance (hunger, food, age, what they're doing, construction progress, 💤 asleep). A **profile** has Overview, Thoughts (every decision), Memory, Relations (feelings & family) and Brain tabs, plus buttons to talk, find, follow or send a gift. |
| **💬 Talk** | Sol's card on top (latest review, next review, Talk / Review now), the conversation in the middle, and the composer at the bottom: pick everyone, Sol, one agent or any group; each answers right away in character. Choose whether they treat you as their **leader** (they obey), an advisor, or an observer. |
| **🌍 World** | A filterable feed of conversations, births and deaths, building, ideas, exploration and food. |
| **📈 Stats** | Population, hunger, food, exploration, structures, farms, objects and ideas over time (hover to read a day; table view available). |
| **⚙️ Settings** | Save / load worlds (also autosaved every day), start a new world, Sol's brain, available brains and usage per model, keyboard shortcuts. |

Keyboard: `Space` pause · `N` next hour · `+`/`−` zoom · `0` fit · `F` follow · `/` talk · `Esc` close · `1`–`5` tabs · `?` help.

## How the world works
- **Time:** one turn is one hour; 24 hours a day, 30 days a month, 12 months a year (Thawing … Deepwinter). Everyone sleeps
  from 22:00 to 06:00 (no model calls, slower hunger, a little healing).
- **Personality (0-1), four traits that each change the game:** *curious* (explores and tries bold attempts), *social*
  (others warm to them faster, time together bonds more), *kind* (easier to win over, nudged to share and care) and
  *driven* (builds faster, sticks to its plans instead of getting distracted). Children inherit a mix of their parents'.
- **Map:** 64×40 tiles of grass, sand, water, rock and forest. Trees give wood, rocks stone, berry bushes food (and seeds);
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
