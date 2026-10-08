"""The world's history: a compact snapshot every few hours (for the replay slider) and Sol's monthly chronicle."""
from . import clock

SNAPSHOT_EVERY = 6           # hours
MAX_SNAPSHOTS = 4000


def snapshot(sim):
    if sim.tick % SNAPSHOT_EVERY:
        return
    sim.snapshots.append({
        "t": sim.tick,
        "a": [[a.name, a.x, a.y, a.color, a.stage(sim.tick)] for a in sim.agents.values()],
        "b": [[b["x"], b["y"], b["w"], b["h"], b["kind"], b.get("function") or "", int(b.get("done", True)), b.get("group") or 0]
              for b in sim.world.buildings.values()],
        "g": {str(g["id"]): [g["name"], g["color"], len(g["members"])] for g in sim.groups.values()},
        "pop": len(sim.agents),
    })
    if len(sim.snapshots) > MAX_SNAPSHOTS:            # thin out the older half
        half = len(sim.snapshots) // 2
        sim.snapshots = sim.snapshots[:half:2] + sim.snapshots[half:]


def chapter_due(sim) -> bool:
    """A new chapter at each review once a month has passed since the last one."""
    last = sim.chronicle[-1]["tick"] if sim.chronicle else -10 ** 9
    return sim.tick - last >= clock.DAYS_PER_MONTH * clock.DAY


def add_chapter(sim, data):
    if not isinstance(data, dict) or not str(data.get("title") or "").strip() or not str(data.get("text") or "").strip():
        return
    w = clock.when(sim.tick)
    sim.chronicle.append({"tick": sim.tick, "when": f"{w['month_name']}, year {w['year']}",
                          "title": str(data["title"])[:80], "text": str(data["text"])[:1200]})


def family(sim) -> list[dict]:
    """Everyone who ever lived, with parents, for the family tree."""
    people = list(sim.agents.values()) + [d["agent"] for d in sim.dead.values()]
    return [{"name": p.name, "parents": p.parents, "color": p.color, "sex": p.sex, "people": p.people,
             "alive": p.name in sim.agents, "born": p.born} for p in people]
