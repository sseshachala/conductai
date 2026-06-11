"""
Guard block executor.

Applies ConductGuard policy checks at a point in the workflow.
Extracted from app.runtime.executor.
"""
from __future__ import annotations

import json
import re as _re
import uuid as _uuid
from datetime import datetime, timezone

import structlog

log = structlog.get_logger(__name__)


def _execute_guard(block: dict, state: dict, workspace_id: str, db) -> dict:
    """Apply ConductGuard policy check at this point in the workflow.

    Evaluates all active team policies against the current workflow state.
    Violations are handled per enforcement_mode:
      block  — raises RuntimeError, halts the run
      warn   — records audit event, adds warning to output, run continues
      audit  — records audit event silently, run continues

    Config keys:
      enforcement_mode: block | warn | audit  (default: block)
      context_keys: list of state keys to include in pattern matching
                    (default: all state keys)
      rule_ids: list of specific rule IDs to evaluate
                (default: all enabled rules)
    """
    from app.modules.guard.models import GuardAuditEvent, GuardPolicy

    config           = block.get("config") or {}
    enforcement_mode = config.get("enforcement_mode", "block")
    context_keys     = config.get("context_keys") or []
    rule_ids_filter  = set(config.get("rule_ids") or [])

    # ── 1. Verify Guard is installed for this workspace ───────────────────────
    try:
        ws_uuid = _uuid.UUID(workspace_id)
    except ValueError:
        ws_uuid = None

    guard_installed = False
    if ws_uuid:
        from sqlalchemy import text as _text
        guard_installed = db.execute(
            _text("SELECT 1 FROM guard_config WHERE workspace_id = :ws LIMIT 1"),
            {"ws": str(ws_uuid)},
        ).fetchone() is not None

    if not guard_installed:
        if enforcement_mode == "block":
            raise RuntimeError(
                "Guard block: ConductGuard is not installed for this workspace. "
                "Install Guard in Settings → Modules to use this block."
            )
        return {
            "status": "skipped",
            "reason": "guard_not_installed",
            "enforcement_mode": enforcement_mode,
        }

    # ── 2. Build context string from workflow state ────────────────────────────
    if context_keys:
        context_dict = {k: state.get(k) for k in context_keys if k in state}
    else:
        # Exclude internal keys starting with __
        context_dict = {k: v for k, v in state.items() if not k.startswith("__")}

    context_json = json.dumps(context_dict, default=str)

    # Extract path-like values for match_path_pattern
    path_values: list[str] = []

    def _collect_paths(obj: object) -> None:
        if isinstance(obj, str) and ("/" in obj or "\\" in obj):
            path_values.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                _collect_paths(v)
        elif isinstance(obj, list):
            for v in obj:
                _collect_paths(v)

    _collect_paths(context_dict)
    path_text = " ".join(path_values)

    # ── 3. Load active policies ───────────────────────────────────────────────
    policy_q = db.query(GuardPolicy).filter(
        GuardPolicy.workspace_id == ws_uuid,
        GuardPolicy.enabled.is_(True),
    )
    if rule_ids_filter:
        policy_q = policy_q.filter(GuardPolicy.rule_id.in_(rule_ids_filter))
    policies = policy_q.order_by(GuardPolicy.updated_at.desc()).all()

    # ── 4. Evaluate rules ─────────────────────────────────────────────────────
    violations = []
    for policy in policies:
        # match_tool — for workflow context use "workflow" as the synthetic tool
        match_tool = (policy.match_tool or "*").lower()
        if match_tool != "*":
            allowed = {t.strip() for t in match_tool.split(",")}
            if "workflow" not in allowed:
                continue

        # match_pattern — search context JSON
        if policy.match_pattern:
            try:
                if not _re.search(policy.match_pattern, context_json, _re.IGNORECASE):
                    continue
            except _re.error:
                continue

        # match_path_pattern — search path-like values
        if policy.match_path_pattern:
            try:
                if not _re.search(policy.match_path_pattern, path_text, _re.IGNORECASE):
                    continue
            except _re.error:
                continue

        violations.append(policy)

    # ── 5. Handle violations ──────────────────────────────────────────────────
    block_id   = block.get("id", "guard")
    now        = datetime.now(timezone.utc)
    warnings   = []

    def _record_event(policy: GuardPolicy, decision: str) -> None:
        try:
            db.add(GuardAuditEvent(
                workspace_id=ws_uuid,
                ai_tool="workflow",
                tool_call=block_id,
                input_summary=context_json[:500],
                decision=decision,
                rule_id=policy.rule_id,
                rule_message=policy.message,
                ts=now,
            ))
            db.flush()
        except Exception:
            pass

    for v in violations:
        message = v.message or f"Policy violation: {v.rule_id}"
        action  = v.action

        if action == "block":
            _record_event(v, "blocked")
            db.commit()
            raise RuntimeError(f"[ConductGuard] Blocked by policy '{v.rule_id}': {message}")

        elif action in ("warn", "approval"):
            _record_event(v, "warned")
            warnings.append({"rule_id": v.rule_id, "message": message})

        else:  # audit
            _record_event(v, "audited")

    if warnings or violations:
        db.commit()

    return {
        "status": "passed",
        "workspace_id": str(ws_uuid),
        "enforcement_mode": enforcement_mode,
        "rules_checked": len(policies),
        "violations": len(violations),
        "warnings": warnings,
    }
