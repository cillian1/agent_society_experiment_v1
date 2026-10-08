"""JSON views of a society for the hub: a light state for polling, and full detail for one agent."""
from .config import ADULT_AGE, LOVE_BOND, OLD_AGE
from .engine import Society, tier_of
from .models import Agent


def _brief(sim: Society, a: Agent) -> dict:
    t = sim.tick
    latest = a.history[-1] if a.history else None
    return {
        "name": a.name, "color": a.color, "role": a.role, "model": a.model, "tier": tier_of(a.model), "sex": a.sex,
        "pregnant": bool(a.pregnancy), "due": a.pregnancy["due"] if a.pregnancy else None,
        "x": a.x, "y": a.y, "hunger": int(a.hunger), "health": int(a.health), "food": a.food,
        "age": a.age(t), "stage": a.stage(t), "adult": a.adult(t),
        "say": a.last_say if t - a.last_say_tick <= 3 else "", "say_to": a.last_say_to,
        "heart": t - a.heart_tick <= 3,
        "doing": f"{latest['action']} → {latest['result']}" if latest else "",
    }


def state(sim: Society, since_event: int = 0) -> dict:
    """Everything the hub redraws every half second (kept small)."""
    with sim.lock:
        return {
            "day": sim.tick, "day_seconds": sim.tick_seconds,
            "agents": [_brief(sim, a) for a in sim.agents.values()],
            "dead": [{"name": n, "x": d["agent"].x, "y": d["agent"].y, "died": d["tick"], "cause": d["cause"],
                      "age": d["agent"].age(d["tick"]), "color": d["agent"].color} for n, d in sim.dead.items()],
            "events": sim.events[-80:],
            "chat": sim.chat[-60:],
            "talk": sim.talk[-60:],
            "inventions": sim.inventions[-40:],
            "structures": [{"x": x, "y": y, "kind": s["kind"], "text": s["text"], "by": s["by"], "walkable": s["walkable"]}
                           for (x, y), s in sim.world.structures.items()],
            "explored": sim.world.explored_pct(),
            "authority": sim.human_authority,
            "usage": sim.llm.usage(),
            "backends": sim.llm.info() if hasattr(sim.llm, "info") else {},
            "errors": sim.errors[-5:],
            "limits": {"max_agents": sim.max_agents, "adult_age": ADULT_AGE, "love": LOVE_BOND, "old_age": OLD_AGE},
            "tiles": [row[:] for row in sim.world.tiles],
            "fog": sim.world.explored_rows(),
        }


def agent_detail(sim: Society, name: str) -> dict | None:
    """Full picture of one agent (alive or dead) for the inspector."""
    with sim.lock:
        a = sim.agents.get(name)
        dead = sim.dead.get(name)
        if not a and not dead:
            return None
        a = a or dead["agent"]
        t = sim.tick
        return {
            **_brief(sim, a), "alive": not dead, "goal": a.goal, "traits": vars(a.traits),
            "seeds": a.seeds, "wood": a.wood, "stone": a.stone, "items": a.items, "discoveries": a.discoveries,
            "parents": a.parents, "children": a.children, "pregnancy": a.pregnancy,
            "bonds": {k: int(v) for k, v in sorted(a.bonds.items(), key=lambda kv: -kv[1]) if v >= 1},
            "summary": a.summary, "log": a.log[-60:], "log_total": len(a.log),
            "orders": [o for o in a.orders if t - o[0] <= 30],
            "history": a.history[-150:], "history_total": len(a.history),
            "died": dead["tick"] if dead else None, "cause": dead["cause"] if dead else None,
            "age": a.age(dead["tick"] if dead else t),
        }
