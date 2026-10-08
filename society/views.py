"""JSON views of a society for the hub: a light state for polling, and full detail for one agent."""
from . import clock
from .config import ADULT_AGE, EFFECTS, FUNCTIONS, LOVE_BOND, OLD_AGE
from .engine import Society, tier_of
from .models import ABILITY_INFO, TRAIT_INFO, Agent


def _task(sim: Society, a: Agent):
    site = sim.world.buildings.get((a.task or {}).get("id")) if a.task else None
    if not site or site.get("done", True):
        return None
    return {"label": f"Building {site['kind']}", "progress": round(site["progress"], 1), "total": site["work"]}


def _brief(sim: Society, a: Agent) -> dict:
    t = sim.tick
    latest = a.history[-1] if a.history else None
    return {
        "name": a.name, "color": a.color, "role": a.role, "model": a.model, "tier": tier_of(a.model), "sex": a.sex,
        "pregnant": bool(a.pregnancy), "due": a.pregnancy["due"] if a.pregnancy else None,
        "x": a.x, "y": a.y, "hunger": int(a.hunger), "health": int(a.health), "food": a.food,
        "age": a.age(t), "age_text": clock.age_text(a.age(t)), "stage": a.stage(t), "adult": a.adult(t),
        "asleep": clock.is_night(t), "dreaming": bool(a.last_dream) and t - a.last_dream[0] <= 1,
        "say": a.last_say if t - a.last_say_tick <= 3 else "", "say_to": a.last_say_to,
        "heart": t - a.heart_tick <= 3,
        "doing": f"{latest['action']} → {latest['result']}" if latest else "",
        "inside": (sim.world.building_at(a.x, a.y) or {}).get("kind", ""),
        "task": _task(sim, a),
    }


def state(sim: Society, since_event: int = 0) -> dict:
    """Everything the hub redraws every half second (kept small)."""
    with sim.lock:
        return {
            "day": sim.tick, "day_seconds": sim.tick_seconds,
            "time": {**clock.when(sim.tick), "stamp": clock.stamp(sim.tick), "part": clock.part_of_day(sim.tick),
                     "night": clock.is_night(sim.tick)},
            "calendar": clock.calendar(),
            "agents": [_brief(sim, a) for a in sim.agents.values()],
            "dead": [{"name": n, "x": d["agent"].x, "y": d["agent"].y, "died": d["tick"], "cause": d["cause"],
                      "age": d["agent"].age(d["tick"]), "age_text": clock.age_text(d["agent"].age(d["tick"])),
                      "color": d["agent"].color} for n, d in sim.dead.items()],
            "events": sim.events[-80:],
            "chat": sim.chat[-60:],
            "talk": sim.talk[-60:],
            "inventions": sim.inventions[-40:],
            "blueprints": list(sim.blueprints.values()),
            "discoveries": [{**d, "meaning": EFFECTS[d["effect"]][0].replace("N", str(d["amount"]))} for d in sim.discoveries],
            "sol": {"model": sim.sol_model, "last": sim.sol_last, "next_in": max(0, sim.sol_next - sim.tick),
                    "next_at": clock.stamp(sim.sol_next) if sim.sol_next >= sim.tick else "soon",
                    "log": sim.sol_log[-5:]},
            "structures": [{"x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"], "kind": b["kind"], "text": b["text"],
                            "by": b["by"], "walkable": b["walkable"], "func": b.get("function") or "",
                            "function": FUNCTIONS[b["function"]][1] if b.get("function") else "", "stock": b.get("stock"),
                            "done": b.get("done", True), "progress": round(b.get("progress", 0), 1), "work": b.get("work", 0)}
                           for b in sim.world.buildings.values()],
            "explored": sim.world.explored_pct(),
            "authority": sim.human_authority, "think_every": sim.think_every,
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
            **_brief(sim, a), "alive": not dead, "goal": a.goal, "traits": vars(a.traits), "trait_info": TRAIT_INFO, "last_dream": a.last_dream,
            "seeds": a.seeds, "wood": a.wood, "stone": a.stone, "items": a.items, "discoveries": a.discoveries,
            "parents": a.parents, "children": a.children, "pregnancy": a.pregnancy, "plan": a.plan, "ambition": a.ambition, "queue": a.queue,
            "advice": [x for x in a.advice if t - x[0] <= 20][-3:],
            "abilities": vars(a.abilities), "ability_info": ABILITY_INFO, "lifespan": a.abilities.lifespan(),
            "bonds": {k: int(v) for k, v in sorted(a.bonds.items(), key=lambda kv: -kv[1]) if v >= 1},
            "summary": a.summary, "log": a.log[-60:], "log_total": len(a.log),
            "orders": [o for o in a.orders if t - o[0] <= 30],
            "history": a.history[-150:], "history_total": len(a.history),
            "died": dead["tick"] if dead else None, "cause": dead["cause"] if dead else None,
            "age": a.age(dead["tick"] if dead else t), "age_text": clock.age_text(a.age(dead["tick"] if dead else t)),
            "lifespan_text": clock.age_text(a.abilities.lifespan() * 24),
        }
