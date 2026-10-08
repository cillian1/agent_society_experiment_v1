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
`--local-concurrency 20`, `--interval 2` (minimum seconds per day). `py serve.py --help` lists everything.
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
1. Install Ollama, then `ollama pull qwen2.5:7b-instruct`.
2. For many agents at once: `setx OLLAMA_NUM_PARALLEL 20`, `setx OLLAMA_FLASH_ATTENTION 1`, `setx OLLAMA_KV_CACHE_TYPE q8_0`,
   then quit and restart Ollama.
3. `py serve.py --local-concurrency 20`. Check `ollama ps` shows `100% GPU`; if not, lower `OLLAMA_NUM_PARALLEL`
   or use `qwen2.5:3b-instruct`. LM Studio / llama.cpp / vLLM work too (`--local-api openai --local-url ...`).

## Using the hub
| Where | What you can do |
|---|---|
| **Top bar** | Day, brains, population, % explored, seconds per day, model usage. Pause / step one day / speed. `?` = help. |
| **Map** | Scroll to zoom, drag to pan, click an agent to open their profile, double-click to follow. Fog of war lifts as they explore. Speech bubbles show who talks to whom. |
| **👥 People** | Everyone at a glance (hunger, food, age, what they're doing). A **profile** has Overview, Thoughts (every decision), Memory, Relations (feelings & family) and Brain tabs, plus buttons to talk, find, follow or send a gift. |
| **💬 Talk** | Message everyone, one agent or any group; each answers right away in character. Choose whether they treat you as their **leader** (they obey), an advisor, or an observer. |
| **🌍 World** | A filterable feed of conversations, births and deaths, building, ideas, exploration and food. |
| **📈 Stats** | Population, hunger, food, exploration, structures, farms, objects and ideas over time (hover to read a day; table view available). |
| **⚙️ Settings** | Save / load worlds (also autosaved every 25 days), start a new world, model usage per brain, keyboard shortcuts. |

Keyboard: `Space` pause · `N` next day · `+`/`−` zoom · `0` fit · `F` follow · `/` talk · `Esc` close · `1`–`5` tabs · `?` help.

## How the world works
- **Map:** 64×40 tiles of grass, sand, water, rock and forest. Trees give wood, rocks stone, berry bushes food (and seeds);
  bushes take 150 days to regrow.
- **Survival:** hunger rises every day; at 100 an agent loses health and can starve. Elders (500+ days) may die of old age.
- **Farming:** plant a seed, tend it; a second farmer within 6 days doubles the growth. Ripe crops give 3 food and replant.
- **Making things:** `build` anything (houses, signs, bridges — bridges can cross water) and `craft` objects. Tools work:
  axe = more wood, pickaxe = more stone, hoe = faster crops, fishing rod/net = fish from water.
- **Society:** no roles or family at the start. Agents claim their own roles, `invent` ideas everyone hears about, build
  friendships by talking, giving and farming together, and when two adults love each other (50+ both ways) they can have
  a child, who inherits a mix of their personalities.
- **Memory:** everything notable goes into each agent's lifelong log; older memories are folded into a running summary
  so prompts stay small and nothing is forgotten.

## Project layout
```
serve.py / run.py        start the hub / run headless (`py run.py --days 50 --save test`)
society/
  config.py              every tunable number (costs, ages, radii, regrowth...)
  world.py               map generation, resources, farming, structures, fog of war
  models.py              Agent and Traits data
  mind.py                prompts, parsing the model's JSON, calling the model
  actions.py             what each action does (one function per action)
  engine.py              the day loop, life & death, the Human's interactions, stats, save state
  views.py               JSON sent to the hub
  persistence.py         save / load / list saves (./saves)
  llm.py, mock.py, cli.py  model backends (Claude, local, router), the offline mock, command-line options
hub/server.py            HTTP server + simulation thread
hub/static/              index.html, style.css, app.js (no build step)
tests/                   `python -m unittest`
```
**Adding an action:** write a function in `society/actions.py` decorated with `@action("name")`, add the name to
`ACTIONS` and a one-line description in `system_prompt` in `society/mind.py`.

## Cost
The top bar and ⚙️ Settings show calls and tokens per model. Local models are free. For a dollar estimate start with
`--price claude-haiku-5-5=IN,OUT` (USD per million tokens, from Anthropic's pricing page). Each agent makes one call per
day (plus one per message you send it), so more agents and a shorter `--interval` cost more.
