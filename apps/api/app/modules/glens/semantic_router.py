"""Semantic intent router — embed query, cosine-match against intent bank.

Replaces T1 regex shortcuts + T2 catalog phrase match.
Falls through (returns None) when confidence < THRESHOLD so T3 LLM dispatch handles it.
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

from app.modules.glens.intent_bank import INTENT_EXAMPLES, INTENT_TO_TOOL, WRITE_INTENTS
from app.modules.glens.slot_extractor import extract_slots

THRESHOLD = 0.72  # below this → fall through to T3


# ── Pure-Python cosine (no numpy dep) ────────────────────────────────────────

def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(a: list[float]) -> float:
    return math.sqrt(sum(x * x for x in a))


def _cosine(a: list[float], b: list[float]) -> float:
    na, nb = _norm(a), _norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return _dot(a, b) / (na * nb)


# ── Embedding call ────────────────────────────────────────────────────────────

def _embed_batch(texts: list[str], api_key: str, base_url: str | None = None) -> list[list[float]]:
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [item.embedding for item in sorted(resp.data, key=lambda x: x.index)]


# ── Intent embedding cache (built once per process) ──────────────────────────

@lru_cache(maxsize=1)
def _intent_vectors(api_key: str, base_url: str | None) -> dict[str, list[float]]:
    """Embed one representative phrase per intent and cache."""
    intents = list(INTENT_EXAMPLES.keys())
    # use the first example as the canonical phrase per intent
    phrases = [INTENT_EXAMPLES[i][0] for i in intents]
    vectors = _embed_batch(phrases, api_key, base_url)
    return dict(zip(intents, vectors))


def _get_api_key_and_url() -> tuple[str, str | None]:
    from app.core.config import settings
    key = settings.openai_api_key
    if not key:
        raise ValueError("OPENAI_API_KEY not set — semantic router needs embeddings")
    return key, None


# ── Public API ────────────────────────────────────────────────────────────────

def route(query: str) -> dict[str, Any] | None:
    """
    Return routing decision or None if confidence too low.

    Returns:
        {
          "intent": str,
          "tool": str,
          "slots": dict,          # extracted date/decision/limit
          "confidence": float,
          "is_write": bool,
          "understood_as": str,
        }
    """
    try:
        api_key, base_url = _get_api_key_and_url()
        intent_vecs = _intent_vectors(api_key, base_url)
        [query_vec] = _embed_batch([query], api_key, base_url)
    except Exception:
        return None  # no embedding key or API error → fall through

    best_intent, best_score = max(
        ((intent, _cosine(query_vec, vec)) for intent, vec in intent_vecs.items()),
        key=lambda x: x[1],
    )

    if best_score < THRESHOLD:
        return None

    slots = extract_slots(query)
    tool = INTENT_TO_TOOL.get(best_intent, best_intent)

    return {
        "intent": best_intent,
        "tool": tool,
        "slots": slots,
        "confidence": round(best_score, 3),
        "is_write": best_intent in WRITE_INTENTS,
        "understood_as": _understood_as(best_intent, slots),
    }


def _understood_as(intent: str, slots: dict) -> str:
    parts = []
    label_map = {
        "governance_kpis": "Governance KPIs",
        "governance_activity": "Recent activity",
        "governance_blocked": "Blocked events",
        "governance_warned": "Warned events",
        "workflow_blocks": "Workflow-triggered blocks",
        "correlated_activity": "Correlated session activity",
        "spend_summary": "Spend summary",
        "list_policies": "Guard policies",
        "discovery_summary": "Agent discovery",
        "compliance_status": "Compliance status",
        "get_guard_config": "Guard configuration",
        "get_budgets": "Budget limits",
        "search_memory": "Team memory search",
        "search_sessions": "Session reports search",
        "create_guard_rule": "Create guard rule",
        "edit_guard_rule": "Edit guard rule",
        "delete_guard_rule": "Delete guard rule",
    }
    parts.append(label_map.get(intent, intent))
    if "since" in slots and "until" in slots:
        parts.append(f"from {slots['since']} to {slots['until']}")
    if "decision" in slots:
        parts.append(f"({slots['decision']})")
    return " ".join(parts)
