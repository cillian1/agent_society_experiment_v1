"""Sol as referee (the 'game master'): an impartial judge that judges anything an agent tries ('attempt') or invents, and
turns it into concrete, bounded changes to the world. Whatever it says is checked and clamped here, so a
generous or confused referee can't break the simulation."""
import json
import re

from .config import DISCOVERY_COOLDOWN, EFFECTS, FUNCTIONS, MAX_BUILD_COST, MAX_ITEMS
from .mind import DIRS, _json

USES = ("wood", "stone", "farm", "fish", "none")


def _context(sim, a) -> str:
    w = sim.world
    near = {}
    for y in range(a.y - 2, a.y + 3):
        for x in range(a.x - 2, a.x + 3):
            if w.in_bounds(x, y):
                near[w.tiles[y][x]] = near.get(w.tiles[y][x], 0) + 1
    disc = "; ".join(f"{d['name']} ({EFFECTS[d['effect']][0].replace('N', str(d['amount']))})" for d in sim.discoveries) or "none yet"
    from .clock import age_text, stamp
    return (f"{stamp(sim.tick)}. {a.name}, a {a.word(sim.tick)}, {age_text(a.age(sim.tick))} old"
            + (f", the {a.role}" if a.role else "") + f". Abilities: {a.abilities.describe()}.\n"
            f"Carrying: {a.food} food, {a.seeds} seeds, {a.wood} wood, {a.stone} stone; objects: "
            f"{', '.join(i['name'] for i in a.items) or 'none'}. Hunger {int(a.hunger)}/100, health {int(a.health)}/100.\n"
            f"Terrain within 2 tiles: {', '.join(f'{v} {k}' for k, v in near.items())}. "
            f"Others nearby: {', '.join(o.name for o in sim.agents.values() if o is not a and a.dist(o) <= 4) or 'nobody'}.\n"
            f"The society's discoveries so far: {disc}.")


def judge(sim, a, act: dict) -> dict | None:
    """Ask the referee what happens. Runs outside the simulation lock (it's a model call)."""
    what = act.get("what") or act.get("message") or act.get("title") or ""
    if not what.strip():
        return None
    kind = "invents / proposes" if act["action"] == "invent" else "tries to"
    recent = a.history and sim.tick - max((d["tick"] for d in sim.discoveries if d["by"] == a.name), default=-999) < DISCOVERY_COOLDOWN
    effects = "\n".join(f'  "{k}": {v[0]} (amount up to {v[1]})' for k, v in EFFECTS.items())
    prompt = (f"GAME_MASTER\n{_context(sim, a)}\n\n{a.name} {kind}: \"{what[:400]}\"\n\n"
              "You are Sol, the wise mentor who also acts as the fair, imaginative referee of this world. Anything is "
              "possible if it is plausible for a "
              "small stone-age society with these resources and abilities. Decide what happens. Reward creativity and "
              "effort; real progress usually needs materials, time, cooperation or skill. Failures can be interesting."
              f"\nA DISCOVERY permanently helps the whole society. Only grant one for a genuinely new, useful idea that "
              f"isn't already discovered{' (this person discovered something very recently: no new discovery now)' if recent else ''}. "
              f"Allowed discovery effects:\n{effects}\n"
              "Reply ONLY with JSON (use null / 0 for anything that doesn't apply):\n"
              '{"success": true, "story": "<1-2 vivid sentences of what happened>", '
              '"gain": {"food": 0, "seeds": 0, "wood": 0, "stone": 0}, "cost": {"food": 0, "seeds": 0, "wood": 0, "stone": 0}, '
              '"item": {"name": "...", "description": "...", "use": "wood|stone|farm|fish|none"}, '
              '"structure": {"kind": "...", "description": "..."}, '
              '"discovery": {"name": "...", "description": "...", "effect": "<one key above>", "amount": 1}, '
              '"hunger": 0, "health": 0}')
    model = sim.sol_model
    data = _json(sim.llm.complete("You are Sol, mentor and referee of a society simulation. Be fair, vivid and concise.",
                                  prompt, model=model))
    return data or None


def design(sim, a, kind: str, idea: str) -> dict | None:
    """A new kind of building: decide what it costs and what it does (once - then everyone knows)."""
    if not (kind or "").strip():
        return None
    funcs = "\n".join(f'  "{k}": {v[1]}' for k, v in FUNCTIONS.items())
    known = "; ".join(f"{b['kind']}: {', '.join(f'{v} {k}' for k, v in b['cost'].items())}"
                      for b in list(sim.blueprints.values())[-8:]) or "none yet"
    prompt = (f"GAME_MASTER_BLUEPRINT\n{_context(sim, a)}\n\n{a.name} wants to build a \"{kind[:60]}\""
              + (f" ({idea[:160]})" if idea else "") + ".\nKnown buildings and their costs: " + known + "\n"
              "As Sol, the referee of this world, design what it takes for a small stone-age society: materials (wood, stone, food; "
              f"0-{MAX_BUILD_COST} each - bigger or cleverer buildings cost more) and what it does. Pick the function "
              f"that fits best, or none if it is decorative or cultural:\n{funcs}\n"
              "Also choose its size in tiles, [width, height], from [1, 1] (a well, a sign) to [3, 3] (a hall, a temple); "
              "people can walk inside buildings.\n"
              'Reply ONLY with JSON: {"cost": {"wood": 0, "stone": 0, "food": 0}, "function": "<key or none>", '
              '"size": [2, 2], "description": "<what it is and does, one sentence>"}')
    data = _json(sim.llm.complete("You are Sol, mentor and referee of a society simulation. Be fair and concise.",
                                  prompt, model=sim.sol_model))
    return data or None


def _num(v, lo, hi) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return 0


def apply_outcome(sim, a, act: dict, out: dict, tick: int) -> str:
    """Turn the referee's verdict into bounded changes. Returns the result the agent sees."""
    what = (act.get("what") or act.get("message") or act.get("title") or "something")[:160]
    story = str(out.get("story") or "").strip()[:300] or ("It worked." if out.get("success") else "It didn't work.")
    ok = bool(out.get("success"))
    notes = []
    cost = out.get("cost") if isinstance(out.get("cost"), dict) else {}
    for k in ("food", "seeds", "wood", "stone"):                      # pay what you can
        pay = int(min(getattr(a, k), _num(cost.get(k), 0, 5)))
        if pay:
            setattr(a, k, getattr(a, k) - pay)
            notes.append(f"-{pay} {k}")
    if ok:
        gain = out.get("gain") if isinstance(out.get("gain"), dict) else {}
        for k in ("food", "seeds", "wood", "stone"):
            g = int(_num(gain.get(k), 0, 3))
            if g:
                setattr(a, k, getattr(a, k) + g)
                notes.append(f"+{g} {k}")
        a.hunger = _num(a.hunger + _num(out.get("hunger"), -40, 20), 0, 100)
        a.health = _num(a.health + _num(out.get("health"), -20, 10), 1, 100)
        item = out.get("item") if isinstance(out.get("item"), dict) else None
        if item and str(item.get("name") or "").strip() and len(a.items) < MAX_ITEMS:
            name = str(item["name"]).strip()[:30]
            use = item.get("use") if item.get("use") in USES else "none"
            a.items.append({"name": name, "text": str(item.get("description") or "")[:120], "by": a.name, "tick": tick,
                            "use": use})
            notes.append(f"made a {name}")
            sim.event(tick, a, f"made a {name}", "craft")
        st = out.get("structure") if isinstance(out.get("structure"), dict) else None
        if st and str(st.get("kind") or "").strip():
            from .actions import place_building
            kind = str(st["kind"])[:40]
            b, _ = place_building(sim, a, kind, str(st.get("description") or "")[:160], sim.blueprint(kind, None, a.name, tick),
                                  None, tick)
            if b:
                notes.append(f"built a {kind}")
                sim.event(tick, a, f"built a {kind} at ({b['x']}, {b['y']})", "build")
        d = out.get("discovery") if isinstance(out.get("discovery"), dict) else None
        if d and d.get("effect") in EFFECTS and str(d.get("name") or "").strip():
            name = str(d["name"]).strip()[:50]
            recent = tick - max((x["tick"] for x in sim.discoveries if x["by"] == a.name), default=-999) < DISCOVERY_COOLDOWN
            if not recent and not any(x["name"].lower() == name.lower() for x in sim.discoveries):
                amount = _num(d.get("amount") or EFFECTS[d["effect"]][1], 0, EFFECTS[d["effect"]][1])
                disc = {"name": name, "description": str(d.get("description") or "")[:200], "effect": d["effect"],
                        "amount": round(amount, 2), "by": a.name, "tick": tick, "color": a.color}
                sim.discoveries.append(disc)
                meaning = EFFECTS[d["effect"]][0].replace("N", str(disc["amount"]))
                notes.append(f"DISCOVERY: {name} ({meaning})")
                sim.event(tick, a, f'discovered "{name}" - {disc["description"]} ({meaning})', "discovery")
                for o in sim.agents.values():
                    o.heard.append(f'{a.name} discovered "{name}": {disc["description"]} ({meaning}).')
                    o.remember(tick, f'{a.name} discovered "{name}" ({meaning}).' if o is not a
                               else f'I discovered "{name}"! ({meaning})')
    a.remember(tick, f"I tried to {what}. {story}")
    if not (out.get("discovery") and ok):
        sim.event(tick, a, f"tried to {what} - {story}", "attempt")
    return ("Success! " if ok else "Didn't work out. ") + story + (f" ({', '.join(notes)})" if notes else "")
