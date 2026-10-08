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
