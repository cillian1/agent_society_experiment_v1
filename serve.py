"""Launch the hub: simulation in a background thread + a web viewer."""
import argparse

from hub.server import serve
from society import Society
from society.llm import make_llm
from society.society import default_agents, load_agents

p = argparse.ArgumentParser()
p.add_argument("--host", default="127.0.0.1")
p.add_argument("--port", type=int, default=8000)
p.add_argument("--agents", help="JSON file defining agents (default: built-in 6)")
p.add_argument("--model", help="default Claude model id (default: claude-haiku-5-5)")
p.add_argument("--mock", action="store_true", help="use offline mock LLM")
p.add_argument("--seed", type=int)
p.add_argument("--interval", type=float, default=1.0, help="min seconds between ticks")
args = p.parse_args()

agents = load_agents(args.agents) if args.agents else default_agents()
society = Society(agents, make_llm(args.mock, args.model), seed=args.seed)
serve(society, args.host, args.port, args.interval)
