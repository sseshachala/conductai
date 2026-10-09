"""Best-effort provider slug from a model name (cost tables key on provider/model)."""
from __future__ import annotations

import re

_OPENAI_REASONING = re.compile(r"^o\d")


def infer_provider_from_model(model: str) -> str | None:
    """Prefix heuristics for the shipped pricing tables and common coding-tool models.

    Unknown prefixes return ``None`` so callers record "unpriced" / 0 cost
    rather than misattributing a model to the wrong provider.
    """
    m = (model or "").lower().strip()
    if not m:
        return None
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith(("gpt", "chatgpt", "codex-", "text-embedding", "text-davinci")) or _OPENAI_REASONING.match(m):
        return "openai"
    if m.startswith("gemini-"):
        return "google"
    if m.startswith("sonar") or m.startswith("perplexity"):
        return "perplexity"
    if m.startswith(("meta-llama", "mistral", "mixtral", "together")):
        return "together"
    return None
