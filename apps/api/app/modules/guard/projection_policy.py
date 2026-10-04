"""Eligibility, versioning, and retention policy for Guard projections."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from app.modules.guard.projection_contract import ProjectionSourceKind

_DECISION_ALIASES = {
    "allow": "allowed",
    "allowed": "allowed",
    "audited": "allowed",
    "permit": "allowed",
    "permitted": "allowed",
    "block": "blocked",
    "blocked": "blocked",
    "deny": "blocked",
    "denied": "blocked",
    "warn": "warned",
    "warned": "warned",
    "warning": "warned",
}
_APPROVAL_ALIASES = {
    "approval",
    "approve",
    "approved",
    "approval_required",
    "requires_approval",
    "require_approval",
    "needs_approval",
    "pending_approval",
}
_IMMUTABLE_AUDIT_FIELDS = (
    "id",
    "workspace_id",
    "ts",
    "source",
    "ai_tool",
    "tool_call",
    "decision",
    "rule_id",
    "rule_message",
)


def normalize_projection_decision(decision: Any) -> str:
    """Normalize producer-specific decision spellings to projection labels."""
    if isinstance(decision, Enum):
        decision = decision.value
    normalized = re.sub(r"[\s-]+", "_", str(decision or "").strip().lower())
    if normalized in _APPROVAL_ALIASES or "approval" in normalized:
        return "approval"
    return _DECISION_ALIASES.get(normalized, normalized)


normalize_decision = normalize_projection_decision


def _value(item: Any, name: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(name)
    return getattr(item, name, None)


def audit_event_projection_reason(
    decision: Any,
    evaluated_rules: Iterable[Any] | None = None,
) -> str | None:
    """Return why an audit event is projection-eligible, or ``None``."""
    normalized = normalize_projection_decision(decision)
    if normalized in {"blocked", "warned", "approval"}:
        return normalized

    for rule in evaluated_rules or ():
        severity = str(_value(rule, "severity") or "").strip().lower()
        action = normalize_projection_decision(_value(rule, "action"))
        if severity in {"high", "critical"} or action in {
            "blocked",
            "warned",
            "approval",
        }:
            return "security_relevant"
    return None


def _canonical_audit_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return _as_utc(value).isoformat()
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def audit_event_source_version(event: Any) -> str:
    """Return the immutable version for an audit-event projection."""
    entry_hash = _value(event, "entry_hash")
    if isinstance(entry_hash, str) and entry_hash.strip():
        return entry_hash

    immutable = {
        field: _canonical_audit_value(_value(event, field))
        for field in _IMMUTABLE_AUDIT_FIELDS
    }
    canonical = json.dumps(immutable, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("timestamp must be a datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def projection_expires_at(
    source_kind: ProjectionSourceKind | str,
    source_timestamp: datetime,
    retention_days: int,
) -> datetime | None:
    """Calculate source-based expiry without extending it on re-embedding."""
    if isinstance(retention_days, bool) or not isinstance(retention_days, int):
        raise TypeError("retention_days must be a positive integer")
    if retention_days <= 0:
        raise ValueError("retention_days must be positive")

    kind = ProjectionSourceKind(source_kind)
    if kind not in {
        ProjectionSourceKind.AUDIT_EVENT,
        ProjectionSourceKind.AUDIT_SUMMARY,
    }:
        return None
    return _as_utc(source_timestamp) + timedelta(days=retention_days)


def projection_is_expired(
    expires_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    """Return whether expiry has reached the exact UTC cutoff."""
    if expires_at is None:
        return False
    cutoff = _as_utc(expires_at)
    current = _as_utc(now) if now is not None else datetime.now(timezone.utc)
    return cutoff <= current
