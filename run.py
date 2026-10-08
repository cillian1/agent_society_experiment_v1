import argparse

from society import Society
from society.llm import make_llm
from society.society import default_agents, load_agents

p = argparse.ArgumentParser(description="Run a small society of communicating agents.")
p.add_argument("--rounds", type=int, default=3)
p.add_argument("--agents", help="JSON file defining agents (default: built-in 6)")
p.add_argument("--model", help="Claude model id (default: claude-haiku-5-5)")
p.add_argument("--mock", action="store_true", help="use offline mock LLM")
p.add_argument("--seed", type=int)
p.add_argument("--log", default="society_log.json")
args = p.parse_args()

agents = load_agents(args.agents) if args.agents else default_agents()
society = Society(agents, make_llm(args.mock, args.model), seed=args.seed)
society.run(args.rounds)
society.save_log(args.log)
