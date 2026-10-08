"""Shared command-line options and backend setup for serve.py and run.py."""
import os

from .config import HAIKU, LOCAL
from .llm import ClaudeLLM, LocalLLM, RouterLLM, is_local
from .mock import MockLLM


def add_llm_args(p):
    p.add_argument("--mock", action="store_true", help="scripted offline agents (NOT real thinking)")
    p.add_argument("--no-local", action="store_true", help="don't use a local model server")
    p.add_argument("--local-url", default=os.environ.get("LOCAL_LLM_URL", "http://127.0.0.1:11434"),
                   help="local model server (default: Ollama on 127.0.0.1:11434)")
    p.add_argument("--local-model", default=os.environ.get("LOCAL_LLM_MODEL", "qwen2.5:7b-instruct"),
                   help="local model name (e.g. one you pulled with `ollama pull`)")
    p.add_argument("--local-api", choices=["ollama", "openai"], default="ollama",
                   help="'openai' for LM Studio / llama.cpp / vLLM style servers (use --local-url .../ without /v1)")
    p.add_argument("--local-concurrency", type=int, default=8, help="max simultaneous requests sent to the local server")
    p.add_argument("--local-ctx", type=int, default=4096, help="context window for local requests (Ollama num_ctx)")
    p.add_argument("--price", action="append", default=[], metavar="MODEL=IN,OUT",
                   help="USD per million tokens, to show a $ estimate (repeatable), e.g. claude-haiku-5-5=1,5")


def build_llm(args) -> RouterLLM:
    notes = []
    if args.mock:
        return RouterLLM(mock=MockLLM(), notes=["--mock: agents are scripted"])
    claude = local = None
    prices = {m: tuple(map(float, v.split(","))) for m, v in (x.split("=") for x in args.price)}
    if os.environ.get("ANTHROPIC_API_KEY"):
        claude = ClaudeLLM(prices=prices)
    else:
        notes.append("ANTHROPIC_API_KEY not set: Claude models (Haiku/Sonnet/Opus) are unavailable")
    if not args.no_local:
        cand = LocalLLM(args.local_url, args.local_model, args.local_api, args.local_concurrency, args.local_ctx)
        ok, msg = cand.probe()
        notes.append(msg)
        local = cand if ok else None
    if not claude and not local:
        notes.append("NO BRAINS AVAILABLE: falling back to scripted mock agents")
        return RouterLLM(mock=MockLLM(), notes=notes)
    for n in notes:
        print("[llm]", n)
    return RouterLLM(claude, local, notes=notes)


def resolve_model(model, llm: RouterLLM):
    """Map an agent's wanted model to one that's actually available."""
    if llm.mock:
        return model
    if is_local(model) or model is None:
        return model if llm.local else (HAIKU if llm.claude else model)
    return model if llm.claude else (LOCAL if llm.local else model)


def apply_backends(agents, llm: RouterLLM):
    for a in agents:
        a.model = resolve_model(a.model, llm)
