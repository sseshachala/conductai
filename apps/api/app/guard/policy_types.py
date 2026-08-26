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
