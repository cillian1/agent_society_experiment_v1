"""Long, specific memory without long prompts, and beliefs that can be wrong.

Every memory line stays in the agent's log forever. Each turn the most relevant older ones are recalled: important
moments (births, deaths, promises, betrayals, discoveries, laws) score high, and so do memories about the people
around, the people speaking and the agent's plan. So Ada remembers that Brix promised wood three days ago the moment
she meets him again.

Beliefs are the agent's own short conclusions ("the east forest has the most wood", "Cleo is lazy"). They come from
its decisions and dreams, can be mistaken, and spread only through what people say."""
import re

IMPORTANT = [  # (pattern, weight)
    (r"born|birth|died|death|pregnant|baby", 4), (r"promis|owe|deal|trade|broke|betray|cheat|kept", 4),
    (r"law|rule|exile|punish|forgave|leader|vote|group|joined|founded", 3.5), (r"love|court|married|heart", 3),
    (r"discover|breakthrough|invent|finished|built", 2.5), (r"gave me|gift|fed|cared|taught", 2),
    (r"flood|fire|winter|starv|hurt|attack", 2.5), (r"story|named|festival", 2), (r"said to me|says to you", 1),
    (r"Human", 2.5), (r"ambition|dreamt|idea", 1.5),
]
STAMP = re.compile(r"^\[([^\]]*)\] ")


def importance(text: str) -> float:
    t = text.lower()
    return 0.5 + sum(w for p, w in IMPORTANT if re.search(p, t, re.I))


def recall(log: list[str], before: int, cues: list[str], k: int = 4) -> list[str]:
    """The k most relevant memories from log[:before] (the part not shown verbatim)."""
    if before <= 0:
        return []
    cues = [c.lower() for c in cues if c and len(c) > 2]
    scored = []
    for i, m in enumerate(log[:before]):
        low = m.lower()
        rel = sum(3 for c in cues if c in low)
        if not rel and importance(m) < 3:
            continue
        scored.append((importance(m) + rel + i / max(1, before), i))   # a little recency
    keep = sorted(i for _, i in sorted(scored, reverse=True)[:k])
    return [log[i] for i in keep]


MAX_BELIEFS = 6


def believe(a, text: str, tick: int, source: str = "") -> bool:
    """Add or update a belief (a new belief about the same subject replaces the old one)."""
    text = str(text or "").strip()[:160]
    if len(text) < 6:
        return False
    words = set(re.findall(r"[a-z]{4,}", text.lower()))
    for b in a.beliefs:
        if len(words & set(re.findall(r"[a-z]{4,}", b["text"].lower()))) >= 2:
            b.update(text=text, t=tick, src=source)
            return True
    a.beliefs.append({"text": text, "t": tick, "src": source})
    del a.beliefs[:-MAX_BELIEFS]
    return True
