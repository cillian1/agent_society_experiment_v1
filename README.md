# agent_society_experiment_v1
Agents building a society

## Quick start
```
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...     # omit (or pass --mock) to use the offline mock
python serve.py                  # visual hub at http://127.0.0.1:8000
python run.py --ticks 10         # headless: prints each agent's thoughts/actions
```

## The world
A procedurally generated 40x26 tile map (`society/world.py`): grass, sand, water and rock (the last two impassable),
plus berry-bush **food** tiles that regrow 40 turns after being picked. Pass `--seed N` for a repeatable map.

## The agents
Six agents (Ada/Leader, Brix/Builder, Cleo/Explorer, Dov/Trader, Eli/Skeptic, Fenn/Mediator on `claude-opus-5-5`)
with roles, goals, skills and Big-Five traits (`society/society.py`). Each turn an agent sees an 11x11 ASCII window
of the map, its hunger, nearby agents and messages, then returns a private *thought* plus one action:
`move`, `gather`, `eat`, `say` (heard within 8 tiles), `give` (food to an adjacent agent) or `wait`.
Pass `--agents my.json` to define your own agents (name, role, goal, traits, skills, model).

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
- **Brains/cost tiers:** babies run on Haiku (cheap). In the hub's inspector, **Upgrade to Sonnet** or **Enlighten (Opus)**:
  only one agent can be Opus at a time; Fenn starts enlightened. More agents = more API calls per turn.

## Talking to the agents
The **Talk** panel in the hub lets you message everyone, one agent, or any group (click the name chips, type, press Enter).
Each addressed agent answers immediately, in character and aware of its current situation, in a chat thread (one extra API
call per agent per message, on that agent's own model). The exchange is also saved in its history and memory for its next turn.
No restart needed for new messages.

## Usage counter
The hub header shows API calls and input/output tokens used this run (hover for a per-model breakdown).
For a dollar estimate, give prices in USD per million tokens: `python serve.py --price claude-haiku-5-5=IN,OUT --price claude-opus-5-5=IN,OUT`
(the estimate appears only when every model in use has a price; look up current prices in the Anthropic docs).
