"""Policy source wrappers — #1225 Phase 2.

Each source takes its underlying check as a constructor parameter (dependency
injection) so tests can supply stubs without monkey-patching the real
production functions. Default constructor pulls the real check.
"""
from __future__ import annotations

from typing import Callable

import structlog

from app.guard.policy_types import (
    PolicyAction,
    PolicyContext,
    PolicyDecision,
)

log = structlog.get_logger(__name__)


class RulePolicySource:
    def __init__(self, evaluator: Callable | None = None):
        self._evaluator = evaluator

    @property
    def name(self) -> str:
        return "rule"

    def _default_evaluator(self):
        from app.guard.policy import evaluate as _evaluate
        return _evaluate

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
        evaluator = self._evaluator or self._default_evaluator()
        raw = evaluator(ctx.workspace_id, ctx.provider, ctx.model, ctx.body)
        action_str = (raw.get("action") or "ALLOW").upper()
        try:
            action = PolicyAction(action_str)
        except ValueError:
            action = PolicyAction.ALLOW

        return PolicyDecision(
            action=action,
            source=self.name,
            reason=raw.get("message"),
            rule_id=raw.get("rule_id"),
            matched_rules=raw.get("matched_rules") or [],
            defense_score=int(raw.get("defense_score") or 0),
            inject_guidance=bool(raw.get("inject_guidance")),
            guidance=raw.get("guidance"),
            extras={"rule": raw.get("rule"), "raw": raw},
        )


class SpendCapPolicySource:
    def __init__(self, checker: Callable | None = None):
        self._checker = checker

    @property
    def name(self) -> str:
        return "spend_cap"

    def _default_checker(self):
        from app.modules.guard.routers.spend import budget_check as _check
        return _check

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
        if ctx.db is None:
            return PolicyDecision(action=PolicyAction.ALLOW, source=self.name)

        checker = self._checker or self._default_checker()

        try:
            result = checker(
                workspace_id=ctx.workspace_id,
                clerk_user_id=ctx.clerk_user_id,
                db=ctx.db,
            )
        except Exception as e:
            log.warning("guard.policy.spend_cap_source.error", err=str(e))
            return PolicyDecision(
                action=PolicyAction.ALLOW,
                source=self.name,
                reason=f"spend cap check unavailable: {type(e).__name__}",
            )

        if not result.hard_blocked:
            return PolicyDecision(
                action=PolicyAction.ALLOW,
                source=self.name,
                extras={
                    "monthly_cost_usd": result.monthly_cost_usd,
                    "hard_limit_usd": result.hard_limit_usd,
                },
            )

        return PolicyDecision(
            action=PolicyAction.BLOCK,
            source=self.name,
            reason=result.reason,
            rule_id="guard.spend_cap",
            extras={
                "monthly_cost_usd": result.monthly_cost_usd,
                "hard_limit_usd": result.hard_limit_usd,
                "error_type": "guard_budget_exceeded",
            },
        )


class ThroughputCapPolicySource:
    def __init__(self, checker: Callable | None = None):
        self._checker = checker

    @property
    def name(self) -> str:
        return "throughput_cap"

    def _default_checker(self):
        from app.modules.guard.rate_limit import check_rate_limit as _check
        return _check

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
        if ctx.db is None:
            return PolicyDecision(action=PolicyAction.ALLOW, source=self.name)

        checker = self._checker or self._default_checker()

        try:
            result = checker(
                ctx.db,
                workspace_id=ctx.workspace_id,
                agent_identity_id=ctx.agent_identity_id,
                input_tokens=ctx.input_tokens,
            )
        except Exception as e:
            log.warning("guard.policy.throughput_cap_source.error", err=str(e))
            return PolicyDecision(
                action=PolicyAction.ALLOW,
                source=self.name,
                reason=f"throughput cap check unavailable: {type(e).__name__}",
            )

        if not result.limited:
            return PolicyDecision(action=PolicyAction.ALLOW, source=self.name)

        return PolicyDecision(
            action=PolicyAction.BLOCK,
            source=self.name,
            reason=result.reason,
            rule_id="guard.throughput_cap",
            extras={
                "metric": result.metric,
                "limit": result.limit,
                "current": result.current,
                "scope": result.scope,
                "error_type": "guard_rate_limited",
            },
        )


DEFAULT_SOURCES = (
    RulePolicySource(),
    SpendCapPolicySource(),
    ThroughputCapPolicySource(),
)
