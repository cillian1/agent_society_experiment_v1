"""Save and load whole societies as JSON files in ./saves (autosave included)."""
import json
import re
import time
from pathlib import Path

from .engine import Society

SAVE_DIR = Path("saves")


def _path(name: str) -> Path:
    name = re.sub(r"[^\w\- ]", "", name).strip()[:60] or "save"
    return SAVE_DIR / f"{name}.json"


def save(sim: Society, name: str) -> str:
    SAVE_DIR.mkdir(exist_ok=True)
    path = _path(name)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(sim.to_dict()))
    tmp.replace(path)                       # atomic: a crash never leaves a half-written save
    return path.stem


def load(name: str, llm) -> Society:
    return Society.from_dict(json.loads(_path(name).read_text()), llm)


def list_saves() -> list[dict]:
    if not SAVE_DIR.exists():
        return []
    out = []
    for p in sorted(SAVE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with p.open() as f:
                head = f.read(4000)
            day = re.search(r'"tick": (\d+)', head)
            out.append({"name": p.stem, "day": int(day.group(1)) if day else None,
                        "saved": time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime)),
                        "size_kb": p.stat().st_size // 1024})
        except OSError:
            pass
    return out
