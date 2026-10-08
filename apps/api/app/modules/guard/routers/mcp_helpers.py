"""ConductGuard remote MCP — platform helpers, policy matching, event recording and JSON-RPC envelope helpers."""

from __future__ import annotations

import json
import re
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text as _sql
from app.core.pii import redact_secrets
from app.modules.guard.models import GuardAuditEvent, chain_hash_for_insert, get_policy_hash
from app.modules.guard.policy_engine import compute_policy
from app.modules.guard.tool_groups import tool_matches


def _list_agents(db, ws_uuid: uuid.UUID) -> list[dict]:
    rows = db.execute(
        _sql("SELECT id, name, status FROM agents WHERE workspace_id = :w ORDER BY name LIMIT 100"),
        {"w": str(ws_uuid)},
    ).fetchall()
    return [{"id": str(r.id), "name": r.name, "status": r.status} for r in rows]


def _list_projects(db, ws_uuid: uuid.UUID) -> list[dict]:
    from sqlalchemy import select
    from app.models.project import Project

    rows = db.execute(
        select(Project.id, Project.name)
        .where(Project.workspace_id == ws_uuid)
        .order_by(Project.name, Project.id)
        .limit(100)
    ).all()
    # Projects have no description column; retain the existing response shape.
    return [{"id": str(r.id), "name": r.name, "description": None} for r in rows]


def _list_playbooks(db, ws_uuid: uuid.UUID) -> list[dict]:
    rows = db.execute(
        _sql("SELECT id, name, description FROM playbooks WHERE workspace_id = :w ORDER BY name LIMIT 100"),
        {"w": str(ws_uuid)},
    ).fetchall()
    return [{"id": str(r.id), "name": r.name, "description": r.description} for r in rows]


def _run_workflow(db, ws_uuid: uuid.UUID, workflow_id: str, payload: dict, user_email: str) -> dict:
    row = db.execute(
        _sql("SELECT id FROM workflows WHERE id = :wf AND workspace_id = :ws LIMIT 1"),
        {"wf": workflow_id, "ws": str(ws_uuid)},
    ).fetchone()
    if not row:
        raise ValueError(f"workflow {workflow_id} not found")
    run_id = str(uuid.uuid4())
    db.execute(
        _sql("""
            INSERT INTO runs (id, workflow_id, workspace_id, status, triggered_by, payload, created_at)
            VALUES (:id, :wf, :ws, 'pending', :by, :pl, :ts)
        """),
        {"id": run_id, "wf": workflow_id, "ws": str(ws_uuid),
         "by": user_email, "pl": json.dumps(payload), "ts": datetime.now(timezone.utc)},
    )
    db.commit()
    return {"run_id": run_id, "status": "pending"}


def _get_run_status(db, ws_uuid: uuid.UUID, workflow_id: str, run_id: str) -> dict:
    row = db.execute(
        _sql("SELECT status, outcome, started_at, completed_at FROM runs WHERE id = :r AND workflow_id = :wf AND workspace_id = :ws LIMIT 1"),
        {"r": run_id, "wf": workflow_id, "ws": str(ws_uuid)},
    ).fetchone()
    if not row:
        raise ValueError(f"run {run_id} not found")
    return {
        "status":       row.status,
        "outcome":      row.outcome,
        "started_at":   row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


def _detect_surface(client_info: dict) -> str:
    name = (client_info.get("name") or "").lower()
    if "desktop" in name:
        return "claude_desktop"
    if "work" in name or "teams" in name or "enterprise" in name:
        return "claude_work"
    if "claude" in name:
        return "claude_chat"
    if "codex" in name:
        return "codex"
    if "cursor" in name:
        return "cursor"
    if "windsurf" in name:
        return "windsurf"
    if "copilot" in name or "github" in name:
        return "copilot"
    return "unknown"


_ACTION_PRIORITY = {"block": 0, "approval": 1, "warn": 2, "audit": 3}


def _match_policy(
    tool_name: str,
    tool_input: dict,
    rules: list,
    gate: str | None = "action",
    agent_risk_tier: str | None = None,
) -> dict | None:
    """Return the most restrictive matching rule (block > approval > warn > audit).

    ``gate`` filters which rules are considered — only rules whose ``gates``
    list includes the given gate fire. Default ``"action"`` preserves
    pre-#1733 MCP behavior for every existing caller. Pass ``gate=None`` to
    skip gate filtering — used by pack-authoring tests.

    ``agent_risk_tier`` is the caller identity's tier. Rules with
    ``match_agent_risk_tier`` set only fire for callers whose tier matches
    exactly; null tier never matches a tier-requiring rule.
    """
    from app.modules.guard.enforcement import rule_matches_gate

    inp_text  = json.dumps(tool_input)
    path_keys = ["file_path", "path", "command"]
    path_text = " ".join(str(tool_input.get(k, "")) for k in path_keys)
    # #1770 follow-up: proxy rules can carry match_prompt / match_provider /
    # match_model (LLM-egress matchers). When the caller supplies these in
    # tool_input (guard_check_prompt does), respect them so proxy rules match
    # the same way they do through the LLM proxy PEP itself. Fields are inert
    # for the action-gate path because legacy callers don't send them.
    prompt_text = str(tool_input.get("prompt") or "")
    provider = tool_input.get("provider")
    model = tool_input.get("model")

    best: dict | None = None
    best_priority = 999

    for rule in rules:
        if gate is not None and not rule_matches_gate(rule, gate):
            continue
        required_tier = rule.get("match_agent_risk_tier")
        if required_tier is not None and required_tier != agent_risk_tier:
            continue
        if not tool_matches(tool_name, rule.get("match_tool")):
            continue

        # Proxy-native filters — apply only when the rule declares them.
        rp = rule.get("match_provider")
        if rp is not None and rp != provider:
            continue
        rm = rule.get("match_model")
        if rm:
            try:
                if not re.search(rm, model or "", re.IGNORECASE):
                    continue
            except re.error:
                continue
        mp = rule.get("match_prompt")
        if mp:
            try:
                if not re.search(mp, prompt_text, re.IGNORECASE):
                    continue
            except re.error:
                continue

        pattern = rule.get("match_pattern")
        if pattern:
            try:
                if not re.search(pattern, inp_text, re.IGNORECASE):
                    continue
            except re.error:
                continue

        path_pattern = rule.get("match_path_pattern")
        if path_pattern:
            try:
                if not re.search(path_pattern, path_text, re.IGNORECASE):
                    continue
            except re.error:
                continue

        priority = _ACTION_PRIORITY.get(rule.get("action", "audit"), 3)
        if priority < best_priority:
            best_priority = priority
            best = rule

    return best


_APPROVAL_FIELDS = ("approval_group", "approval_type", "approval_timeout_sec", "approval_notification", "guidance", "inject_guidance")


def _project_rule(r: dict) -> dict:
    """Trim a raw rule to the fields the matcher + downstream handlers use.
    Preserves approval_* fields so action=approval can honour rule spec.
    Preserves enforcement contract so surface-scoped matchers can honour
    proxy/hook/mcp/runtime = not_supported / conditional / hard."""
    out = {
        "rule_id":           r.get("id") or r.get("rule_id"),
        "match_tool":        r.get("match_tool"),
        "match_ai_tool":     r.get("match_ai_tool"),  # #1752: was dropped by projector
        "match_pattern":     r.get("match_pattern"),
        "match_path_pattern": r.get("match_path_pattern"),
        # #2401: the workflow runtime scopes MCP tool rules by server name;
        # dropping this made server-scoped rules apply to every server.
        "match_mcp_server":  r.get("match_mcp_server"),
        # #1770 follow-up: proxy-native matchers preserved so guard_check_prompt
        # honours them from the MCP transport. Legacy MCP callers pass no
        # prompt/provider/model in tool_input, so these fields are inert
        # for the action-gate path.
        "match_prompt":      r.get("match_prompt"),
        "match_provider":    r.get("match_provider"),
        "match_model":       r.get("match_model"),
        "action":            r.get("action"),
        "message":           r.get("message"),
        "pack":              r.get("pack") or r.get("pack_slug"),
        "gates":             r.get("gates") or ["action"],  # #1733: expose gate list to consumers
        "enforcement":       r.get("enforcement") or {},
    }
    for k in _APPROVAL_FIELDS:
        if k in r and r[k] is not None:
            out[k] = r[k]
    return out


def _get_rules(db: Session, ws_uuid: uuid.UUID, persona: str = "agent") -> list[dict]:
    """Active ruleset for the requested persona.

    Two personas today (locked by rule schema, not this function):
      - ``"agent"``  — governs what AI does on the machine. MCP + hook + runtime
                        PEPs call this. Gate: ``action``.
      - ``"proxy"``  — governs outbound LLM traffic. LLM proxy PEP calls this
                        directly; the ``guard_check_prompt`` MCP verb also calls
                        this so LiteLLM-style callers can reach proxy rules
                        without a new transport. Gate: ``prompt`` (``response``
                        when that path lands).

    Property 8 stays clean: MCP is the *transport*; the proxy PEP is the
    *enforcement point* that declares ``{prompt, response}`` capability.
    """
    rules = compute_policy(db, ws_uuid, persona)
    return [_project_rule(r) for r in rules]


#: ``"proxy"`` kept for backward compat; new writes should use ``"gateway"``.
_PERSONAS = ["agent", "proxy", "gateway"]


def _record_event(
    db: Session,
    ws_uuid: uuid.UUID,
    tool_name: str,
    tool_input: dict,
    decision: str,
    rule_id: str | None,
    ai_tool: str,
    user_email: str,
    session_id: str,
    *,
    conductai_run_id: str | None = None,
    conductai_workflow: str | None = None,
    prompt: str | None = None,
    source: str = "mcp",
    rule_message: str | None = None,
) -> None:
    ts = datetime.now(timezone.utc)
    prev_hash, entry_hash = chain_hash_for_insert(db, ws_uuid, ts, tool_name, decision)
    policy_hash = get_policy_hash(db, ws_uuid)

    raw_summary = redact_secrets(json.dumps(tool_input)[:500])[0][:200]
    if prompt:
        raw_summary = f"[prompt: {prompt[:100]}] {raw_summary}"

    actor = db.info.get("mcp_actor") or {}
    event = GuardAuditEvent(
        workspace_id=ws_uuid,
        clerk_user_id=actor.get("clerk_user_id", user_email),
        agent_identity_id=actor.get("agent_identity_id"),
        user_email=user_email,
        ai_tool=ai_tool,
        tool_call=tool_name,
        source=source,
        input_summary=raw_summary,
        decision=decision,
        rule_id=rule_id,
        rule_message=rule_message,
        hook_session_id=session_id,
        ts=ts,
        conductai_run_id=conductai_run_id,
        conductai_workflow=conductai_workflow,
        previous_hash=prev_hash,
        entry_hash=entry_hash,
        policy_hash=policy_hash,
    )
    if actor.get("credential_session_id"):
        event.routing_meta = {"credential_session_id": actor["credential_session_id"]}
    db.add(event)
    identity = db.info.get("federation_identity")
    if identity is not None:
        from app.models.audit_log import AuditLog
        from app.core.workspace_context import set_workspace_rls
        from app.modules.auth.federation.mcp_ingress import provenance
        set_workspace_rls(db, ws_uuid)
        event.routing_meta = {**(event.routing_meta or {}), "federation": provenance(identity), "evidence_kind": "policy_check"}
        db.flush()
        db.add(AuditLog(workspace_id=ws_uuid, action="federation.guard.decision",
                        resource_type="guard_audit_event", resource_id=str(event.id),
                        meta={**provenance(identity), "decision": decision, "rule_id": rule_id}))
    db.commit()

    # Slack + webhook + PagerDuty + email fan-out for blocks/warns.
    # Uses caller-provided `source` so Guard Activity attribution is precise
    # (mcp vs hook vs runtime vs proxy).
    if decision in ("blocked", "warned"):
        try:
            from app.modules.guard.routers.events import notify_guard_block
            notify_guard_block(db, ws_uuid, decision=decision, rule_id=rule_id,
                               user_email=user_email, tool=tool_name, source=source)
        except Exception:
            pass


def _ok(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _err(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


# Governance: when a tool_call handler runs, we stamp the response text with
# [ws:xxxxxxxx] so the model can spot silent workspace drift (dashboard switch,
# token rotation, etc) without having to poll guard_status every turn.
# Init / OAuth responses leave this unset, so their text stays unchanged.
_tool_ws_ctx: ContextVar[uuid.UUID | None] = ContextVar("guard_mcp_tool_ws", default=None)


def _text(msg_id, text: str) -> dict:
    _ws = _tool_ws_ctx.get()
    if _ws is not None:
        text = f"[ws:{str(_ws)[:8]}] {text}"
    return _ok(msg_id, {"content": [{"type": "text", "text": text}]})
