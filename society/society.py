import json
import random
from pathlib import Path

from .agent import Agent, Traits


def default_agents() -> list[Agent]:
    return [
        Agent("Ada", "Leader", "Organise the group and keep everyone working toward a shared plan.",
              Traits(0.6, 0.8, 0.9, 0.6, 0.2), ["planning", "persuasion"]),
        Agent("Brix", "Builder", "Construct shelter and infrastructure efficiently.",
              Traits(0.4, 0.9, 0.4, 0.5, 0.3), ["construction", "engineering"]),
        Agent("Cleo", "Explorer", "Discover new resources and ideas beyond the settlement.",
              Traits(0.95, 0.3, 0.7, 0.6, 0.4), ["scouting", "mapping"]),
        Agent("Dov", "Trader", "Grow your own wealth through deals; trade resources for advantage.",
              Traits(0.5, 0.6, 0.7, 0.2, 0.5), ["negotiation", "accounting"]),
        Agent("Eli", "Skeptic", "Question plans, find flaws, and protect the group from bad decisions.",
              Traits(0.7, 0.7, 0.3, 0.2, 0.7), ["critical thinking", "history"]),
    ]


def load_agents(path: str) -> list[Agent]:
    """Load agents from a JSON list of {name, role, goal, traits{...}, skills[], resources}."""
    out = []
    for d in json.loads(Path(path).read_text()):
        d["traits"] = Traits(**d.get("traits", {}))
        out.append(Agent(**d))
    return out


class Society:
    def __init__(self, agents: list[Agent], llm, seed: int | None = None):
        self.agents = {a.name: a for a in agents}
        self.llm = llm
        self.rng = random.Random(seed)
        self.log: list[dict] = []

    def step(self, round_no: int):
        order = list(self.agents.values())
        self.rng.shuffle(order)
        for agent in order:
            others = [n for n in self.agents if n != agent.name]
            msg = agent.act(self.llm, others)
            # deliver: everyone hears public messages; only the target hears private ones
            for a in self.agents.values():
                if msg["to"] == "all" or a.name in (msg["to"], agent.name):
                    a.hear(agent.name, msg["to"], msg["message"])
            entry = {"round": round_no, "from": agent.name, **msg}
            self.log.append(entry)
            print(f"[{round_no}] {agent.name} ({agent.role}) -> {msg['to']}: {msg['message']}")

    def run(self, rounds: int):
        for r in range(1, rounds + 1):
            self.step(r)

    def save_log(self, path: str):
        Path(path).write_text(json.dumps(self.log, indent=2))
