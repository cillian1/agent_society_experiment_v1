"""Headless run: print every agent's thoughts and actions each day (use serve.py for the visual hub)."""
import argparse

from society import Society, default_agents, load_agents, persistence
from society.cli import add_llm_args, apply_backends, build_llm, resolve_model
from society.config import DEFAULT_MAX_AGENTS, LOCAL

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--days", "--ticks", type=int, default=10, dest="days")
p.add_argument("--agents", help="JSON file defining the starting agents (default: built-in 6)")
p.add_argument("--max-agents", type=int, default=DEFAULT_MAX_AGENTS)
p.add_argument("--seed", type=int)
p.add_argument("--save", metavar="NAME", help="save the result to ./saves/NAME.json (open it in the hub with --load)")
add_llm_args(p)
args = p.parse_args()

llm = build_llm(args)
agents = load_agents(args.agents) if args.agents else default_agents()
apply_backends(agents, llm)
society = Society(agents, llm, seed=args.seed, max_agents=args.max_agents, baby_model=resolve_model(LOCAL, llm))
society.run(args.days)
if args.save:
    print("saved to", persistence.save(society, args.save))
