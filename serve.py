"""Launch the hub: simulation in a background thread + a web viewer."""
import argparse

from hub.server import serve
from society import Society
from society.cli import add_llm_args, apply_backends, build_llm, resolve_model
from society.llm import LOCAL
from society.society import default_agents, load_agents

p = argparse.ArgumentParser()
p.add_argument("--host", default="127.0.0.1")
p.add_argument("--port", type=int, default=8000)
p.add_argument("--agents", help="JSON file defining agents (default: built-in 6)")
p.add_argument("--max-agents", type=int, default=14, help="population cap (babies stop at this number)")
p.add_argument("--seed", type=int)
p.add_argument("--interval", type=float, default=1.0, help="min seconds between ticks")
add_llm_args(p)
args = p.parse_args()

llm = build_llm(args)
agents = load_agents(args.agents) if args.agents else default_agents()
apply_backends(agents, llm)
society = Society(agents, llm, seed=args.seed, max_agents=args.max_agents, baby_model=resolve_model(LOCAL, llm))
serve(society, args.host, args.port, args.interval)
