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
p.add_argument("--price", action="append", default=[], metavar="MODEL=IN,OUT",
               help="USD per million tokens, to show a $ estimate (repeatable), e.g. claude-haiku-5-5=1,5")
p.add_argument("--max-agents", type=int, default=14, help="population cap (babies stop at this number)")
p.add_argument("--seed", type=int)
p.add_argument("--interval", type=float, default=1.0, help="min seconds between ticks")
args = p.parse_args()

prices = {m: tuple(map(float, v.split(","))) for m, v in (x.split("=") for x in args.price)}
agents = load_agents(args.agents) if args.agents else default_agents()
society = Society(agents, make_llm(args.mock, args.model, prices), seed=args.seed, max_agents=args.max_agents)
serve(society, args.host, args.port, args.interval)
