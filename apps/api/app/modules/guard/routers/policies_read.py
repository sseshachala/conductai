"""ConductGuard policies — generate, sync, list and coverage endpoints."""

from __future__ import annotations

import hashlib
import os
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.auth import (
    get_guard_hook_auth,
    get_workspace_id,
    require_permission,
)
from app.core.database import get_db
from app.modules.guard.models import (
    GuardAuditEvent,
    GuardConfig,
    GuardRuleOverride,
    WorkspaceCustomRule,
    WorkspaceSkillPack,
)
from app.modules.guard.policy_engine import (
    compute_policy,
)
from app.modules.guard.coverage import workspace_coverage_matrix
from app.modules.guard.enforcement import (
    is_hook_applicable_rule,
)
from app.modules.guard.routers.policies_schemas import (
    EnforcementCoverageOut,
    PackCoverageMatrixOut,
    PolicyGenerateOut,
    PolicyGenerateRequest,
    PolicyOut,
    PolicySyncOut,
    PolicySyncRule,
)
from app.modules.guard.routers.policies_helpers import (
    _GENERATE_SYSTEM,
    _VALID_ACTIONS,
    _audit_exception_transitions,
    _custom_to_out,
    _org_ws_subquery,
    _pack_rule_to_out,
    _resolve_workspace_pack,
    _ws_uuid,
)

router = APIRouter(prefix="/guard/policies", tags=["guard-policies"])


@router.post("/generate", response_model=PolicyGenerateOut)
def generate_policy(
    body: PolicyGenerateRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.edit")),
):
    """LLM-generate a rule from a plain-English description."""
    from app.routers.generate import _resolve_anthropic_key

    resolved_ws = body.workspace_id or workspace_id
    api_key = _resolve_anthropic_key(resolved_ws, body.environment_id, db) or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        env_hint = "selected environment" if body.environment_id else "Default environment"
        raise HTTPException(
            status_code=503,
            detail=f"Anthropic API key not configured for the {env_hint} — add it in Settings -> Environments",
        )

    try:
        from app.runtime.llm_client import client_for, LLMTextBlock
        client = client_for("anthropic", api_key)
        response = client.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=_GENERATE_SYSTEM,
            messages=[{"role": "user", "content": body.prompt}],
        )
        first = response.content[0] if response.content else None
        raw = first.text.strip() if isinstance(first, LLMTextBlock) else ""
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=422,
            detail="Could not generate a rule from that description — try being more specific.",
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Rule generation failed — check that your Anthropic API key is valid in Settings -> Environments.",
        )

    action = data.get("action", "block")
    if action not in _VALID_ACTIONS:
        action = "block"

    return PolicyGenerateOut(
        rule_id=data.get("rule_id", "custom-rule"),
        description=data.get("description", ""),
        match_tool=data.get("match_tool", "*"),
        match_pattern=data.get("match_pattern") or None,
        match_path_pattern=data.get("match_path_pattern") or None,
        action=action,
        message=data.get("message", ""),
    )


@router.get("/sync", response_model=PolicySyncOut)
def sync_policies(
    workspace_id: str = Query(...),
    db: Session = Depends(get_db),
    _auth: str = Depends(get_guard_hook_auth),
):
    """Return the current active ruleset for the hook binary or MCP server.

    When the workspace has a signing key configured, the response includes a
    HMAC-SHA256 signature field. The canonical body used for signing is the
    JSON-serialised dict of all fields except signature and signed_at,
    with keys sorted and no extra whitespace.
    """
    import hmac as _hmac
    from app.modules.guard.models import WorkspaceSigningKey

    ws_uuid = _ws_uuid(workspace_id)

    gc = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
    # ponytail: sync always uses surface="agent" — GuardConfig.persona is developer type, not surface
    active_rules = compute_policy(db, ws_uuid, "agent")
    hook_rules = [rule for rule in active_rules if is_hook_applicable_rule(rule)]
    _audit_exception_transitions(db, ws_uuid, audit_use=True)
    version_hash = hashlib.sha256(json.dumps(hook_rules, sort_keys=True).encode()).hexdigest()[:16]
    version = f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}-{version_hash}"

    out = PolicySyncOut(
        workspace_id=workspace_id,
        version=version,
        persona="agent",
        fail_mode=getattr(gc, "fail_mode", "fail_open") if gc else "fail_open",
        advisory_mode=getattr(gc, "advisory_mode", False) if gc else False,
        rules=[
            PolicySyncRule(
                rule_id=r["id"],
                match_tool=r.get("match_tool"),
                match_ai_tool=r.get("match_ai_tool"),
                match_pattern=r.get("match_pattern"),
                match_path_pattern=r.get("match_path_pattern"),
                action=r["action"],
                message=r.get("message"),
            )
            for r in hook_rules
        ],
    )

    # Sign the response if the workspace has a signing key.
    signing_key_row = db.get(WorkspaceSigningKey, ws_uuid)
    if signing_key_row and signing_key_row.key_bytes:
        signed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        body_dict = out.model_dump(exclude={"signature", "signed_at"})
        body_dict["rules"] = [r.model_dump() for r in out.rules]
        canonical = json.dumps(body_dict, sort_keys=True, separators=(",", ":"))
        sig = _hmac.new(signing_key_row.key_bytes, canonical.encode(), hashlib.sha256).hexdigest()
        out.signature = sig
        out.signed_at = signed_at

    return out


@router.get("", response_model=list[PolicyOut])
def list_policies(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.view")),
):
    """List all policies for a workspace — custom rules + active pack rules."""
    ws_uuid = _ws_uuid(workspace_id)
    _audit_exception_transitions(db, ws_uuid, audit_use=False)
    org_ws = _org_ws_subquery(db, workspace_id)

    out: list[PolicyOut] = []

    # Last-hit timestamp per rule_id, aggregated across org workspaces
    last_hits: dict[str, datetime] = dict(
        db.query(GuardAuditEvent.rule_id, func.max(GuardAuditEvent.ts))
        .filter(GuardAuditEvent.workspace_id.in_(org_ws))
        .filter(GuardAuditEvent.rule_id.isnot(None))
        .group_by(GuardAuditEvent.rule_id)
        .all()
    )

    # 1. Custom rules
    customs = (
        db.query(WorkspaceCustomRule)
        .filter(WorkspaceCustomRule.workspace_id.in_(org_ws))
        .order_by(WorkspaceCustomRule.created_at.asc())
        .all()
    )
    out.extend(_custom_to_out(c) for c in customs)

    # 2. Pack rules (with overrides applied)
    installed = (
        db.query(WorkspaceSkillPack)
        .filter(WorkspaceSkillPack.workspace_id.in_(org_ws))
        .order_by(WorkspaceSkillPack.installed_at)
        .all()
    )
    overrides = {
        o.rule_id: o
        for o in db.query(GuardRuleOverride)
        .filter(GuardRuleOverride.workspace_id.in_(org_ws))
        .all()
    }
    seen: set[str] = set()
    for wp in installed:
        pack = _resolve_workspace_pack(db, wp)
        if not pack:
            continue
        for rule in pack.rules or []:
            if rule["id"] in seen:
                continue
            seen.add(rule["id"])
            out.append(_pack_rule_to_out(rule, wp.pack_slug, wp.installed_at, ws_uuid, overrides.get(rule["id"])))

    for p in out:
        p.last_triggered = last_hits.get(p.rule_id)

    return out


@router.get("/coverage", response_model=list[EnforcementCoverageOut])
def get_enforcement_coverage(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.view")),
):
    """Generated enforcement matrix for the workspace's resolved policy sources."""
    return workspace_coverage_matrix(db, _ws_uuid(workspace_id))


@router.get("/packs/{pack_slug}/coverage-matrix", response_model=PackCoverageMatrixOut)
def get_pack_coverage_matrix(
    pack_slug: str,
    db: Session = Depends(get_db),
    _workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.view")),
) -> PackCoverageMatrixOut:
    """#1751 PR 5 — per-pack surface × gate coverage summary.

    Answers "does conduct-hipaa cover response-gate leakage on the proxy?"
    without walking every rule client-side. Feeds the Policies UI pack
    detail table.

    Missing pack returns a zero-filled envelope so callers can render an
    empty state without null checks.
    """
    from app.modules.guard.coverage import pack_coverage_matrix

    return PackCoverageMatrixOut(**pack_coverage_matrix(db, pack_slug))
