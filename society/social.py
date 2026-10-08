"""How people live together: deals and promises (trust and reputation), groups with leaders and shared plans, and
laws that bind - noticed by witnesses, answered with punishment, forgiveness or exile."""
import re

from . import clock

RES = ("food", "seeds", "wood", "stone")
OFFER_HOURS = 8               # an offer stands this long
DEFAULT_DUE = 24              # hours to deliver if nobody said
WITNESS_RADIUS = 6
TERRITORY = 4                 # tiles around a group's buildings that count as its land
GROUP_COLORS = ["#e76f51", "#2a9d8f", "#e9c46a", "#8ab17d", "#9d4edd", "#f4a261", "#457b9d", "#d62828"]


def bundle(x) -> dict:
    """{"food": 2} or "2 food, 1 wood" -> {"food": 2, "wood": 1} (resources only)."""
    out = {}
    if isinstance(x, dict):
        items = x.items()
    else:
        items = [(m.group(2), m.group(1)) for m in re.finditer(r"(\d+)\s*(food|seeds?|wood|stones?)", str(x or "").lower())]
    for k, v in items:
        k = str(k).lower().rstrip("s") if str(k).lower() not in ("seeds",) else "seeds"
        k = {"seed": "seeds", "stone": "stone", "wood": "wood", "food": "food"}.get(k, k)
        try:
            n = int(float(v))
        except (TypeError, ValueError):
            continue
        if k in RES and n > 0:
            out[k] = out.get(k, 0) + min(n, 20)
    return out


def text(b: dict) -> str:
    return ", ".join(f"{v} {k}" for k, v in b.items()) or "nothing"


def has(a, b: dict) -> bool:
    return all(getattr(a, k) >= v for k, v in b.items())


def move(src, dst, b: dict):
    for k, v in b.items():
        setattr(src, k, getattr(src, k) - v)
        setattr(dst, k, getattr(dst, k) + v)


def reputation(a) -> str:
    if a.broken >= 2 and a.broken > a.kept:
        return f"known to break promises ({a.broken} broken)"
    if a.kept >= 3 and a.broken == 0:
        return f"known to keep their word ({a.kept} promises kept)"
    return ""


# ================================================================ deals & promises
def offer(sim, a, o, give: dict, want: dict, within: int, tick: int) -> str:
    if not give and not want:
        return "an offer needs something: give (what you hand over) and/or want (what you ask for)"
    if not has(a, give):
        return f"you don't have {text(give)} to offer"
    d = {"id": sim.next_id("deal"), "from": a.name, "to": o.name, "give": give, "want": want,
         "within": max(0, min(72, int(within or 0))), "tick": tick, "status": "open"}
    sim.deals.append(d)
    del sim.deals[:-60]
    when = "now" if not d["within"] else f"within {d['within']} hours"
    o.heard.append(f'{a.name} offers you {text(give)} for {text(want)} ({when}). Answer with accept or decline, target "{d["id"]}".')
    a.remember(tick, f"I offered {o.name} {text(give)} for {text(want)} ({when}).")
    return f"offered {o.name} {text(give)} for {text(want)} (deal {d['id']}); waiting for their answer"


def open_offers(sim, a, tick) -> list[dict]:
    return [d for d in sim.deals if d["to"] == a.name and d["status"] == "open" and tick - d["tick"] <= OFFER_HOURS]


def find_offer(sim, a, target, tick):
    offers = open_offers(sim, a, tick)
    t = str(target or "").strip()
    return next((d for d in offers if str(d["id"]) == t or d["from"].lower() == t.lower()), offers[-1] if offers else None)


def accept(sim, a, d, tick) -> str:
    p = sim.agents.get(d["from"])
    if not p:
        d["status"] = "void"
        return f"{d['from']} is gone; the deal is off"
    d["status"] = "accepted"
    near = a.dist(p) <= 2
    notes = []
    if d["give"]:                                   # what the proposer hands over
        if near and has(p, d["give"]):
            move(p, a, d["give"])
            notes.append(f"{p.name} handed you {text(d['give'])}")
        else:
            promise(sim, p, a, d["give"], 12, tick, d["id"])
            notes.append(f"{p.name} owes you {text(d['give'])} within 12 hours")
    if d["want"]:                                   # what you give back
        if d["within"] == 0 and near and has(a, d["want"]):
            move(a, p, d["want"])
            notes.append(f"you handed over {text(d['want'])}")
        else:
            promise(sim, a, p, d["want"], d["within"] or DEFAULT_DUE, tick, d["id"])
            notes.append(f"you owe {p.name} {text(d['want'])} within {d['within'] or DEFAULT_DUE} hours")
    sim.bond(a, p, 4)
    sim.bond(p, a, 4)
    p.heard.append(f"{a.name} accepted your deal ({text(d['give'])} for {text(d['want'])}).")
    p.remember(tick, f"I made a deal with {a.name}: my {text(d['give'])} for their {text(d['want'])}.")
    a.remember(tick, f"I made a deal with {p.name}: my {text(d['want'])} for their {text(d['give'])}.")
    sim.event(tick, a, f"made a deal with {p.name}: {text(d['give'])} for {text(d['want'])}", "trade")
    return "deal done: " + "; ".join(notes)


def decline(sim, a, d, tick) -> str:
    d["status"] = "declined"
    p = sim.agents.get(d["from"])
    if p:
        p.heard.append(f"{a.name} declined your offer of {text(d['give'])} for {text(d['want'])}.")
    return f"declined {d['from']}'s offer"


def promise(sim, a, o, what: dict, within: int, tick: int, deal=None) -> dict:
    pr = {"id": sim.next_id("promise"), "from": a.name, "to": o.name, "what": dict(what), "left": dict(what),
          "due": tick + max(1, int(within or DEFAULT_DUE)), "tick": tick, "status": "open", "deal": deal}
    sim.promises.append(pr)
    del sim.promises[:-120]
    a.remember(tick, f"I promised {o.name} {text(what)} by {clock.short(pr['due'])}.")
    o.remember(tick, f"{a.name} promised me {text(what)} by {clock.short(pr['due'])}.")
    if deal is None:
        o.heard.append(f"{a.name} promises you {text(what)} by {clock.short(pr['due'])}.")
    return pr


def owed(sim, a) -> list[dict]:
    return [p for p in sim.promises if p["status"] == "open" and a.name in (p["from"], p["to"])]


def delivered(sim, giver, taker, res: str, n: int, tick: int) -> str:
    """A gift counts toward what the giver owes the taker."""
    note = ""
    for p in sim.promises:
        if p["status"] != "open" or p["from"] != giver.name or p["to"] != taker.name or res not in p["left"]:
            continue
        use = min(n, p["left"][res])
        p["left"][res] -= use
        n -= use
        if p["left"][res] <= 0:
            del p["left"][res]
        if not p["left"]:
            p["status"] = "kept"
            giver.kept += 1
            sim.bond(taker, giver, 10)
            taker.remember(tick, f"{giver.name} kept their promise ({text(p['what'])}).")
            giver.remember(tick, f"I kept my promise to {taker.name}.")
            note = " - promise kept!"
        if n <= 0:
            break
    return note


def check_promises(sim, tick):
    for d in sim.deals:
        if d["status"] == "open" and tick - d["tick"] > OFFER_HOURS:
            d["status"] = "expired"
    for p in sim.promises:
        if p["status"] != "open" or tick < p["due"]:
            continue
        p["status"] = "broken"
        debtor, creditor = sim.agents.get(p["from"]), sim.agents.get(p["to"])
        if not debtor or not creditor:
            continue
        debtor.broken += 1
        creditor.bonds[debtor.name] = max(-100.0, creditor.bonds.get(debtor.name, 0) - 25)
        creditor.anger = max(creditor.anger, 12)
        creditor.remember(tick, f"{debtor.name} BROKE their promise to give me {text(p['what'])}.")
        debtor.remember(tick, f"I broke my promise to {creditor.name} ({text(p['what'])}).")
        creditor.heard.append(f"{debtor.name} broke their promise to you ({text(p['what'])}).")
        for o in sim.agents.values():          # word gets around among the creditor's friends
            if o not in (debtor, creditor) and o.bonds.get(creditor.name, 0) >= 25:
                o.remember(tick, f"I heard {debtor.name} broke a promise to {creditor.name}.")
        sim.event(tick, debtor, f"broke a promise to {creditor.name} ({text(p['what'])})", "trade")
        sim.seed_story(tick, f"{debtor.name} broke a promise to {creditor.name}", [debtor.name, creditor.name])


# ================================================================ groups
def group_of(sim, a):
    return sim.groups.get(a.group) if a.group else None


def find_group(sim, name: str):
    n = str(name or "").strip().lower()
    return next((g for g in sim.groups.values() if n and (n == g["name"].lower() or n in g["name"].lower())), None)


def found(sim, a, name: str, purpose: str, tick: int) -> str:
    name = re.sub(r"\s+", " ", str(name or "")).strip()[:40]
    if not name:
        return "a group needs a name (title)"
    if find_group(sim, name):
        return f'there is already a group called "{name}" - join it instead'
    if a.group:
        leave(sim, a, tick, quiet=True)
    gid = sim.next_id("group")
    g = {"id": gid, "name": name, "purpose": str(purpose or "")[:160], "founder": a.name, "leader": a.name,
         "members": [a.name], "color": GROUP_COLORS[(gid - 1) % len(GROUP_COLORS)], "plan": "", "laws": [],
         "proposals": [], "notes": [f"{clock.short(tick)}: founded by {a.name}" + (f" - {purpose}" if purpose else "")],
         "banned": [], "votes": {}, "tick": tick}
    sim.groups[gid] = g
    a.group = gid
    a.remember(tick, f'I founded "{name}"' + (f" ({purpose})" if purpose else "") + ". I lead it until we choose otherwise.")
    for o in sim.agents.values():
        if o is not a and a.dist(o) <= 8:
            o.heard.append(f'{a.name} founded a group called "{name}"' + (f": {purpose}" if purpose else "") + ". You could join it.")
    sim.event(tick, a, f'founded "{name}"' + (f" - {purpose}" if purpose else ""), "group")
    sim.seed_story(tick, f'{a.name} founded "{name}"', [a.name])
    return f'founded "{name}" - you are its leader. Invite others to join.'


def join(sim, a, name: str, tick: int) -> str:
    g = find_group(sim, name)
    if not g:
        return f'no group called "{name}" (groups: {", ".join(x["name"] for x in sim.groups.values()) or "none yet - found one"})'
    if a.name in g["banned"]:
        return f'you were exiled from "{g["name"]}" - they won\'t have you back'
    if a.name in g["members"]:
        return f'you are already in "{g["name"]}"'
    if not any(m in sim.agents and a.dist(sim.agents[m]) <= 8 for m in g["members"]):
        return f'go to a member of "{g["name"]}" to join'
    if a.group:
        leave(sim, a, tick, quiet=True)
    g["members"].append(a.name)
    a.group = g["id"]
    note(g, tick, f"{a.name} joined")
    for m in g["members"]:
        if m != a.name and m in sim.agents:
            sim.agents[m].heard.append(f'{a.name} joined your group "{g["name"]}".')
            sim.bond(sim.agents[m], a, 5)
    a.remember(tick, f'I joined "{g["name"]}" (leader: {g["leader"] or "none"}).')
    sim.event(tick, a, f'joined "{g["name"]}"', "group")
    return f'joined "{g["name"]}"' + (f" - its plan: {g['plan']}" if g["plan"] else "")


def leave(sim, a, tick: int, quiet=False) -> str:
    g = group_of(sim, a)
    if not g:
        return "you are not in a group"
    g["members"] = [m for m in g["members"] if m != a.name]
    g["votes"] = {k: v for k, v in g["votes"].items() if k != a.name and v != a.name}
    a.group = None
    note(g, tick, f"{a.name} left")
    if g["leader"] == a.name:
        g["leader"] = None
        elect(sim, g, tick)
    if not g["members"]:
        del sim.groups[g["id"]]
        sim.event(tick, a, f'"{g["name"]}" broke up', "group")
    elif not quiet:
        sim.event(tick, a, f'left "{g["name"]}"', "group")
    a.remember(tick, f'I left "{g["name"]}".')
    return f'left "{g["name"]}"'


def vote(sim, a, who: str, tick: int) -> str:
    g = group_of(sim, a)
    if not g:
        return "you are not in a group"
    if who not in g["members"]:
        return f"{who} is not a member of {g['name']}"
    g["votes"][a.name] = who
    elect(sim, g, tick)
    return f"voted for {who} to lead {g['name']} (leader now: {g['leader'] or 'nobody'})"


def elect(sim, g, tick):
    tally = {}
    for voter, who in g["votes"].items():
        if voter in g["members"] and who in g["members"]:
            tally[who] = tally.get(who, 0) + 1
    if tally:
        best = max(tally, key=lambda n: (tally[n], n == g["leader"]))
        if tally[best] * 2 >= len(g["members"]) and best != g["leader"]:
            g["leader"] = best
            note(g, tick, f"{best} chosen as leader")
            if best in sim.agents:
                sim.event(tick, sim.agents[best], f'was chosen to lead "{g["name"]}"', "group")
                sim.agents[best].remember(tick, f'I was chosen to lead "{g["name"]}".')
                sim.seed_story(tick, f'{best} was chosen to lead "{g["name"]}"', [best])
    if not g["leader"] and g["members"]:
        g["leader"] = g["members"][0]


def note(g, tick, text):
    g["notes"].append(f"{clock.short(tick)}: {text}")
    del g["notes"][:-12]


def set_plan(sim, a, plan: str, tick: int):
    g = group_of(sim, a)
    if g and g["leader"] == a.name and plan and plan != g["plan"]:
        g["plan"] = plan[:200]
        note(g, tick, f"plan: {g['plan']}")
        for m in g["members"]:
            if m != a.name and m in sim.agents:
                sim.agents[m].heard.append(f'{a.name}, your leader, set the plan for "{g["name"]}": {g["plan"]}')


def territory(sim, gid) -> set:
    key = (gid, len(sim.world.buildings), tuple(sim.groups[gid]["members"]) if gid in sim.groups else ())
    if sim._territory.get(gid, (None,))[0] == key:
        return sim._territory[gid][1]
    tiles = set()
    for b in sim.world.buildings.values():
        if b.get("group") == gid:
            for y in range(b["y"] - TERRITORY, b["y"] + b["h"] + TERRITORY):
                for x in range(b["x"] - TERRITORY, b["x"] + b["w"] + TERRITORY):
                    if sim.world.in_bounds(x, y):
                        tiles.add((x, y))
    sim._territory[gid] = (key, tiles)
    return tiles


def land_of(sim, x, y):
    return next((g for g in sim.groups.values() if (x, y) in territory(sim, g["id"])), None)


# ================================================================ laws
ACTS = [(r"steal|theft|thie|rob", "steal"), (r"take|taking|granary|storehouse|store", "take"),
        (r"hunt|kill.*animal|slaughter", "hunt"), (r"cut|chop|fell|tree|wood", "gather_wood"),
        (r"berr|forag|pick|bush", "gather_food"), (r"court|flirt", "court"), (r"build|construct", "build")]
WHEN = [(r"night|dark", "night"), (r"day ?time|by day|daylight", "day"), (r"spring", "spring"), (r"summer", "summer"),
        (r"autumn|fall\b", "autumn"), (r"winter", "winter")]


def classify(text: str) -> dict | None:
    """Turn a law's words into something the game can check: which action it forbids, when and where.
    Laws it can't read are still laws - people just have to notice breaches themselves."""
    t = text.lower()
    if not re.search(r"\bno\b|not|never|forbid|ban|must not|mustn|don't|dont|nobody|prohibit|illegal", t):
        return None
    act = next((a for p, a in ACTS if re.search(p, t)), None)
    if not act:
        return None
    when = next((w for p, w in WHEN if re.search(p, t)), "any")
    where = "territory" if re.search(r"our land|territory|near (the )?(village|camp|home)|around|here|in the village", t) else "any"
    if act == "take" and not re.search(r"night|without|more than|too much", t):
        where = "store"
    return {"act": act, "when": when, "where": where}


def propose(sim, a, text: str, tick: int) -> str:
    g = group_of(sim, a)
    if not g:
        return "only a group can make laws - found or join one first"
    text = str(text or "").strip()[:140]
    if len(text) < 5:
        return "say the law in words (title)"
    if any(l["text"].lower() == text.lower() for l in g["laws"]) or any(p["text"].lower() == text.lower() for p in g["proposals"]):
        return f'"{text}" is already a law (or proposed) in "{g["name"]}"'
    if g["leader"] == a.name or len(g["members"]) == 1:
        return adopt(sim, g, text, a.name, tick, "decreed")
    pr = {"id": sim.next_id("proposal"), "text": text, "by": a.name, "tick": tick, "support": [a.name]}
    g["proposals"].append(pr)
    del g["proposals"][:-5]
    for m in g["members"]:
        if m != a.name and m in sim.agents:
            sim.agents[m].heard.append(f'{a.name} proposes a law for "{g["name"]}": "{text}". Use support with target "{pr["id"]}" to back it.')
    return f'proposed the law "{text}" (proposal {pr["id"]}); it passes when most members support it'


def support(sim, a, target, tick: int) -> str:
    g = group_of(sim, a)
    if not g or not g["proposals"]:
        return "there is no proposal to support"
    t = str(target or "").strip().lower()
    pr = next((p for p in g["proposals"] if str(p["id"]) == t or (t and t in p["text"].lower())), g["proposals"][-1])
    if a.name not in pr["support"]:
        pr["support"].append(a.name)
    if len(pr["support"]) * 2 > len(g["members"]):
        g["proposals"].remove(pr)
        return adopt(sim, g, pr["text"], pr["by"], tick, "agreed")
    return f'backed "{pr["text"]}" ({len(pr["support"])}/{len(g["members"])} support it)'


def adopt(sim, g, text, by, tick, how):
    if any(l["text"].lower() == text.lower() for l in g["laws"]):
        return f'"{text}" is already a law in "{g["name"]}"'
    law = {"id": sim.next_id("law"), "text": text, "rule": classify(text), "by": by, "tick": tick}
    g["laws"].append(law)
    del g["laws"][:-8]
    note(g, tick, f'law {how}: "{text}"')
    for m in g["members"]:
        if m in sim.agents:
            sim.agents[m].remember(tick, f'"{g["name"]}" {how} a law: "{text}".')
            sim.agents[m].heard.append(f'New law in "{g["name"]}": "{text}".')
    who = sim.agents.get(by)
    if who:
        sim.event(tick, who, f'{"decreed" if how == "decreed" else "got agreement on"} a law for "{g["name"]}": "{text}"', "law")
    sim.seed_story(tick, f'"{g["name"]}" made the law "{text}"', [by])
    return f'"{text}" is now law in "{g["name"]}"'


def breaks(rule, act_name: str, result: str, a, sim, tick) -> bool:
    if not rule:
        return False
    kind = act_name
    if act_name == "gather":
        kind = "gather_wood" if "tree" in result else "gather_food" if ("bush" in result or "crop" in result) else "gather"
    if rule["act"] != kind:
        return False
    w = rule["when"]
    if w == "night" and not (clock.when(tick)["hour"] >= 20 or clock.when(tick)["hour"] < 6):
        return False
    if w == "day" and clock.when(tick)["hour"] >= 20:
        return False
    if w in ("spring", "summer", "autumn", "winter") and clock.season(tick) != w:
        return False
    return True


def check_laws(sim, a, act_name: str, result: str, tick: int):
    """After an action: did it break a law of the agent's own group, or of the group whose land it is on?"""
    groups = [g for g in (group_of(sim, a), land_of(sim, a.x, a.y)) if g]
    for g in {id(g): g for g in groups}.values():
        own = a.name in g["members"]
        for law in g["laws"]:
            r = law["rule"]
            if not breaks(r, act_name, result, a, sim, tick):
                continue
            if r["where"] == "territory" and (a.x, a.y) not in territory(sim, g["id"]):
                continue
            if not own and r["where"] != "territory":
                continue                                     # other groups' laws only bind on their land
            seen = [o for o in sim.agents.values() if o is not a and o.name in g["members"] and a.dist(o) <= WITNESS_RADIUS
                    and not o.is_baby(tick)]
            a.offenses.append({"law": law["text"], "group": g["id"], "tick": tick, "seen": [o.name for o in seen]})
            del a.offenses[:-6]
            if not seen:
                a.remember(tick, f'I broke the law "{law["text"]}" - nobody saw.')
                continue
            a.remember(tick, f'I broke the law "{law["text"]}" and {", ".join(o.name for o in seen)} saw it.')
            for o in seen:
                o.remember(tick, f'I saw {a.name} break the law "{law["text"]}".')
                o.heard.append(f'You saw {a.name} break the law "{law["text"]}" of "{g["name"]}". You may punish, forgive or let it go.')
            sim.event(tick, a, f'broke the law "{law["text"]}" of "{g["name"]}" (seen by {", ".join(o.name for o in seen)})', "law")


def open_offense(a, tick, by=None):
    return next((o for o in reversed(a.offenses) if tick - o["tick"] <= 3 * clock.DAY and not o.get("dealt")
                 and (by is None or by in o["seen"])), None)


def punish(sim, a, o, message: str, tick: int) -> str:
    g = group_of(sim, a)
    off = open_offense(o, tick) if g and g["leader"] == a.name else open_offense(o, tick, a.name)
    if not off:
        return f"{o.name} has done nothing you know of that deserves punishment"
    off["dealt"] = "punished"
    fine = min(2, o.food)
    o.food -= fine
    a.food += fine
    o.bonds[a.name] = max(-100.0, o.bonds.get(a.name, 0) - 15)
    o.anger = max(o.anger, 24)
    o.needs["status"] = min(100, o.needs.get("status", 30) + 20)
    o.heard.append(f'{a.name} punished you for breaking "{off["law"]}"' + (f': "{message}"' if message else "") + (f" (fined {fine} food)" if fine else ""))
    o.remember(tick, f'{a.name} punished me for breaking "{off["law"]}".')
    a.remember(tick, f'I punished {o.name} for breaking "{off["law"]}".')
    sim.event(tick, a, f'punished {o.name} for breaking "{off["law"]}"' + (f" (fined {fine} food)" if fine else ""), "law")
    return f"punished {o.name}" + (f", fined {fine} food" if fine else "")


def forgive(sim, a, o, tick: int) -> str:
    off = open_offense(o, tick)
    if off:
        off["dealt"] = "forgiven"
    o.anger = 0
    sim.bond(o, a, 8)
    sim.bond(a, o, 4)
    o.heard.append(f"{a.name} forgave you.")
    o.remember(tick, f"{a.name} forgave me.")
    a.remember(tick, f"I forgave {o.name}.")
    return f"forgave {o.name}"


def exile(sim, a, o, tick: int) -> str:
    g = group_of(sim, a)
    if not g or g["leader"] != a.name:
        return "only a group's leader can exile someone"
    if o.name not in g["members"]:
        return f"{o.name} is not in your group"
    leave(sim, o, tick, quiet=True)
    g["banned"].append(o.name)
    off = open_offense(o, tick)
    if off:
        off["dealt"] = "exiled"
    o.anger, o.grief = 48, 24
    o.heard.append(f'{a.name} exiled you from "{g["name"]}". You may never return.')
    o.remember(tick, f'{a.name} exiled me from "{g["name"]}".')
    a.remember(tick, f'I exiled {o.name} from "{g["name"]}".')
    note(g, tick, f"{o.name} exiled by {a.name}")
    sim.event(tick, a, f'exiled {o.name} from "{g["name"]}"', "law")
    sim.seed_story(tick, f'{a.name} exiled {o.name} from "{g["name"]}"', [a.name, o.name])
    return f"exiled {o.name}"
