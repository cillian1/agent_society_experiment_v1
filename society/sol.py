"""Sol: a wise mentor who watches over the society from outside the world. Every morning Sol reviews how
everyone is doing, speaks to the whole society, and gives individuals concrete advice (and can line up next steps
for agents who are drifting). The Human can talk to Sol, and Sol passes things on."""
import collections
import re
import json
import threading

from .clock import age_text, stamp
from .clock import DAY
from .config import FUNCTIONS, MAX_QUEUE, SOL_MAX_DAYS, SOL_MIN_DAYS
from .mind import ACTIONS, _json, failed, parse_action, said
from . import clock, culture, history, social
from . import tech as techtree

NAME = "Sol"
SOL_TOKENS = 1500         # Sol talks to everyone and advises many people at once: allow a long answer
COLOR = "#ffd93d"


def overview(sim) -> str:
    """A compact picture of the whole society for Sol."""
    t, lines = sim.tick, []
    for a in sim.agents.values():
        recent = [h for h in a.history[-20:] if h["action"] != "reply to Human"]
        counts = collections.Counter(h["action"] for h in recent)
        fails = sum(failed(h["result"]) for h in recent)
        lines.append(
            f"- {a.name} ({a.word(t)}, {age_text(a.age(t))}, {a.stage(t)}{', role: ' + a.role if a.role else ''}): "
            f"hunger {int(a.hunger)}, health {int(a.health)}, carries {a.food} food/{a.wood} wood/{a.stone} stone"
            + (f"; ambition: {a.ambition}" if a.ambition else "") + (f"; plan: {a.plan}" if a.plan else "")
            + (f"; last 20 hours: {', '.join(f'{k} x{v}' for k, v in counts.most_common(5))}, {fails} failed" if recent else "")
            + (f"; latest: {recent[-1]['action']} -> {recent[-1]['result'][:90]}" if recent else ""))
    funcs = collections.Counter(s.get("function") or "decorative" for s in sim.world.buildings.values())
    stock = [f"{s['kind']} holds {s['stock']['food']} food" for s in sim.world.buildings.values() if s.get("stock")]
    groups = "; ".join(f'"{g["name"]}" (leader {g["leader"]}, {len(g["members"])} members, {len(g["laws"])} laws)'
                       for g in sim.groups.values()) or "none"
    broken = sum(p["status"] == "broken" for p in sim.promises)
    return (f"{stamp(t)}, {clock.season(t)}. {len(sim.agents)} alive, {len(sim.dead)} dead. Explored {sim.world.explored_pct()}% of the world.\n"
            f"Age: {techtree.age(sim.techs)}; breakthroughs: {', '.join(techtree.name(x) for x in sim.techs) or 'none'}. "
            f"Wild animals: {sum(1 for b in sim.eco.animals.values() if not b['owner'])}. Groups: {groups}. "
            f"Deals made: {sum(d['status'] == 'accepted' for d in sim.deals)}, promises broken: {broken}. "
            f"Peoples met: {', '.join(sim.contacts) or 'not yet'}.\n"
            f"Buildings: {', '.join(f'{v} {k}' for k, v in funcs.items()) or 'none'}. {'; '.join(stock)}\n"
            f"Discoveries: {', '.join(d['name'] for d in sim.discoveries) or 'none'}. "
            f"Known blueprints: {', '.join(b['kind'] for b in sim.blueprints.values()) or 'none'}.\n"
            f"Building functions available: {', '.join(f'{k} ({v[1]})' for k, v in FUNCTIONS.items())}.\n"
            "People:\n" + "\n".join(lines))


INSTRUCTIONS = (
    "You are Sol, a wise, warm and practical mentor who watches over this small society from outside the world. "
    "Nobody has to obey you, but they respect you. Help them flourish: spot anyone doing pointless or repetitive "
    "things (talking in circles, idling, failing at the same thing, hoarding), what the community lacks (food security, "
    "shelter, storage, farms, tools, discoveries, friendships, children's care), and the most promising opportunities. "
    "Give concrete, specific advice that fits each person's abilities and ambition. Be encouraging and brief.")

FORMAT = (
    'Reply ONLY with JSON: {"speech": "<1-3 sentences to everyone>", "advice": {"<name>": {"message": '
    f'"<1-2 sentences to them>", "next": [<up to {MAX_QUEUE} actions for them to start on, optional>]}}}}, '
    '"note_to_human": "<1-2 sentences for the human observer about how the society is doing>", '
    f'"next_review_in_days": <{SOL_MIN_DAYS}-{SOL_MAX_DAYS}: sooner if things are shaky, later if all is well>}}. '
    f"Actions in next use the agents' format, e.g. {{\"action\": \"go\", \"target\": \"wood\"}}, {{\"action\": \"gather\"}}, "
    '{"action": "build", "direction": "east", "title": "well"}, {"action": "plant", "direction": "north"}; '
    f"allowed: {', '.join(x for x in ACTIONS if x not in ('wait', 'attempt', 'invent'))}. Only advise people listed.")


def review(sim) -> dict:
    seeds = "\n".join(f"- {clock.short(x['tick'])}: {x['text']}" for x in sim.story_seeds[-6:])
    old = sim.stories[-1]["title"] if sim.stories and sim.rng.random() < 0.3 else ""
    extra = ""
    if seeds:
        extra += ("\nSTORYTELLER: these happened recently:\n" + seeds + "\nTurn the most memorable into a short story the people "
                  'will tell around the fire (myth-like, 2-4 sentences; it may exaggerate): add "story": {"title": "...", '
                  '"text": "...", "about": ["<names>"]}.')
        if old:
            extra += f' Also retell the old story "{old}" a little differently, as tales change: "retold": {{"title": "{old}", "text": "..."}}.'
    if history.chapter_due(sim):
        extra += ('\nCHRONICLE: write this month\'s chapter of the society\'s history book (60-120 words, vivid, past tense): '
                  '"chapter": {"title": "...", "text": "..."}.')
    prompt = (f"SOL_REVIEW\n{overview(sim)}\n\nThis is your morning address to the society. Your last words to them: "
              f"{sim.sol_log[-1]['speech'] if sim.sol_log else '(this is your first review)'}\n\n{FORMAT}{extra}")
    return _json(sim.llm.complete(INSTRUCTIONS, prompt, model=sim.sol_model, max_tokens=SOL_TOKENS))


def chat(sim, message: str) -> dict:
    talk = "\n".join(f"{c['from']}: {c['text']}" for c in sim.chat if c["from"] in ("You", NAME) and c.get("text"))[-2500:]
    prompt = (f"SOL_CHAT\n{overview(sim)}\n\nYour recent conversation with the Human:\n{talk or '(none)'}\n\n"
              f'The Human (who founded this world) says to you: "{message}"\n'
              "Answer the Human helpfully and honestly in 1-4 sentences. If they ask you to pass something on or to guide "
              "people, also include a speech to everyone and/or advice (with next actions) for specific people - but keep "
              "it short. Put your answer to the Human FIRST. "
              + FORMAT.replace('Reply ONLY with JSON: {', 'Reply ONLY with JSON: {"message": "<your answer to the Human>", '))
    raw = sim.llm.complete(INSTRUCTIONS, prompt, model=sim.sol_model, urgent=True, max_tokens=SOL_TOKENS)
    data = _json(raw)
    data["message"] = said(raw)[:600]
    if not data.get("message"):
        raise RuntimeError(f"Sol's answer couldn't be read: {raw[:160]!r}")
    return data


def apply(sim, data: dict, source: str):
    """Deliver Sol's words: a speech to everyone, advice (and next steps) to individuals. Call with the lock held."""
    t = sim.tick
    speech = str(data.get("speech") or "").strip()[:500]
    advice = data.get("advice") if isinstance(data.get("advice"), dict) else {}
    given = {}
    if speech:
        for a in sim.agents.values():
            if not a.is_baby(t):
                a.heard.append(f'Sol, the wise mentor, says to everyone: "{speech}"')
                a.advice.append([t, f"(to everyone) {speech}"])
                del a.advice[:-6]
        sim.events.append({"tick": t, "agent": NAME, "text": f'to everyone: "{speech}"', "color": COLOR, "kind": "sol"})
    for name, adv in advice.items():
        a = sim.agents.get(name)
        if not a or a.is_baby(t):
            continue
        adv = adv if isinstance(adv, dict) else {"message": str(adv)}
        msg = str(adv.get("message") or "").strip()[:400]
        nxt = parse_action(json.dumps({"action": "wait", "next": adv.get("next") or []}), [])["next"]
        if msg:
            a.heard.append(f'Sol, the wise mentor, says to you: "{msg}"')
            a.advice.append([t, msg])
            del a.advice[:-6]
            a.remember(t, f'Sol advised me: "{msg}"')
        if nxt:
            a.queue = [dict(n) for n in nxt]
        given[name] = msg + (f" (next: {' → '.join(n['action'] for n in nxt)})" if nxt else "")
        sim.events.append({"tick": t, "agent": NAME, "text": f'to {name}: "{msg}"', "color": COLOR, "kind": "sol"})
    try:
        days = int(data.get("next_review_in_days") or 0)
    except (TypeError, ValueError):
        days = 0
    if days:                                   # Sol decides when to look again
        days = max(SOL_MIN_DAYS, min(SOL_MAX_DAYS, days))
        sim.sol_next = sim.sol_last + days * DAY
    st = data.get("story") if isinstance(data.get("story"), dict) else None
    if st and culture.add_story(sim, st.get("title"), st.get("text"), st.get("about") or [], t):
        sim.story_seeds.clear()
        sim.events.append({"tick": t, "agent": NAME, "text": f'a new story is told: "{str(st.get("title"))[:60]}"', "color": COLOR, "kind": "story"})
    rt = data.get("retold") if isinstance(data.get("retold"), dict) else None
    if rt:
        culture.add_story(sim, rt.get("title"), rt.get("text"), [], t)
    if data.get("chapter"):
        history.add_chapter(sim, data["chapter"])
    sim.sol_log.append({"tick": t, "source": source, "speech": speech, "advice": given, "next_days": days or None,
                        "note": str(data.get("note_to_human") or "").strip()[:400]})
    del sim.sol_log[:-30]
    del sim.events[:-300]
    return given


def run_review(sim):
    """Review now (blocking model call outside the lock, then apply)."""
    try:
        data = review(sim)
    except Exception as e:
        sim.errors.append({"tick": sim.tick, "agent": NAME, "model": sim.sol_model, "error": f"Sol's review failed: {e}"[:300]})
        return
    with sim.lock:
        given = apply(sim, data, "review")
        log = sim.sol_log[-1]
        text = (log["note"] + " " if log["note"] else "") + (f'I told everyone: "{log["speech"]}"' if log["speech"] else "")
        if given:
            text += " Advice: " + "; ".join(f"{n}: {m}" for n, m in given.items())
        sim.chat.append({"from": NAME, "text": text.strip() or "(Sol watched quietly.)", "tick": sim.tick, "color": COLOR,
                         "review": True})


def review_async(sim):
    threading.Thread(target=run_review, args=(sim,), daemon=True).start()


def reply_async(sim, message: str, slot: dict):
    def go():
        try:
            data = chat(sim, message)
            text = str(data.get("message") or data.get("note_to_human") or data.get("speech") or "").strip()
            text = text or "(Sol nodded but said nothing - try asking again)"
        except Exception as e:
            sim.errors.append({"tick": sim.tick, "agent": NAME, "model": sim.sol_model, "error": f"Sol's reply failed: {e}"[:300]})
            data, text = {}, f"(Sol couldn't answer: {e})"
        with sim.lock:
            given = apply(sim, data, "human") if data else {}
            changes = ([f'📣 told everyone: "{data["speech"]}"'] if data.get("speech") else []) + \
                      [f"💬 {n}: {m}" for n, m in given.items()]
            slot.update(text=text, pending=False, changes=changes)
    threading.Thread(target=go, daemon=True).start()
