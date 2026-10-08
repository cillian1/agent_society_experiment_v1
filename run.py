"""Headless run: print each agent's thoughts/actions per tick (use serve.py for the visual hub)."""
import argparse

from society import Society
from society.llm import make_llm
from society.society import default_agents, load_agents

p = argparse.ArgumentParser()
p.add_argument("--ticks", type=int, default=10)
p.add_argument("--agents", help="JSON file defining agents (default: built-in 6)")
p.add_argument("--model", help="default Claude model id (default: claude-haiku-5-5)")
p.add_argument("--mock", action="store_true", help="use offline mock LLM")
p.add_argument("--max-agents", type=int, default=14)
p.add_argument("--seed", type=int)
p.add_argument("--log", default="society_log.json")
args = p.parse_args()

agents = load_agents(args.agents) if args.agents else default_agents()
society = Society(agents, make_llm(args.mock, args.model), seed=args.seed, max_agents=args.max_agents)
society.run(args.ticks)
society.save_log(args.log)
