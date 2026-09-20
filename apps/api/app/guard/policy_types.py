"""Composable policy engine types — shared shape for pluggable sources.

See epic #1225 for design context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class PolicyAction(str, Enum):
    ALLOW = "ALLOW"
    WARN = "WARN"
    APPROVAL = "APPROVAL"
    BLOCK = "BLOCK"


_ACTION_RANK: dict[PolicyAction, int] = {
    PolicyAction.ALLOW: 0,
    PolicyAction.WARN: 1,
    PolicyAction.APPROVAL: 2,
    PolicyAction.BLOCK: 3,
}


@dataclass
class PolicyContext:
    workspace_id: str
    provider: str
    model: str
    body: dict
    clerk_user_id: str | None = None
    agent_identity_id: str | None = None
    input_tokens: int = 0
    db: "Session | None" = None
    extras: dict[str, Any] = field(default_factory=dict)
    # #1733: which enforcement gate this context represents. Locked enum
    # ("action", "prompt", "response") per Guard architecture doc §3.
    # "prompt" = outbound LLM proxy egress; "response" = inbound LLM proxy
    # ingress; "action" = tool call. Default "action" for pre-#1733 callers.
    gate: str = "action"
    # Caller's AgentIdentity.risk_tier, populated by each PEP at request
    # entry. Used by rules with `match_agent_risk_tier` set. None = unknown
    # (legacy row or non-agent caller) — matcher treats null tier as
    # "no match" for any rule requiring a specific tier.
    risk_tier: str | None = None
    # Client-declared or UA-inferred AI tool key ("claude-code",
    # "codex-desktop", ...). Populated at each PEP entry. Feeds
    # SpendCapPolicySource so per-tool budgets scope enforcement to the
    # calling tool. None (or the sentinel string "unknown") means "no
    # trustworthy tool label" — the SpendCap source treats both as absence
    # and falls back to workspace-wide + per-user caps.
    ai_tool: str | None = None
    # #2159 PR 2 (#2156) — tool-name signals for rules that select on
    # tool identity. Distinguished per the epic's "gateway sees
    # generation, not execution" language:
    #   - ``tool_names_offered``   : names in ``body["tools"][].function.name``
    #                                (what the caller advertised to upstream).
    #   - ``tool_names_generated`` : names in ``choices[].message.tool_calls[]``
    #                                (what the model returned this turn;
    #                                 response-gate only).
    #   - ``tool_names_supplied``  : ``tool_call_id``s from ``role:tool``
    #                                messages (previous-turn tool results the
    #                                caller supplied THIS turn).
    # None = "not populated by the PEP" (legacy callers, non-inference
    # gates). Empty list = "PEP populated, no tools present" — semantically
    # distinct so rules can distinguish "unset" from "explicitly empty".
    tool_names_offered: list[str] | None = None
    tool_names_generated: list[str] | None = None
    tool_names_supplied: list[str] | None = None


@dataclass
class PolicyDecision:
    action: PolicyAction
    source: str
    reason: str | None = None
    rule_id: str | None = None
    matched_rules: list[dict] = field(default_factory=list)
    defense_score: int = 0
    inject_guidance: bool = False
    guidance: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def blocks(self) -> bool:
        return self.action == PolicyAction.BLOCK

    @property
    def needs_approval(self) -> bool:
        return self.action == PolicyAction.APPROVAL


def merge_decisions(decisions: list[PolicyDecision]) -> PolicyDecision:
    """Combine non-blocking decisions into one envelope.

    Winner action = highest rank across inputs. matched_rules and
    defense_score accumulate. First inject_guidance flag wins for guidance
    text. extras namespaced by source name.
    """
    if not decisions:
        return PolicyDecision(action=PolicyAction.ALLOW, source="empty")

    if len(decisions) == 1:
        return decisions[0]

    winner = max(decisions, key=lambda d: _ACTION_RANK[d.action])
    accumulated_rules: list[dict] = []
    accumulated_score = 0
    accumulated_extras: dict[str, Any] = {}
    guidance_text: str | None = None
    inject_flag = False

    for d in decisions:
        accumulated_rules.extend(d.matched_rules)
        accumulated_score += d.defense_score
        if d.inject_guidance and guidance_text is None:
            guidance_text = d.guidance
            inject_flag = True
        if d.extras:
            accumulated_extras[d.source] = d.extras

    non_allow_sources = sorted({d.source for d in decisions if d.action != PolicyAction.ALLOW})
    return PolicyDecision(
        action=winner.action,
        source=",".join(non_allow_sources) if non_allow_sources else winner.source,
        reason=winner.reason,
        rule_id=winner.rule_id,
        matched_rules=accumulated_rules,
        defense_score=accumulated_score,
        inject_guidance=inject_flag,
        guidance=guidance_text,
        extras=accumulated_extras,
    )


class PolicySource(Protocol):
    @property
    def name(self) -> str:
        ...

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
        ...
