# agent_society_experiment_v1
Agents building a society

## Quick start
```
py -m pip install -r requirements.txt      # (python -m pip ... on Mac/Linux)
py serve.py                                # visual hub at http://127.0.0.1:8000
py run.py --ticks 10                       # headless: prints each agent's thoughts/actions
```
**Where do the agents' brains come from?** `serve.py` auto-detects what is available and shows it in the hub header:
- **Local model (free)** via [Ollama](https://ollama.com) - see below.
- **Claude** (Haiku / Sonnet / Opus) if the `ANTHROPIC_API_KEY` environment variable is set.
- If neither is found it falls back to a **scripted MOCK** (red banner in the hub): those agents cannot really think or reply.
  `--mock` forces this.

Default setup: **Ada and Fenn on Haiku, everyone else (and all babies) on the local model.** If you have no API key, everyone
uses the local model; if you have no local server, everyone uses Haiku. You can switch any agent to any model in the hub
(Local / Haiku / Sonnet / Enlighten=Opus, or type any model id; `local:<name>` for another local model). The memory summaries
use Haiku if there is a key, else the local model.

## Running local models (RTX 5070 Ti 16 GB, Windows)
1. Install Ollama, then `ollama pull qwen2.5:7b-instruct` (a good small instruction model; any Ollama model works via `--local-model`).
2. For many simultaneous agents set these environment variables, then restart Ollama (right-click tray icon > Quit, start again):
   - `OLLAMA_NUM_PARALLEL=20` - how many requests it serves at once (memory use = context size x this number).
   - `OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KV_CACHE_TYPE=q8_0` - halves the memory used by each conversation.
3. Start the hub with matching settings: `py serve.py --local-concurrency 20 --local-ctx 4096`
   (prompts are ~2-3k tokens, so 4096 is enough; `--local-ctx` is the per-request window).
4. Check `ollama ps` / Task Manager: the model should be 100% on GPU. If it spills to CPU, lower `OLLAMA_NUM_PARALLEL`
   (try 8-10), or use a smaller model (`qwen2.5:3b-instruct`). A day's speed is shown in the hub header (`Ns/day`).
Rough guide: a 7B 4-bit model is ~5 GB; each parallel conversation adds roughly 0.2-0.4 GB at 4k context, so ~20 in parallel
should fit in 16 GB - but this is an estimate, not a guarantee. LM Studio / llama.cpp / vLLM work too (`--local-api openai`).
Small local models are noticeably weaker at following the JSON format and at being creative; expect some wasted turns.

## The world
A procedurally generated 64x40 tile map (`society/world.py`): grass, sand, water, rock and forest (the last three impassable; trees give wood, rocks stone),
plus berry-bush **food** tiles that regrow 40 turns after being picked. Pass `--seed N` for a repeatable map.

## The agents
Six settlers (Ada, Brix, Cleo, Dov, Eli, Fenn) start with **nothing but a personality** (Big-Five traits), a random adult age,
and no roles, no goals beyond "survive and build a society", and no family. They invent their own roles (any agent can add
`"role": "..."` to a reply), talk, make friends, farm, build, invent customs and have children.
Each turn an agent sees a 13x13 ASCII window of the map, its stats, nearby agents, structures, feelings, ideas and its memory,
then returns a private *thought* plus one action: `move`, `gather` (food/wood/stone), `eat`, `say`, `give`, `plant`, `tend`,
`build` (anything: houses, signs, bridges... costs 2 wood/stone), `court`, `procreate`, `invent` or `wait`.
**They remember everything:** every notable event goes into a lifelong log; the newest ~25-45 lines are shown verbatim and older
ones are folded into a running summary by a cheap Haiku call, so nothing is lost but prompts stay small.
Ages are in days (1 turn = 1 day): adult at 40, elders may die of old age after 500.
Pass `--agents my.json` to define your own agents (name, traits, optional goal/role/model).

## The hub
Watch agents move on the map, with speech bubbles and a world feed. Click an agent (on the map or in the list)
to see its current thought and action, stats, and its full history of thoughts and actions. Pause/speed controls
are in the header. `serve.py --host 0.0.0.0 --port 8000` exposes it beyond localhost.

## Survival, farming, love and children
- **Scarce food:** wild bushes take 150 turns to regrow. At hunger 100 an agent loses health and can starve to death (🪦).
- **Farming (discovered, not taught):** picking a bush sometimes yields a seed. `plant` it on grass, then `tend` it. A second agent
  tending within 6 turns doubles the effect (teamwork); ripe crops give 3 food + a seed and replant themselves.
- **Imagination:** agents can `invent` ideas/customs/tools, which are shared with everyone (shown in the hub) and keep a
  long-term `remember` memory.
- **Love & children:** `court`, `give` and talking build a *bond*. When two adult, non-related agents each reach 50, both
  choose `procreate` (each pays 2 food) and a baby spawns. Population is capped (`--max-agents`, default 14).
- **Brains/cost tiers:** babies run on the free local model. In the hub's inspector pick any agent's brain: Local, Haiku, Sonnet,
  **Enlighten (Opus, only one agent at a time)** or any model id. More agents = more calls per turn.

## Talking to the agents
The **Talk** panel in the hub lets you message everyone, one agent, or any group (click the name chips, type, press Enter).
Each addressed agent answers immediately, in character and aware of its current situation, in a chat thread (one extra API
call per agent per message, on that agent's own model). The exchange is also saved in its history and memory for its next turn.
No restart needed for new messages.

## Usage counter
The hub header shows API calls and input/output tokens used this run (hover for a per-model breakdown).
For a dollar estimate, give prices in USD per million tokens: `python serve.py --price claude-haiku-5-5=IN,OUT --price claude-opus-5-5=IN,OUT`
(the estimate appears only when every model in use has a price; look up current prices in the Anthropic docs).
