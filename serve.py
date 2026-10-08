"""Start the hub: the simulation runs in the background, open http://127.0.0.1:8000 to watch and interact."""
import argparse
from pathlib import Path

from hub.server import Hub, serve
from society import Society, default_agents, load_agents, persistence
from society.cli import add_llm_args, apply_backends, build_llm, resolve_model
from society.config import DEFAULT_MAX_AGENTS, LOCAL

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--host", default="127.0.0.1")
p.add_argument("--port", type=int, default=8000)
p.add_argument("--agents", help="JSON file defining the starting agents (default: built-in 6)")
p.add_argument("--max-agents", type=int, default=DEFAULT_MAX_AGENTS, help="population cap")
p.add_argument("--seed", type=int, help="world seed (same seed = same map)")
p.add_argument("--interval", type=float, default=0.8, help="seconds per hour of world time")
p.add_argument("--max-wait", type=float, default=0.8,
               help="max seconds a day waits for slow brains (they act a little later instead)")
p.add_argument("--load", metavar="NAME", help="start from a save in ./saves (e.g. autosave)")
p.add_argument("--resume", action="store_true", help="continue from the latest autosave if there is one")
p.add_argument("--no-autosave", action="store_true", help="don't autosave every few days")
p.add_argument("--sol-model", default="local", help="Sol's brain: local, haiku, sonnet, opus or a model id")
add_llm_args(p)
args = p.parse_args()

llm = build_llm(args)


def new_world(seed=None) -> Society:
    agents = load_agents(args.agents) if args.agents else default_agents()
    apply_backends(agents, llm)
    return Society(agents, llm, seed=seed, max_agents=args.max_agents, baby_model=resolve_model(LOCAL, llm))


def load_world(name: str) -> Society:
    sim = persistence.load(name, llm)
    apply_backends(list(sim.agents.values()), llm)          # e.g. Haiku agents fall back to local without a key
    sim.baby_model = resolve_model(sim.baby_model, llm)
    return sim


def sol_brain() -> str:
    names = {"local": "local", "smart": "local", "haiku": "claude-haiku-5-5",
             "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}
    return resolve_model(names.get(args.sol_model, args.sol_model), llm)


_new, _load = new_world, load_world
new_world = lambda seed=None: _with_sol(_new(seed))
load_world = lambda name: _with_sol(_load(name))


def _with_sol(sim: Society) -> Society:
    sim.sol_model = sol_brain()
    return sim


start = args.load or ("autosave" if args.resume and Path("saves/autosave.json").exists() else None)
society = load_world(start) if start else new_world(args.seed)
if start:
    print(f"Loaded '{start}' at day {society.tick}")
serve(Hub(society, new_world, load_world, args.interval, args.max_wait, autosave=not args.no_autosave), args.host, args.port)
