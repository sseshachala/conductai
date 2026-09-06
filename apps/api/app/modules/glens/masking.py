"""Secret masking for Lens outbound text (#1214 #S3).

Applied at the SSE `done` boundary in chat.py before the assistant answer
is streamed to the client AND before it's persisted to the session. Any
prefixed-key that leaks through a tool response ends up masked in both
the UI and the durable transcript.

The patterns are intentionally conservative — match well-known key
prefixes with a length floor, leave everything else alone. Adding
unbounded heuristics (base64-y strings, high-entropy tokens) risks
masking real content and is out of scope for this pass.
"""
from __future__ import annotations

import re


# Ordered by specificity: more-specific prefixes first so "sk-ant-" wins
# over the generic "sk-" pattern.
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("anthropic",  re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai",     re.compile(r"sk-(?!ant-)[A-Za-z0-9_\-]{20,}")),
    ("github-pat", re.compile(r"ghp_[A-Za-z0-9]{20,}")),
    ("github-oauth", re.compile(r"gho_[A-Za-z0-9]{20,}")),
    ("github-server", re.compile(r"ghs_[A-Za-z0-9]{20,}")),
    ("github-refresh", re.compile(r"ghr_[A-Za-z0-9]{20,}")),
    ("slack-bot",  re.compile(r"xoxb-[A-Za-z0-9\-]{20,}")),
    ("slack-user", re.compile(r"xoxp-[A-Za-z0-9\-]{20,}")),
    ("aws-akid",   re.compile(r"AKIA[0-9A-Z]{16}")),
    ("google-api", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    # Conduct-internal tokens
    ("conduct-agent", re.compile(r"cond_agt_[A-Za-z0-9_\-]{20,}")),
    ("conduct-run",   re.compile(r"cond_run_[A-Za-z0-9_\-]{20,}")),
    ("conduct-cred",  re.compile(r"cond_cred_[A-Za-z0-9_\-]{20,}")),
]


def mask_secrets(text: str) -> str:
    """Return `text` with recognised secret substrings replaced by a
    labelled placeholder. Idempotent — running twice is a no-op."""
    if not text:
        return text
    for label, pat in _SECRET_PATTERNS:
        text = pat.sub(f"[REDACTED:{label}]", text)
    return text
