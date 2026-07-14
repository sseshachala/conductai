"""
Guard block executor.

Applies ConductGuard policy checks before brain, tool, and output blocks.
Policy is loaded once at run start (executor.py) and passed as _policy_cache.
"""
from __future__ import annotations

import json
import re as _re
import uuid as _uuid
from datetime import datetime, timezone

import structlog
from app.modules.guard.models import GuardAuditEvent, chain_hash_for_insert, get_policy_hash

log = structlog.get_logger(__name__)


def _execute_guard(
    block: dict,
    state: dict,
    workspace_id: str,
    db,
    run_id=None,
    playbook_slug: str | None = None,
    workflow_id: str | None = None,
    user_email: str | None = None,
    workflow_name: str | None = None,
    _policy_cache: dict | None = None,
) -> dict:
    """
    Evaluate cached Guard policies against current workflow state.

    Called by _auto_guard_check before every brain / tool / output block.
    _policy_cache is always provided — loaded once at run start by executor.py.
    If cache is missing (Guard not installed / disabled), returns skipped.

    Violations handled per enforcement_mode:
      block  — raises RuntimeError, halts the run
      warn   — audit event written, warning in output, run continues
      audit  — silent audit event, run continues
    """
    if not _policy_cache:
        return {"status": "skipped", "reason": "guard_not_enabled"}

    try:
        ws_uuid = _uuid.UUID(_policy_cache["workspace_id"])
    except (ValueError, KeyError):
        return {"status": "skipped", "reason": "invalid_workspace_id"}

    policies         = list(_policy_cache.get("policies") or [])
    enforcement_mode = _policy_cache.get("enforcement_mode", "block")
    advisory         = bool(_policy_cache.get("advisory", False))

    # ── Build context from workflow state ─────────────────────────────────────
    context_dict = {k: v for k, v in state.items() if not k.startswith("__")}
    context_json = json.dumps(context_dict, default=str)

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

    # ── Evaluate rules ────────────────────────────────────────────────────────
    violations = []
    for policy in policies:
        # In workflow context, match_tool is irrelevant — all agent-persona rules apply

        if policy.get("match_pattern"):
            try:
                if not _re.search(policy["match_pattern"], context_json, _re.IGNORECASE):
                    continue
            except _re.error:
                continue

        if policy.get("match_path_pattern"):
            try:
                if not _re.search(policy["match_path_pattern"], path_text, _re.IGNORECASE):
                    continue
            except _re.error:
                continue

        violations.append(policy)

    # ── Handle violations ─────────────────────────────────────────────────────
    block_id              = block.get("id", "guard")
    now                   = datetime.now(timezone.utc)
    warnings: list[dict] = []
    audited:  list[dict] = []
    estimated_input_tokens = max(1, len(context_json) // 4)

    def _record_event(policy: dict, decision: str) -> None:
        try:
            prev_h, entry_h = chain_hash_for_insert(db, ws_uuid, now, block_id, decision)
            pol_h = get_policy_hash(db, ws_uuid)
            db.add(GuardAuditEvent(
                workspace_id=ws_uuid,
                ai_tool="workflow",
                tool_call=block_id,
                input_summary=context_json[:500],
                tokens_before=estimated_input_tokens,
                decision=decision,
                rule_id=policy.get("id") or policy.get("rule_id"),
                rule_message=policy.get("message"),
                ts=now,
                conductai_run_id=str(run_id) if run_id else None,
                conductai_workflow=workflow_name or playbook_slug,
                conductai_workflow_id=workflow_id,
                user_email=user_email,
                previous_hash=prev_h,
                entry_hash=entry_h,
                policy_hash=pol_h,
            ))
            db.flush()
        except Exception:
            pass

    for v in violations:
        v_rule_id = v.get("id") or v.get("rule_id")
        message   = v.get("message") or f"Policy violation: {v_rule_id}"
        action    = v.get("action")

        if advisory:
            _record_event(v, "audited")
            warnings.append({"rule_id": v_rule_id, "message": f"[advisory] {message}"})
            continue

        if action == "block":
            _record_event(v, "blocked")
            try:
                state["__governance"] = {
                    "blocked":      True,
                    "rule_id":      v_rule_id,
                    "rule_message": message,
                    "reason_code":  "GUARD_POLICY_BLOCKED",
                }
            except Exception:
                pass
            db.commit()
            raise RuntimeError(f"[ConductGuard] Blocked by policy '{v_rule_id}': {message}")

        elif action in ("warn", "approval"):
            _record_event(v, "warned")
            warnings.append({"rule_id": v_rule_id, "message": message})

        else:
            _record_event(v, "audited")
            audited.append({"rule_id": v_rule_id, "message": message})

    if warnings or violations:
        db.commit()

    return {
        "status":           "passed",
        "workspace_id":     str(ws_uuid),
        "enforcement_mode": enforcement_mode,
        "rules_checked":    len(policies),
        "violations":       len(violations),
        "warnings":         warnings,
        "audited":          audited,
    }
