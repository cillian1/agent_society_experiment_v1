"""Headless run: print each agent's thoughts/actions per tick (use serve.py for the visual hub)."""
import argparse

from society import Society
from society.cli import add_llm_args, apply_backends, build_llm, resolve_model
from society.llm import LOCAL
from society.society import default_agents, load_agents

p = argparse.ArgumentParser()
p.add_argument("--ticks", type=int, default=10)
p.add_argument("--agents", help="JSON file defining agents (default: built-in 6)")
p.add_argument("--max-agents", type=int, default=14)
p.add_argument("--seed", type=int)
p.add_argument("--log", default="society_log.json")
add_llm_args(p)
args = p.parse_args()

llm = build_llm(args)
agents = load_agents(args.agents) if args.agents else default_agents()
apply_backends(agents, llm)
society = Society(agents, llm, seed=args.seed, max_agents=args.max_agents, baby_model=resolve_model(LOCAL, llm))
society.run(args.ticks)
society.save_log(args.log)
