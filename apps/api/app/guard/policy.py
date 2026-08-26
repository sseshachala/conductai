"""Guard policy engine — pre-call rule evaluation for proxied LLM calls.

The single source of truth for \"should this LLM call be allowed?\"

Callers:
- HTTP proxy handler (app/modules/guard/routers/proxy.py) — external agents
- Lens LLM client (planned, #1218 Step 3) — in-process, dogfood

Extracted from proxy.py in #1218 Step 1a. Behavior is byte-identical to the
pre-refactor implementation; the regression harness under tests/regression/
locks that in.
"""
from __future__ import annotations

import re
import uuid

import structlog

from app.core.database import SessionLocal
from app.core.workspace_context import set_workspace_rls
from app.modules.guard.detectors.normalizer import normalize as _normalize_text
from app.modules.guard.policy_engine import (
    canonical_workspace_id as _canonical_workspace_id,
    compute_policy,
)

log = structlog.get_logger(__name__)


# ─── Constants (public — used by audit/proxy for consistent scoring) ──────────

SEVERITY_WEIGHTS = {"critical": 10, "high": 5, "medium": 3, "low": 1}
_ACTION_RANK = {"allow": 0, "audit": 1, "inject": 2, "warn": 3, "approval": 4, "block": 5}


def _defense_score(matched: list[dict]) -> int:
    return sum(SEVERITY_WEIGHTS.get((m.get("severity") or "medium").lower(), 3) for m in matched)


# ─── Prompt flattening (shared with audit-time prompt summarisation) ──────────

def flatten_prompt(body: dict) -> str:
    """Best-effort: join all user message contents for prompt-pattern matching.

    Anthropic + OpenAI share the messages[].content shape; content can be a
    string or a list of typed parts. Non-text parts are skipped.
    """
    out: list[str] = []
    for msg in body.get("messages") or []:
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            out.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") in (None, "text", "input_text"):
                    text = part.get("text")
                    if text:
                        out.append(text)
    return "\n".join(out)


# ─── Rule matching helpers ────────────────────────────────────────────────────

def _is_proxy_rule(rule: dict) -> bool:
    """True if the rule has at least one proxy-applicable matcher.
    match_pattern is proxy-applicable only when match_tool is absent
    (rules with match_tool are hook-event rules, not LLM-call rules)."""
    if any(k in rule for k in ("match_provider", "match_model", "match_prompt")):
        return True
    return "match_pattern" in rule and "match_tool" not in rule


def _rule_matches(rule: dict, provider: str, model: str, prompt_text: str) -> bool:
    p = rule.get("match_provider")
    if p is not None and p != provider:
        return False
    m = rule.get("match_model")
    if m and not re.search(m, model or "", re.IGNORECASE):
        return False
    pp = rule.get("match_prompt")
    pat = rule.get("match_pattern")
    if not pp and not pat:
        return True
    variants = _normalize_text(prompt_text or "")
    if pp and not any(re.search(pp, v.text, re.IGNORECASE) for v in variants):
        return False
    if pat and not any(re.search(pat, v.text, re.IGNORECASE) for v in variants):
        return False
    return True


# ─── Evaluate (public API) ────────────────────────────────────────────────────

def evaluate(workspace_id: str, provider: str, model: str, body: dict) -> dict:
    """Pre-call Guard policy evaluation.

    Loads the workspace's compiled policy snapshot (from skill_packs via the
    existing engine) and applies any rule with proxy-applicable matchers:

      match_provider  exact string ('anthropic' | 'openai' | 'perplexity')
      match_model     regex against the model id
      match_prompt    regex against concatenated user messages

    First match wins; action is mapped to BLOCK / WARN / ALLOW. Rules written
    for hook events (match_tool + match_pattern) are silently skipped here —
    they don't apply to raw LLM calls.

    Fail-open on engine errors: returns ALLOW with rule_id='guard.engine_error'
    so the call still goes through and we don't lock customers out of LLMs if
    our cache is busted. The error is logged. If the workspace has
    deny_on_error set, returns BLOCK instead.
    """
    db = SessionLocal()
    try:
        policy_ws_id = _canonical_workspace_id(workspace_id)

        set_workspace_rls(db, policy_ws_id)
        try:
            rules = compute_policy(db, uuid.UUID(policy_ws_id), "proxy")
        except Exception as e:
            log.warning("guard.proxy.policy_load_failed", err=str(e))
            from app.modules.guard.models import GuardConfig as _GuardConfig
            cfg = db.query(_GuardConfig).filter(_GuardConfig.workspace_id == uuid.UUID(policy_ws_id)).first()
            deny = cfg.deny_on_error if cfg else True
            if deny:
                return {"action": "BLOCK", "rule_id": "guard.engine_error", "message": "Policy engine error — request blocked (fail-closed). Check Guard settings to change this behavior."}
            return {"action": "ALLOW", "rule_id": "guard.engine_error", "message": None}

        prompt_text = flatten_prompt(body)
        matched: list[dict] = []
        winner_full: dict | None = None
        winner_rank = -1
        for r in rules:
            if not _is_proxy_rule(r):
                continue
            if not _rule_matches(r, provider, model, prompt_text):
                continue
            rule_id = r.get("rule_id") or r.get("id")
            action = (r.get("action") or "warn").lower()
            matched.append({
                "rule_id": rule_id,
                "severity": (r.get("severity") or "medium").lower(),
                "action": action,
                "message": r.get("message") or r.get("description"),
            })
            rank = _ACTION_RANK.get(action, 0)
            if rank > winner_rank:
                winner_rank = rank
                winner_full = r

        matched.sort(key=lambda m: (-SEVERITY_WEIGHTS.get(m["severity"], 3), m["rule_id"] or ""))
        score = _defense_score(matched)

        if winner_full is None:
            return {
                "action": "ALLOW",
                "rule_id": None,
                "message": None,
                "inject_guidance": False,
                "guidance": None,
                "matched_rules": matched,
                "defense_score": score,
            }

        w_action = (winner_full.get("action") or "warn").upper()
        inject_guidance = bool(winner_full.get("inject_guidance"))
        guidance = (winner_full.get("guidance") or winner_full.get("message") or winner_full.get("description")) if inject_guidance else None
        mapped = {"BLOCK": "BLOCK", "WARN": "WARN", "APPROVAL": "APPROVAL"}.get(w_action, "ALLOW")
        return {
            "action": mapped,
            "rule_id": winner_full.get("rule_id") or winner_full.get("id"),
            "message": winner_full.get("message") or winner_full.get("description"),
            "inject_guidance": inject_guidance,
            "guidance": guidance,
            "rule": winner_full,
            "matched_rules": matched,
            "defense_score": score,
        }
    finally:
        db.close()


# ─── Composable engine — #1225 Phase 3 ────────────────────────────────────────

def evaluate_composed(ctx, sources=None):
    """Run policy sources in order. Short-circuit on first BLOCK. Merge others."""
    from app.guard.policy_types import PolicyAction, merge_decisions
    from app.guard.sources import DEFAULT_SOURCES

    if sources is None:
        sources = DEFAULT_SOURCES

    collected = []
    for source in sources:
        decision = source.evaluate(ctx)
        collected.append(decision)
        if decision.action in (PolicyAction.BLOCK, PolicyAction.APPROVAL):
            return decision  # short-circuit — later sources not called

    return merge_decisions(collected)
