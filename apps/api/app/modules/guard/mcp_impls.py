"""Guard MCP tool impls — extracted from the /guard/mcp inline dispatch
chain so both the legacy endpoint and the new /mcp adapter (#1219 Phase 3b)
call the same function.

Byte-parity guarantee by construction: single source of truth means the
two endpoints cannot diverge — no possibility of drift between the guard
MCP surface and the consolidated /mcp surface.

Contract:
- Every impl returns the text-content payload (a plain string). Caller
  wraps it in MCP text-content envelope (both endpoints do).
- Impls read + write via ctx.db but do NOT open/close the session — the
  caller owns the session lifecycle (matches the pre-refactor behavior).
- Impls call ctx.db.commit() where the pre-refactor code did (post_finding,
  trigger_fix, guard_discover_register).
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text as _sql
from sqlalchemy.orm import Session

from app.modules.guard import approval as _approval
from app.modules.guard.models import (
    GuardApprovalRequest,
    GuardAuditEvent,
    GuardConfig,
)
from app.models.workspace import Workspace


@dataclass
class GuardCtx:
    """Bundle every guard tool needs at dispatch time. Immutable per request.

    Both /guard/mcp and /mcp construct this from their transport auth and
    pass it to dispatch_guard_tool(). Nothing here should be reused across
    requests.
    """
    db: Session
    ws_uuid: uuid.UUID
    workspace_id: str | None
    resolved_token: str
    clerk_user_id: str | None
    user_email: str | None
    ai_tool: str
    session_id: str


def dispatch_guard_tool(
    tool_name: str,
    arguments: dict[str, Any],
    ctx: GuardCtx,
) -> str:
    """Run one guard MCP tool. Returns the text-content payload string.

    Every branch here is a verbatim move from the pre-refactor
    `apps/api/app/modules/guard/routers/mcp.py::mcp_endpoint` dispatch
    chain (lines 732-1209). The only transforms:
      1. `return JSONResponse(_text(msg_id, X))` → `return X`
      2. Closure vars → `ctx.X`
      3. Late imports for helpers that live in the router module (avoids
         circular import while keeping the diff minimal).
    """
    # Late imports: mcp.py already loaded these helpers; importing at
    # module load would cycle through the router that itself may import
    # this module for /guard/mcp integration.
    from app.modules.guard.routers.mcp import (
        _get_rules,
        _get_rules_for_pack,
        _list_agents,
        _list_playbooks,
        _list_projects,
        _match_policy,
        _record_event,
        _run_workflow,
        _get_run_status,
    )

    db = ctx.db
    ws_uuid = ctx.ws_uuid
    workspace_id = ctx.workspace_id
    resolved_token = ctx.resolved_token
    clerk_user_id = ctx.clerk_user_id
    user_email = ctx.user_email
    ai_tool = ctx.ai_tool
    session_id = ctx.session_id

    if tool_name == "guard_status":
        rules = _get_rules(db, ws_uuid)
        _ws_out = workspace_id or (str(ws_uuid) if ws_uuid else None)
        _pv = None
        _pv_at = None
        try:
            from app.modules.guard.models import GuardPolicyCache as _PC
            _cache = db.get(_PC, (ws_uuid, "agent"))
            if _cache:
                _pv = _cache.version_hash
                _pv_at = _cache.computed_at.isoformat() if _cache.computed_at else None
        except Exception:
            pass  # never fail guard_status over policy-version lookup
        return json.dumps({
            "workspace_id":       _ws_out,
            "email":              user_email,
            "rules_active":       len(rules),
            "policy_version":     _pv,
            "policy_computed_at": _pv_at,
        }, indent=2)

    if tool_name == "guard_check":
        inner_tool = arguments.get("tool_name", "")
        inner_input = arguments.get("tool_input") or {}
        _run_id = arguments.get("conduct_run_id") or None
        _workflow = arguments.get("conduct_workflow") or None
        _pack = arguments.get("pack") or None
        _prompt = arguments.get("prompt") or None
        try:
            if _pack:
                rules_or_err = _get_rules_for_pack(db, ws_uuid, _pack)
                if isinstance(rules_or_err, str):
                    return rules_or_err
                rules = rules_or_err
            else:
                rules = _get_rules(db, ws_uuid)
        except Exception as _eval_err:
            _cfg = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
            if _cfg and not _cfg.deny_on_error:
                return f"advisory: policy eval error (fail-open): {_eval_err}"
            _record_event(db, ws_uuid, inner_tool, inner_input, "blocked", "policy_eval_error", ai_tool, user_email, session_id, conductai_run_id=_run_id, conductai_workflow=_workflow, prompt=_prompt)
            return f"BLOCKED — policy evaluation failed. Request denied by fail-closed default."

        _cfg = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
        _advisory = _cfg.advisory_mode if _cfg else False

        rule = _match_policy(inner_tool, inner_input, rules)

        if rule is None:
            _record_event(db, ws_uuid, inner_tool, inner_input, "allowed", None, ai_tool, user_email, session_id, conductai_run_id=_run_id, conductai_workflow=_workflow, prompt=_prompt)
            return "ok"

        action = rule.get("action", "audit")
        rule_id = rule.get("rule_id", "unknown")
        message = rule.get("message") or f"Policy violation ({rule_id})"
        _guidance_suffix = ""
        _guidance_text = rule.get("guidance") or message
        if rule.get("inject_guidance") and _guidance_text:
            _guidance_suffix = f"\n\nGUIDANCE — {_guidance_text}"

        if _advisory:
            _record_event(db, ws_uuid, inner_tool, inner_input, "audited", rule_id, ai_tool, user_email, session_id, conductai_run_id=_run_id, conductai_workflow=_workflow, prompt=_prompt)
            return f"advisory: {message} [rule: {rule_id}]{_guidance_suffix}"

        if action == "block":
            _record_event(db, ws_uuid, inner_tool, inner_input, "blocked", rule_id, ai_tool, user_email, session_id, conductai_run_id=_run_id, conductai_workflow=_workflow, prompt=_prompt)
            return f"BLOCKED — {message}  [rule: {rule_id}]{_guidance_suffix}"

        if action == "warn":
            already_warned = db.query(GuardAuditEvent).filter(
                GuardAuditEvent.workspace_id == ws_uuid,
                GuardAuditEvent.hook_session_id == session_id,
                GuardAuditEvent.rule_id == rule_id,
                GuardAuditEvent.decision == "warned",
            ).first()
            if already_warned:
                return "ok"
            _record_event(db, ws_uuid, inner_tool, inner_input, "warned", rule_id, ai_tool, user_email, session_id, conductai_run_id=_run_id, conductai_workflow=_workflow, prompt=_prompt)
            return f"WARNING — {message}  [rule: {rule_id}]{_guidance_suffix}"

        if action == "approval":
            prior = None
            if session_id:
                prior = (
                    db.query(GuardApprovalRequest)
                    .filter(
                        GuardApprovalRequest.workspace_id == ws_uuid,
                        GuardApprovalRequest.rule_id == rule_id,
                        GuardApprovalRequest.session_id == str(session_id),
                    )
                    .order_by(GuardApprovalRequest.created_at.desc())
                    .first()
                )
                if prior:
                    prior = _approval.sweep_if_timed_out(db, prior)

            verdict, block_reason = _approval.resume_verdict(prior)
            if verdict == "proceed":
                _record_event(db, ws_uuid, inner_tool, inner_input, "allowed", rule_id, ai_tool, user_email, session_id, conductai_run_id=_run_id, conductai_workflow=_workflow, prompt=_prompt)
                return "ok"
            if verdict == "block":
                _record_event(db, ws_uuid, inner_tool, inner_input, "blocked", rule_id, ai_tool, user_email, session_id, conductai_run_id=_run_id, conductai_workflow=_workflow, prompt=_prompt)
                return f"BLOCKED — {block_reason}  [rule: {rule_id}]{_guidance_suffix}"
            if verdict == "wait":
                return _approval.pending_marker(prior)
            # verdict == "create"
            req = _approval.create_approval_request(
                db,
                workspace_id=ws_uuid,
                rule=rule,
                tool_name=inner_tool,
                tool_input=inner_input,
                requester_email=user_email,
                requester_user_id=clerk_user_id,
                surface=ai_tool,
                session_id=str(session_id) if session_id else None,
            )
            _approval.dispatch_approval_notifications(db, req)
            return _approval.pending_marker(req)

        # audit action fires the side-effect but returns "ok" to the agent
        _record_event(db, ws_uuid, inner_tool, inner_input, "audited", rule_id, ai_tool, user_email, session_id, conductai_run_id=_run_id, conductai_workflow=_workflow, prompt=_prompt)
        return "ok"

    if tool_name == "guard_sync":
        rules = _get_rules(db, ws_uuid)
        return f"Policy is live — {len(rules)} active rule(s). Remote MCP always uses latest."

    if tool_name == "guard_enable":
        rules = _get_rules(db, ws_uuid)
        _record_event(db, ws_uuid, "guard_enable", {}, "allowed", None, ai_tool, user_email, session_id)
        snippet = (
            "You have ConductGuard active. "
            "Call guard_activity ONCE at the start of a user request with a one-line summary. "
            "Call guard_check ONCE per intent (not per file/command). Re-check only when scope changes "
            "— e.g. reads → writes, local → network, or entering a new task. "
            "If the response is BLOCKED, stop and explain the policy rule. "
            "If WARNING, proceed but surface the warning inline. "
            "If the response is empty or 'ok', proceed silently — do NOT narrate the check in chat."
        )
        mcp_url = "https://api.conductai.ai/guard/mcp"
        desktop_config = (
            '{\n'
            '  "mcpServers": {\n'
            '    "conductguard": {\n'
            '      "command": "npx",\n'
            '      "args": ["-y", "mcp-remote", "' + mcp_url + '",\n'
            '               "--header", "Authorization: Bearer ' + resolved_token + '"]\n'
            '    }\n'
            '  }\n'
            '}'
        )
        return (
            f"✓ ConductGuard is connected — {len(rules)} active rule(s).\n\n"
            f"**Claude.ai Projects** — paste this into Project Instructions "
            f"(Projects → your project → Instructions):\n\n"
            f"---\n{snippet}\n---\n\n"
            f"**Claude Desktop** — add this to ~/Library/Application Support/Claude/claude_desktop_config.json "
            f"(Mac) or %APPDATA%\\Claude\\claude_desktop_config.json (Windows), then restart Claude Desktop:\n\n"
            f"```json\n{desktop_config}\n```\n\n"
            f"Until then, Guard is active for this conversation only."
        )

    if tool_name == "guard_spend":
        days = max(1, min(int(arguments.get("days", 1)), 30))
        rows = db.execute(
            _sql("""
                SELECT provider, model,
                       COUNT(*)            AS calls,
                       SUM(tokens_before)  AS in_tokens,
                       SUM(tokens_after)   AS out_tokens,
                       SUM(cost_usd_after) AS usd
                FROM guard_audit_events
                WHERE workspace_id = :ws AND source = 'proxy'
                  AND ts > now() - (:days || ' days')::interval
                GROUP BY provider, model
                ORDER BY usd DESC NULLS LAST
                LIMIT 20
            """),
            {"ws": ws_uuid, "days": days},
        ).fetchall()
        if not rows:
            return f"No proxy traffic in the last {days} day(s)."
        total = sum(float(r[5] or 0) for r in rows)
        lines = [f"Proxy spend - last {days} day(s):  ${total:.4f} total", ""]
        for prov, model, calls, in_t, out_t, usd in rows:
            lines.append(
                f"  {prov}/{model or '?'}: {calls} calls, "
                f"in {int(in_t or 0):,} / out {int(out_t or 0):,}, "
                f"${(usd or 0):.4f}"
            )
        return "\n".join(lines)

    if tool_name == "guard_local_risks":
        rows = db.execute(
            _sql("""
                SELECT provider, ai_tool, input_summary AS path,
                       user_email, ts
                FROM guard_audit_events
                WHERE workspace_id = :ws AND source = 'local_audit'
                ORDER BY ts DESC LIMIT 50
            """),
            {"ws": ws_uuid},
        ).fetchall()
        if not rows:
            return "No local key risks flagged. All devs are clean."
        lines = [f"Open local key risks ({len(rows)}):", ""]
        for prov, ai_tool_row, path, email, ts in rows:
            who = email or "unknown dev"
            lines.append(f"  [{prov}] {path} ({ai_tool_row}) - {who}")
        return "\n".join(lines)

    if tool_name == "guard_activity":
        summary = arguments.get("summary", "")
        category = arguments.get("category", "other")
        _run_id = arguments.get("conduct_run_id") or None
        _workflow = arguments.get("conduct_workflow") or None
        _record_event(db, ws_uuid, "guard_activity", {"summary": summary, "category": category}, "allowed", None, ai_tool, user_email, session_id, conductai_run_id=_run_id, conductai_workflow=_workflow)
        return f"Activity logged — '{summary}'"

    if tool_name == "guard_recent_activity":
        _days = max(1, min(int(arguments.get("days") or 1), 30))
        _limit = max(1, min(int(arguments.get("limit") or 20), 100))
        _decision = arguments.get("decision") or None
        if _decision == "ok":  # accept legacy alias; storage layer writes "allowed"
            _decision = "allowed"
        _rule_id = arguments.get("rule_id") or None

        _parts = [
            "SELECT ts, decision, rule_id, tool_call, ai_tool",
            "FROM guard_audit_events",
            "WHERE workspace_id = :ws",
            "AND ts > now() - (:days || ' days')::interval",
        ]
        _params = {"ws": ws_uuid, "days": _days, "lim": _limit + 1}
        if user_email:
            _parts.append("AND user_email = :email"); _params["email"] = user_email
        if _decision:
            _parts.append("AND decision = :dec"); _params["dec"] = _decision
        if _rule_id:
            _parts.append("AND rule_id = :rid"); _params["rid"] = _rule_id
        _parts.append("ORDER BY ts DESC LIMIT :lim")
        _rows = db.execute(_sql(" ".join(_parts)), _params).fetchall()

        _has_more = len(_rows) > _limit
        _rows = _rows[:_limit]

        if not _rows:
            return f"No events in the last {_days} day(s)."

        _hdr = f"Last {len(_rows)} event(s) - past {_days} day(s)"
        if _has_more:
            _hdr += " (more available — raise `limit` or narrow with `decision`/`rule_id`)"
        _hdr += ":"
        _lines = [_hdr]
        for _ts, _dec, _rid, _tc, _ait in _rows:
            _t = _ts.strftime("%Y-%m-%d %H:%MZ") if _ts else "-"
            _decs = (_dec or "-").ljust(8)
            _rids = ((_rid or ("none" if _dec == "allowed" else "-"))[:24]).ljust(24)
            _call = (_tc or _ait or "-")[:60]
            _lines.append(f"{_t}  {_decs}  {_rids}  {_call}")
        return "\n".join(_lines)

    if tool_name == "guard_discover":
        from app.modules.guard.models import DiscoveredAgent
        _ws = db.query(Workspace).filter(Workspace.id == ws_uuid).first()
        if _ws and _ws.org_id:
            _org_ws = db.query(Workspace.id).filter(Workspace.org_id == _ws.org_id)
        elif _ws and _ws.owner_id:
            _org_ws = db.query(Workspace.id).filter(Workspace.owner_id == _ws.owner_id)
        else:
            _org_ws = db.query(Workspace.id).filter(Workspace.id == ws_uuid)
        all_agents = db.query(DiscoveredAgent).filter(DiscoveredAgent.workspace_id.in_(_org_ws)).limit(200).all()
        total = len(all_agents)
        covered = sum(1 for a in all_agents if a.under_guard)
        missing = total - covered
        pct = round(covered / total * 100) if total else 0
        agents_list = [{
            "id": str(a.id), "name": a.name, "framework": a.framework,
            "source": a.source, "location": a.location,
            "governed": bool(a.under_guard),
        } for a in all_agents]
        if total == 0:
            return "No discovery scan found. Run `conduct guard discover` from your machine first."
        return f"Guard coverage: {covered} of {total} agents ({pct}%)\n{missing} shadow agents not under Guard.\n\n" + json.dumps(agents_list, indent=2)

    if tool_name == "guard_discover_register":
        from app.modules.guard.models import DiscoveredAgent
        agent_id = arguments.get("agent_id", "")
        try:
            row = db.query(DiscoveredAgent).filter(
                DiscoveredAgent.id == uuid.UUID(agent_id),
                DiscoveredAgent.workspace_id == ws_uuid,
            ).first()
            if not row:
                return f"Agent {agent_id} not found."
            row.under_guard = True
            row.last_seen_at = datetime.now(timezone.utc)
            db.commit()
            return f"Agent '{row.name or agent_id}' ({row.framework}) is now under Guard."
        except Exception as e:
            return f"Error registering agent: {e}"

    if tool_name == "post_finding":
        from app.models.security_finding import SecurityFinding as SF
        from app.core.queue import enqueue_run
        _sev = arguments.get("severity", "info")
        _typ = arguments.get("type", "other")
        _valid_sev = {"critical", "high", "medium", "low", "info"}
        _valid_typ = {"injection", "path-traversal", "secret-leak", "auth-bypass", "crypto", "guard_violation", "other"}
        if _sev not in _valid_sev:
            return f"Error — severity must be one of: {', '.join(sorted(_valid_sev))}"
        if _typ not in _valid_typ:
            return f"Error — type must be one of: {', '.join(sorted(_valid_typ))}"
        _now_dt = datetime.now(timezone.utc)
        finding = SF(
            id=uuid.uuid4(),
            workspace_id=ws_uuid,
            tool=arguments.get("tool", "mcp"),
            severity=_sev,
            type=_typ,
            description=arguments.get("description", ""),
            file=arguments.get("file"),
            line=arguments.get("line"),
            repo_full_name=arguments.get("repo_full_name"),
            suggested_fix=arguments.get("suggested_fix"),
            reporter_email=user_email,
            status="open",
            created_at=_now_dt,
            updated_at=_now_dt,
        )
        db.add(finding)
        db.flush()
        try:
            from app.models.run import Run
            from app.routers.security import (
                _SECURITY_LOOP_SLUG,
                _build_finding_trigger_state,
                _find_security_workflow,
                _load_security_config_defaults,
            )
            _wf = _find_security_workflow(db, ws_uuid, _SECURITY_LOOP_SLUG)
            if _wf and _wf.current_version_id:
                _cfg = _load_security_config_defaults(db, ws_uuid)
                _run = Run(
                    workflow_version_id=_wf.current_version_id,
                    triggered_by="security_finding",
                    status="pending",
                    state=_build_finding_trigger_state(finding, _cfg, "security_finding"),
                )
                db.add(_run)
                db.flush()
                finding.run_id = str(_run.id)
                enqueue_run(str(_run.id))
        except Exception:
            pass
        db.commit()
        return json.dumps({
            "finding_id": str(finding.id),
            "status": "open",
            "message": f"Finding reported — severity={_sev}, type={_typ}. Use trigger_fix to enqueue an automated fix.",
        }, indent=2)

    if tool_name == "trigger_fix":
        from app.models.security_finding import SecurityFinding as SF
        from app.models.run import Run
        from app.core.queue import enqueue_run
        _fid = arguments.get("finding_id", "")
        try:
            _fid_uuid = uuid.UUID(_fid)
        except ValueError:
            return "Error — finding_id must be a valid UUID"
        finding = db.query(SF).filter(SF.id == _fid_uuid, SF.workspace_id == ws_uuid).first()
        if not finding:
            return f"Error — finding {_fid} not found"
        from app.routers.security import (
            _SECURITY_AUTOPILOT_FIX_SLUG,
            _build_finding_trigger_state,
            _find_security_workflow,
            _load_security_config_defaults,
        )
        _wf = _find_security_workflow(db, ws_uuid, _SECURITY_AUTOPILOT_FIX_SLUG)
        if not _wf or not _wf.current_version_id:
            return "Error — security-autopilot-fix playbook is not installed in this workspace"
        _cfg = _load_security_config_defaults(db, ws_uuid)
        _run = Run(
            workflow_version_id=_wf.current_version_id,
            triggered_by="security_finding_fix",
            status="pending",
            state=_build_finding_trigger_state(finding, _cfg, "security_finding_fix"),
        )
        db.add(_run)
        db.flush()
        enqueue_run(str(_run.id))
        finding.status = "triaging"
        finding.updated_at = datetime.now(timezone.utc)
        db.commit()
        return json.dumps({
            "run_id": str(_run.id),
            "finding_id": str(finding.id),
            "status": "triaging",
            "message": "security-autopilot-fix enqueued — finding set to triaging.",
        }, indent=2)

    if tool_name == "conduct_list_agents":
        return json.dumps(_list_agents(db, ws_uuid), indent=2)

    if tool_name == "conduct_list_projects":
        return json.dumps(_list_projects(db, ws_uuid), indent=2)

    if tool_name == "conduct_list_playbooks":
        return json.dumps(_list_playbooks(db, ws_uuid), indent=2)

    if tool_name == "conduct_run_workflow":
        wf_id = arguments.get("workflow_id", "")
        payload = arguments.get("payload") or {}
        if not wf_id:
            return "Error — workflow_id is required."
        try:
            result = _run_workflow(db, ws_uuid, wf_id, payload, user_email)
            return json.dumps(result, indent=2)
        except ValueError as e:
            return f"Error — {e}"

    if tool_name == "conduct_get_run":
        wf_id = arguments.get("workflow_id", "")
        run_id = arguments.get("run_id", "")
        if not wf_id or not run_id:
            return "Error — workflow_id and run_id are required."
        try:
            result = _get_run_status(db, ws_uuid, wf_id, run_id)
            return json.dumps(result, indent=2)
        except ValueError as e:
            return f"Error — {e}"

    return f"Unknown tool: {tool_name}"
