"""Typed view of a ``guard_check`` response.

Extracted from ``conduct_litellm_guard.guardrail`` so both plugins parse
verdicts the same way. When a third consumer arrives this file should
move to ``packages/shared/``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

# Server prefixes tool responses with "[ws:xxxxxxxx] " for debug context
# (apps/api/app/modules/guard/routers/mcp.py:_text). Strip before matching.
_WS_PREFIX = re.compile(r"^\[ws:[^\]]+\]\s*")

Verdict = Literal["allow", "block", "warning", "advisory", "approval", "unknown"]


@dataclass
class GuardDecision:
    """Structured view of what ``guard_check`` returned. The raw text is
    kept so audit / logging surfaces can quote it verbatim."""

    verdict: Verdict
    raw: str
    rule_id: str | None = None
    message: str | None = None

    @classmethod
    def parse(cls, text: str) -> "GuardDecision":
        """Map the ``guard_check`` string envelope to a verdict.

        Response contract (from ``apps/api/app/modules/guard/routers/mcp.py``):

        * ``"ok"`` or empty → allow silently
        * ``"advisory: ..."`` → allow but log
        * ``"WARNING — ..."`` → allow but surface
        * ``"BLOCKED — ..."`` → hard block
        * ``"PENDING approval — ..."`` → HITL — treat as block for now
        """
        stripped = _WS_PREFIX.sub("", (text or "").strip())
        if not stripped or stripped.lower().startswith("ok"):
            return cls(verdict="allow", raw=stripped)
        if stripped.startswith("BLOCKED"):
            return cls(
                verdict="block",
                raw=stripped,
                rule_id=_extract_rule_id(stripped),
                message=_strip_prefix(stripped, "BLOCKED"),
            )
        if stripped.startswith("PENDING approval"):
            return cls(
                verdict="approval",
                raw=stripped,
                rule_id=_extract_rule_id(stripped),
                message=_strip_prefix(stripped, "PENDING approval"),
            )
        if stripped.startswith("WARNING"):
            return cls(
                verdict="warning",
                raw=stripped,
                rule_id=_extract_rule_id(stripped),
                message=_strip_prefix(stripped, "WARNING"),
            )
        if stripped.startswith("advisory"):
            return cls(
                verdict="advisory",
                raw=stripped,
                rule_id=_extract_rule_id(stripped),
                message=_strip_prefix(stripped, "advisory"),
            )
        return cls(verdict="unknown", raw=stripped)


def _strip_prefix(text: str, prefix: str) -> str:
    remainder = text[len(prefix):].lstrip(" —:-").rstrip()
    return remainder or text


_RULE_MARKER = re.compile(r"(?:rule=|\[rule:\s*)([^\s\]]+)")


def _extract_rule_id(text: str) -> str | None:
    """Guard emits either ``rule=<id>`` or ``[rule: <id>]`` in the
    message body. Accept both."""
    m = _RULE_MARKER.search(text)
    return m.group(1).strip(".,;:()[]") if m else None


class ConductGuardBlocked(Exception):
    """Raised when a plugin caller wants an exception rather than a
    branch on ``decision.verdict``. Carries the decision so downstream
    error handlers can quote the rule + message."""

    def __init__(self, decision: GuardDecision):
        super().__init__(decision.message or decision.raw or "blocked by Conduct Guard")
        self.decision = decision
