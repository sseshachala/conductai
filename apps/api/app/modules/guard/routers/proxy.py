"""
Guard Proxy — universal LLM gateway.

Receives LLM API calls from any AI tool that respects standard SDK env vars
(ANTHROPIC_BASE_URL, OPENAI_BASE_URL, PERPLEXITY_BASE_URL). Resolves the caller
via member_token, applies Guard policies, looks up the workspace vendor key,
and forwards upstream (default = real vendor API, override = customer's own
gateway like Portkey/Helicone).

V1 scope (see memory/project_guard_proxy_v1.md):
  - Anthropic + OpenAI + Perplexity endpoints
  - Stream-through SSE (no mid-stream cutoff)
  - Pre-call BLOCK only, fail-closed on errors
  - Audit event with lineage per call
  - Conduct's own runtime stays direct vault access (not via proxy yet)

Auth: SDK puts the member token in the request:
  - Anthropic SDK:   x-api-key: guard-mt-<token>
  - OpenAI SDK:      Authorization: Bearer guard-mt-<token>
"""
from __future__ import annotations

import json
import time
import uuid

from datetime import datetime, timezone
from typing import AsyncIterator
from urllib.parse import urlparse as _urlparse

import httpx
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

import re

from app.core.auth import get_workspace_id, require_permission, resolve_agent_token, token_is_expired
from app.core.pii import redact_pii, redact_secrets
from app.core.config import settings
from app.core.crypto import decrypt, encrypt
from app.core.database import SessionLocal, get_db
from app.models.integration import Integration
from app.models.workspace import Workspace
from app.core.workspace_context import set_workspace_rls
from app.modules.guard.policy_engine import compute_policy, canonical_workspace_id as _canonical_workspace_id
from app.modules.guard.detectors.normalizer import normalize as _normalize_text
from app.modules.guard.circuit_breaker import get_breaker as _get_breaker
from app.runtime.pricing import get_model_rates


log = structlog.get_logger(__name__)
router = APIRouter(prefix="/proxy", tags=["guard-proxy"])
# Sibling router for non-proxy guard endpoints (e.g. local-audit-findings)
# so URLs stay semantic — `/guard/local-audit-findings`, not `/proxy/...`.
guard_router = APIRouter(prefix="/guard", tags=["guard"])


# Severity weights for the layered verdict envelope (#1150 phase 1).
# Linear scale — critical bumps score meaningfully vs low.
# Re-exported from app.guard.policy for existing callers (workflows.py, tests).
# Extracted in #1218 Step 1a — behavior identical, source of truth moved.
from app.guard.policy import (
    SEVERITY_WEIGHTS,
    _ACTION_RANK,
    _defense_score,
    _is_proxy_rule,
    _rule_matches,
    evaluate as _evaluate_policies,
    flatten_prompt as _flatten_prompt,
)

# Re-exported from app.guard.audit — #1218 Step 1b.
from app.guard.audit import (
    _compute_cost,
    _estimate_input_tokens,
    _extract_token_counts,
    record as _record_audit,
)

# Re-exported from app.guard.router — #1218 Step 1c.
from app.guard.router import (
    _safe_json,
    _stream_chunks,
    fail_closed as _fail_closed,
    upstream as _forward,
)


# Action restrictiveness for winner selection when multiple rules match.
# _ACTION_RANK now re-exported from app.guard.policy (see import block above).


VENDOR_DEFAULTS = {
    "anthropic": "https://api.anthropic.com",
    "openai":    "https://api.openai.com",
    "perplexity": "https://api.perplexity.ai",
}

MEMBER_TOKEN_PREFIX = "guard-mt-"   # legacy — kept for transition
AGENT_TOKEN_PREFIX  = "cond_agt_"  # new unified Agent ID token
API_TOKEN_PREFIX    = "cond_api_"  # long-lived machine token — no GMC link


def _workspace_proxy_url(db: Session, workspace_id: str) -> str:
    return settings.conduct_proxy_url


# ─── Local key audit ingest ───────────────────────────────────────────────

class _LocalFinding(BaseModel):
    provider: str
    path: str
    masked: str
    line: int | None = None


class _LocalAuditIn(BaseModel):
    user_email: str | None = None
    findings: list[_LocalFinding] = []


@guard_router.post("/local-audit-findings", include_in_schema=True)
async def ingest_local_audit(request: Request, body: _LocalAuditIn):
    """Receive pre-existing-key findings from `conduct guard sync`.

    One audit_event row per finding, source='local_audit', decision='WARN'.
    Auth: same member-token header used by the proxy routes.
    """
    raw = request.headers.get("x-api-key") or request.headers.get("authorization", "")
    if raw.lower().startswith("bearer "):
        raw = raw[7:].strip()
    if not raw:
        return _fail_closed(401, "Missing or malformed Conduct member token — run `conduct login`")

    db = SessionLocal()
    try:
        ident = resolve_agent_token(raw, db)
        if not ident:
            if token_is_expired(raw, db):
                return _fail_closed(401, "Conduct session expired — run `conduct login`")
            return _fail_closed(401, "Conduct member token not recognized — run `conduct login`")
        workspace_id, clerk_user_id = ident
        set_workspace_rls(db, workspace_id)

        # Replace this user's prior local_audit rows for the same paths
        # (so we don't grow N×N noise on every re-sync).
        paths = sorted({f.path for f in body.findings})
        if paths:
            db.execute(
                text("""
                    DELETE FROM guard_audit_events
                    WHERE workspace_id = :ws
                      AND source = 'local_audit'
                      AND clerk_user_id = :uid
                      AND input_summary = ANY(:paths)
                """),
                {"ws": workspace_id, "uid": clerk_user_id, "paths": paths},
            )

        now = datetime.now(timezone.utc)
        for f in body.findings:
            db.execute(
                text("""
                    INSERT INTO guard_audit_events (
                      workspace_id, clerk_user_id, ai_tool, tool_call,
                      source, provider, model,
                      decision, rule_id, rule_message, ts,
                      input_summary
                    ) VALUES (
                      :ws, :uid, :ai, NULL,
                      'local_audit', :prov, NULL,
                      'WARN', 'local_key_pre_existing',
                      :msg, :ts, :path
                    )
                """),
                {
                    "ws": workspace_id, "uid": clerk_user_id,
                    "ai": _tool_from_path(f.path),
                    "prov": f.provider,
                    "msg": f"Pre-existing {f.provider} key in {f.path}:{f.line} ({f.masked})",
                    "ts": now,
                    "path": f.path,
                },
            )
        db.commit()
        log.info("guard.proxy.local_audit_ingested",
                 workspace_id=workspace_id, count=len(body.findings))
        return {"received": len(body.findings)}
    finally:
        db.close()


def _tool_from_path(path: str) -> str:
    p = path.lower()
    if "claude" in p:    return "claude-code"
    if "cursor" in p:    return "cursor"
    if "codex" in p:     return "codex"
    if "aider" in p:     return "aider"
    return "shell" if any(s in p for s in ("zshrc", "bashrc", "profile")) else "unknown"


# ─── Anthropic ─────────────────────────────────────────────────────────────

@router.post("/anthropic/v1/messages")
async def proxy_anthropic(request: Request, background: BackgroundTasks):
    return await _proxy(
        request, background,
        provider="anthropic",
        upstream_path="/v1/messages",
        auth_header_in="x-api-key",
        auth_header_out="x-api-key",
    )


# ─── OpenAI ────────────────────────────────────────────────────────────────

@router.post("/openai/v1/chat/completions")
async def proxy_openai(request: Request, background: BackgroundTasks):
    return await _proxy(
        request, background,
        provider="openai",
        upstream_path="/v1/chat/completions",
        auth_header_in="authorization",
        auth_header_out="authorization",
        bearer=True,
    )


# ─── Perplexity (OpenAI-compatible) ────────────────────────────────────────

@router.post("/perplexity/chat/completions")
async def proxy_perplexity(request: Request, background: BackgroundTasks):
    return await _proxy(
        request, background,
        provider="perplexity",
        upstream_path="/chat/completions",
        auth_header_in="authorization",
        auth_header_out="authorization",
        bearer=True,
    )


# ─── Core proxy logic ──────────────────────────────────────────────────────

async def _proxy(
    request: Request,
    background: BackgroundTasks,
    *,
    provider: str,
    upstream_path: str,
    auth_header_in: str,
    auth_header_out: str,
    bearer: bool = False,
) -> StreamingResponse | JSONResponse:
    """One implementation, three providers — only the URL + auth header shape differs."""
    started = time.monotonic()

    # 1. Extract member token from whichever auth header the SDK sent
    raw = request.headers.get(auth_header_in, "")
    token = _extract_member_token(raw, bearer=bearer)

    # Internal server-to-server bypass (brain block / runtime calling its own proxy).
    # The runtime sends a per-run cond_run_* token OR the workspace's
    # cond_agt_* Agent Identity token via x-conductai-internal.
    _internal_key = request.headers.get("x-conductai-internal", "")
    _is_internal = False  # flips to True only after run/agent token validation
    _needs_run_token_validation = bool(_internal_key and _internal_key.startswith("cond_run_"))
    _needs_agent_validation = bool(_internal_key and _internal_key.startswith("cond_agt_"))
    _agent_identity_id: str | None = None

    if not token and not _is_internal and not _needs_agent_validation and not _needs_run_token_validation:
        return _fail_closed(401, "Missing or malformed Conduct member token — run `conduct login`")

    # 2. Resolve workspace + user
    db = SessionLocal()
    try:
        if _needs_run_token_validation and not _is_internal:
            import hashlib as _rt_hashlib
            from app.modules.agent_identity.run_token_model import AgentRunToken as _AgentRunToken
            from datetime import datetime, timezone
            _hdr_ws = request.headers.get("x-conductai-workspace-id", "")
            if not _hdr_ws:
                return _fail_closed(400, "X-Conductai-Workspace-Id required for run token calls")
            _token_hash = _rt_hashlib.sha256(_internal_key.encode()).hexdigest()
            _rt = db.query(_AgentRunToken).filter(
                _AgentRunToken.token_hash == _token_hash,
                _AgentRunToken.workspace_id == uuid.UUID(_hdr_ws),
                _AgentRunToken.invalidated_at == None,  # noqa: E711
            ).first()
            if not _rt:
                return _fail_closed(401, "Run token not found or already invalidated")
            _is_internal = True
            if not _rt.first_used_at:
                _rt.first_used_at = datetime.now(timezone.utc)
                db.commit()

        if _needs_agent_validation and not _is_internal:
            _hdr_ws = request.headers.get("x-conductai-workspace-id", "")
            if not _hdr_ws:
                return _fail_closed(400, "X-Conductai-Workspace-Id required for agent identity calls")
            from app.modules.agent_identity.models import AgentIdentity as _AgentIdentity
            from app.core.crypto import decrypt as _decrypt
            for _cand in db.query(_AgentIdentity).filter(_AgentIdentity.workspace_id == _hdr_ws).all():
                try:
                    if _decrypt(_cand.token_encrypted).get("token") == _internal_key:
                        from datetime import datetime, timezone as _tz
                        if _cand.expires_at and _cand.expires_at < datetime.now(_tz.utc):
                            return _fail_closed(401, "Agent Identity token expired — run `conduct guard sync` to refresh")
                        _is_internal = True
                        _agent_identity_id = _cand.id
                        break
                except Exception:
                    pass
            if not _is_internal:
                return _fail_closed(401, "Agent Identity token not recognized")

        if _is_internal:
            workspace_id = request.headers.get("x-conductai-workspace-id", "")
            if not workspace_id:
                return _fail_closed(400, "X-Conductai-Workspace-Id required for internal proxy calls")
            set_workspace_rls(db, workspace_id)
            _internal_email = request.headers.get("x-conductai-user-email") or None
            clerk_user_id = _internal_email or "system"
            if _agent_identity_id:
                from app.modules.agent_identity.models import AgentIdentity as _AgentIdentity
                from datetime import datetime, timezone as _tz
                _id_row = db.query(_AgentIdentity).filter(_AgentIdentity.id == _agent_identity_id).first()
                if _id_row:
                    _id_row.last_used_at = datetime.now(_tz.utc)
                    db.commit()
        else:
            ident = resolve_agent_token(token, db)
            if not ident:
                if token_is_expired(token, db):
                    return _fail_closed(401, "Conduct session expired — run `conduct login`")
                return _fail_closed(401, "Conduct member token not recognized — run `conduct login`")
            workspace_id, clerk_user_id = ident
            set_workspace_rls(db, workspace_id)

        # 3. Parse request body
        try:
            body = await request.json()
        except Exception:
            return _fail_closed(400, "Body must be valid JSON")

        model = body.get("model", "unknown")
        ai_tool = request.headers.get("x-conduct-ai-tool") or _infer_ai_tool(request)

        # 4a. Resolve user email for audit rows
        _user_email: str | None = None
        if not _user_email:
            try:
                from app.models.user import User as _User
                _u = db.query(_User).filter(_User.clerk_id == clerk_user_id).first()
                if _u:
                    _user_email = _u.email
            except Exception:
                pass

        # 4b. Run context from brain block headers (workflow runs only)
        _run_id = request.headers.get("x-conductai-run-id") or None
        _workflow = request.headers.get("x-conductai-workflow") or None
        _workflow_id = request.headers.get("x-conductai-workflow-id") or None
        _environment_id = request.headers.get("x-conductai-environment-id") or None
        _hook_session_id = request.headers.get("x-conduct-session-id") or None

        # 4c. Pre-call Guard policy evaluation
        prompt_summary = _flatten_prompt(body)[:200]
        decision = _evaluate_policies(workspace_id, provider, model, body)
        _action = decision["action"]  # "BLOCK" | "WARN" | "ALLOW"
        _guidance_text = decision.get("guidance") if decision.get("inject_guidance") else None

        if _action == "BLOCK":
            background.add_task(
                _record_audit, workspace_id, clerk_user_id, ai_tool, provider, model,
                "blocked", decision["rule_id"], int((time.monotonic() - started) * 1000),
                body=body, response_bytes=None,
                prompt_summary=prompt_summary, user_email=_user_email,
                conductai_run_id=_run_id, conductai_workflow=_workflow,
                conductai_workflow_id=_workflow_id, hook_session_id=_hook_session_id,
                evaluated_rules=decision.get("matched_rules"),
                defense_score=decision.get("defense_score"),
            )
            _err = {
                "type": "guard_block",
                "message": decision["message"],
                "rule": decision["rule_id"],
                "matched_rules": decision.get("matched_rules", []),
                "defense_score": decision.get("defense_score", 0),
            }
            if _guidance_text:
                _err["guidance"] = _guidance_text
            return JSONResponse(status_code=403, content={"error": _err})

        if _action == "APPROVAL":
            from app.modules.guard.models import GuardApprovalRequest as _GAR
            from app.modules.guard import approval as _approval
            _db2 = SessionLocal()
            try:
                # De-dupe: if this workspace + rule + requester already has a pending
                # request in the last 5 minutes, reuse it so a retrying agent does
                # not spam the inbox.
                from datetime import datetime as _dt, timedelta as _td, timezone as _tz
                cutoff = _dt.now(_tz.utc) - _td(minutes=5)
                existing = _db2.query(_GAR).filter(
                    _GAR.workspace_id == uuid.UUID(workspace_id),
                    _GAR.rule_id == decision["rule_id"],
                    _GAR.requester_user_id == (clerk_user_id or ""),
                    _GAR.status == "pending",
                    _GAR.created_at >= cutoff,
                ).first() if clerk_user_id else None
                if existing is None:
                    req = _approval.create_approval_request(
                        _db2,
                        workspace_id=workspace_id,
                        rule=decision.get("rule") or {"id": decision["rule_id"], "message": decision.get("message")},
                        tool_name=f"llm.{provider}",
                        tool_input={"model": model, "prompt": prompt_summary},
                        requester_email=_user_email,
                        requester_user_id=clerk_user_id,
                        surface="proxy",
                        session_id=_hook_session_id,
                        source_run_id=_run_id,
                    )
                    _approval.dispatch_approval_notifications(_db2, req)
                else:
                    req = existing
                background.add_task(
                    _record_audit, workspace_id, clerk_user_id, ai_tool, provider, model,
                    "approval_pending", decision["rule_id"], int((time.monotonic() - started) * 1000),
                    body=body, response_bytes=None,
                    prompt_summary=prompt_summary, user_email=_user_email,
                    conductai_run_id=_run_id, conductai_workflow=_workflow,
                    conductai_workflow_id=_workflow_id, hook_session_id=_hook_session_id,
                    evaluated_rules=decision.get("matched_rules"),
                    defense_score=decision.get("defense_score"),
                )
                _err = {
                    "type": "guard_approval_required",
                    "message": decision["message"] or "Human approval required by policy.",
                    "rule": decision["rule_id"],
                    "approval_request_id": str(req.id),
                    "approval_url": _approval.approval_url(req.id),
                    "pending_marker": _approval.pending_marker(req),
                    "matched_rules": decision.get("matched_rules", []),
                    "defense_score": decision.get("defense_score", 0),
                }
                return JSONResponse(status_code=428, content={"error": _err})
            finally:
                _db2.close()

        # Map internal action to audit decision string
        _audit_decision = "warned" if _action == "WARN" else "allowed"
        _audit_rule_id  = decision["rule_id"] if _action == "WARN" else None

        # 4d. Pre-forward budget check (#1083 — Loopers parity).
        # ponytail: SQL scan per call; swap to atomic Redis Lua counter when
        # throughput hurts (#822 tracks the upgrade).
        from app.modules.guard.routers.spend import budget_check as _budget_check
        _bc = _budget_check(workspace_id=workspace_id, clerk_user_id=clerk_user_id, db=db)
        if _bc.hard_blocked:
            background.add_task(
                _record_audit, workspace_id, clerk_user_id, ai_tool, provider, model,
                "budget_exceeded", None, int((time.monotonic() - started) * 1000),
                body=body, response_bytes=None,
                prompt_summary=prompt_summary, user_email=_user_email,
                conductai_run_id=_run_id, conductai_workflow=_workflow,
                conductai_workflow_id=_workflow_id, hook_session_id=_hook_session_id,
            )
            return JSONResponse(
                status_code=429,
                content={"error": {
                    "type": "guard_budget_exceeded",
                    "message": _bc.reason or "Monthly AI budget reached.",
                    "monthly_cost_usd": _bc.monthly_cost_usd,
                    "hard_limit_usd": _bc.hard_limit_usd,
                }},
            )

        # 4d.2. Per-key RPM/TPM rate limit (#980 — Loopers parity).
        from app.modules.guard.rate_limit import check_rate_limit as _check_rate_limit
        _rl = _check_rate_limit(
            db,
            workspace_id=workspace_id,
            agent_identity_id=str(_agent_identity_id) if _agent_identity_id else None,
            input_tokens=_estimate_input_tokens(body),
        )
        if _rl.limited:
            background.add_task(
                _record_audit, workspace_id, clerk_user_id, ai_tool, provider, model,
                "rate_limited", None, int((time.monotonic() - started) * 1000),
                body=body, response_bytes=None,
                prompt_summary=prompt_summary, user_email=_user_email,
                conductai_run_id=_run_id, conductai_workflow=_workflow,
                conductai_workflow_id=_workflow_id, hook_session_id=_hook_session_id,
            )
            return JSONResponse(
                status_code=429,
                content={"error": {
                    "type": "guard_rate_limited",
                    "message": _rl.reason,
                    "metric": _rl.metric,
                    "limit": _rl.limit,
                    "current": _rl.current,
                    "scope": _rl.scope,
                }},
            )

        # 5. Vault lookup — for BYO gateways: upstream_key authenticates with the gateway,
        # vault_key is the real vendor key the gateway forwards to Anthropic/OpenAI.
        upstream = _upstream_url(db, workspace_id, provider, _environment_id)
        _upstream_key = _upstream_api_key(db, workspace_id, _environment_id)
        _vault_key_val = _vault_key(db, workspace_id, provider, _environment_id)
        real_key = _upstream_key or _vault_key_val
        if not real_key:
            return _fail_closed(
                503,
                f"No API key configured — add {provider.upper()}_API_KEY in Settings → Environments, "
                f"or set LLM_UPSTREAM_API_KEY in Settings → Proxy.",
            )
    finally:
        db.close()

    # 5.5 Redact secrets from body before forwarding — runs after policy eval so
    # credential-leak rules still fire first and can block.
    body, _redacted = _redact_body(body)
    if _redacted:
        log.info("guard.proxy.redacted", types=_redacted, workspace_id=workspace_id)

    # 5.6 Inject guidance to model when rule has inject_guidance=true (#1141).
    # Fires for warn/audit/allow paths — block path is handled above via response body.
    if _guidance_text:
        body = _inject_guidance(body, _guidance_text, provider)
        log.info("guard.proxy.guidance_injected",
                 rule_id=decision.get("rule_id"), workspace_id=workspace_id)

    # 6. Forward + stream back. Use a fresh DB session inside the background task.
    is_stream = bool(body.get("stream"))
    # Pass through all vendor-specific headers the SDK sends (anthropic-beta,
    # openai-organization, openai-project, etc.) minus the ones we own.
    _skip = {auth_header_in, "host", "content-length", "transfer-encoding",
             "connection", "content-type", "accept", "user-agent"}
    extra_headers = {
        k.lower(): v for k, v in request.headers.items()
        if k.lower() not in _skip and not k.lower().startswith("x-conduct")
    }
    return await _forward(
        upstream=upstream,
        path=upstream_path,
        body=body,
        real_key=real_key,
        auth_header_out=auth_header_out,
        bearer=bearer,
        is_stream=is_stream,
        extra_headers=extra_headers,
        background=background,
        audit_args=(workspace_id, clerk_user_id, ai_tool, provider, model, _audit_decision, _audit_rule_id, started, body, prompt_summary, _user_email, _run_id, _workflow, _workflow_id, _hook_session_id),
        upstream_api_key=_upstream_key,
        vendor_key=_vault_key_val,
        provider=provider,
    )


# ─── Helpers ───────────────────────────────────────────────────────────────

def _extract_member_token(raw: str, *, bearer: bool) -> str | None:
    """Extract guard-mt- or cond_agt_ token from header value."""
    if not raw:
        return None
    if bearer:
        if not raw.lower().startswith("bearer "):
            return None
        raw = raw[7:].strip()
    if raw.startswith(MEMBER_TOKEN_PREFIX) or raw.startswith(AGENT_TOKEN_PREFIX) or raw.startswith(API_TOKEN_PREFIX):
        return raw
    return None



def _vault_key(db: Session, workspace_id: str, provider: str, environment_id: str | None = None) -> str | None:
    """Find the real vendor API key from env_vars for the workflow's environment."""
    env_var_name = {
        "anthropic":  "ANTHROPIC_API_KEY",
        "openai":     "OPENAI_API_KEY",
        "perplexity": "PERPLEXITY_API_KEY",
    }[provider]

    # Try environment-scoped env_vars first, then workspace-wide fallback
    candidates = []
    if environment_id:
        candidates.append({"ws": workspace_id, "env_id": environment_id})
    # workspace-wide fallback (environment_id IS NULL)
    candidates.append({"ws": workspace_id, "env_id": None})

    for params in candidates:
        env_filter = "AND environment_id = :env_id" if params["env_id"] else "AND environment_id IS NULL"
        rows = db.execute(
            text(f"""
                SELECT handle, encrypted_credentials
                FROM integrations
                WHERE workspace_id = :ws
                  AND handle IN (:provider, 'env_vars')
                  AND encrypted_credentials IS NOT NULL
                  {env_filter}
            """),
            {"ws": params["ws"], "provider": provider, "env_id": params["env_id"]},
        ).fetchall()
        for handle, enc in rows:
            try:
                creds = decrypt(enc) or {}
            except Exception:
                continue
            k = creds.get("api_key") if handle == provider else (creds.get(env_var_name) or creds.get(env_var_name.lower()))
            if k:
                return k
    return None


def _upstream_api_key(db: Session, workspace_id: str, environment_id: str | None = None) -> str | None:
    """Return LLM_UPSTREAM_API_KEY from proxy_config for the workflow's environment."""
    if not environment_id:
        return None
    from app.core.credentials import get_credential
    try:
        creds = get_credential(db, workspace_id, "proxy_config", environment_id)
        return creds.get("LLM_UPSTREAM_API_KEY") or None
    except Exception:
        pass
    return None


def _upstream_url(db: Session, workspace_id: str, provider: str, environment_id: str | None = None) -> str:
    """Return BYO upstream URL from proxy_config for the workflow's environment, else vendor default."""
    if environment_id:
        from app.core.credentials import get_credential
        try:
            creds = get_credential(db, workspace_id, "proxy_config", environment_id)
            override = creds.get("LLM_UPSTREAM")
            if override:
                return override.rstrip("/")
        except Exception:
            pass
    return VENDOR_DEFAULTS[provider]


def _redact_body(body: dict) -> tuple[dict, list[str]]:
    """Redact credentials from prompt body before forwarding to the LLM provider.

    Runs after policy evaluation so credential-leak rules still fire first.
    Returns a deep-copied body with secrets replaced by [REDACTED:label] and
    a list of secret type labels found.
    """
    import copy
    body = copy.deepcopy(body)
    found: list[str] = []

    def _clean(text: str) -> str:
        pii_scrubbed = redact_pii(text)
        if pii_scrubbed != text:
            found.append("pii")
        cleaned, secrets = redact_secrets(pii_scrubbed)
        found.extend(secrets)
        return cleaned

    if isinstance(body.get("system"), str):
        body["system"] = _clean(body["system"])

    for msg in body.get("messages") or []:
        content = msg.get("content")
        if isinstance(content, str):
            msg["content"] = _clean(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    block["text"] = _clean(block["text"])

    return body, found


def _prepend_system_content(existing, prefix: str):
    """Prepend `prefix` to a system-content value that is a string, a list of
    text blocks, or missing. Same shape in / same shape out."""
    if isinstance(existing, str):
        return f"{prefix}\n\n{existing}" if existing else prefix
    if isinstance(existing, list):
        return [{"type": "text", "text": prefix}, *existing]
    return prefix


def _inject_guidance(body: dict, guidance: str, provider: str) -> dict:
    """Prepend guidance to the system prompt of the outbound LLM body.

    Anthropic: body["system"] is a string OR list of {type:"text", text:...} blocks.
    OpenAI / Perplexity: prepend to messages[0].content when role=='system',
        else insert a new system message at index 0.

    Mutates and returns body. Non-inject_guidance callers should not invoke this.
    """
    if not guidance:
        return body
    prefix = f"[Guard guidance] {guidance.strip()}"

    if provider == "anthropic":
        body["system"] = _prepend_system_content(body.get("system"), prefix)
        return body

    # openai / perplexity — chat-completions shape
    messages = body.get("messages") or []
    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        messages[0]["content"] = _prepend_system_content(messages[0].get("content"), prefix)
    else:
        body["messages"] = [{"role": "system", "content": prefix}, *messages]
    return body



def _infer_ai_tool(request: Request) -> str:
    """Best-effort AI tool detection from User-Agent / referer when the client
    didn't send X-Conduct-AI-Tool. Helps the activity feed without forcing
    clients to opt in to the header."""
    ua = (request.headers.get("user-agent") or "").lower()
    for marker, name in (
        ("claude-code", "claude-code"),
        ("anthropic", "anthropic-sdk"),
        ("cursor", "cursor"),
        ("codex", "codex"),
        ("openai", "openai-sdk"),
    ):
        if marker in ua:
            return name
    return "unknown"



# ── Proxy config endpoints ────────────────────────────────────────────────────

class ProxyConfigBody(BaseModel):
    llm_upstream: str = ""
    llm_upstream_api_key: str = ""


@guard_router.get("/proxy-config")
def get_proxy_config(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    upstream = ""
    has_upstream_key = False
    from app.core.credentials import get_credential
    try:
        _pc_creds = get_credential(db, workspace_id, "proxy_config")
        upstream = _pc_creds.get("LLM_UPSTREAM", "")
        has_upstream_key = bool(_pc_creds.get("LLM_UPSTREAM_API_KEY"))
    except Exception:
        pass
    return {
        "conduct_proxy_url": _workspace_proxy_url(db, workspace_id),
        "llm_upstream": upstream,
        "has_upstream_key": has_upstream_key,
    }


@guard_router.put("/proxy-config")
def save_proxy_config(
    body: ProxyConfigBody,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    pc_row = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == "proxy_config",
        Integration.environment_id.is_(None),
    ).first()

    existing: dict = {}
    if pc_row:
        try:
            existing = decrypt(pc_row.encrypted_credentials) or {}
        except Exception:
            pass

    # Preserve existing upstream key if not supplied
    api_key = body.llm_upstream_api_key or existing.get("LLM_UPSTREAM_API_KEY", "")

    existing["LLM_UPSTREAM"] = body.llm_upstream
    if api_key:
        existing["LLM_UPSTREAM_API_KEY"] = api_key

    encrypted = encrypt(existing)

    if pc_row:
        pc_row.encrypted_credentials = encrypted
    else:
        db.add(Integration(
            workspace_id=workspace_id, service="proxy_config", handle="proxy_config",
            auth_method="api_key", encrypted_credentials=encrypted,
            environment_id=None,
        ))

    db.commit()
    return {"saved": True}


class ProxyConfigPushBody(BaseModel):
    environment_id: str


@guard_router.post("/proxy-config/push")
def push_proxy_config(
    body: ProxyConfigPushBody,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    if not body.environment_id:
        raise HTTPException(status_code=422, detail="environment_id is required")

    # Read workspace-level proxy config
    pc_row = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == "proxy_config",
        Integration.environment_id.is_(None),
    ).first()
    if not pc_row:
        raise HTTPException(status_code=404, detail="No proxy config saved yet")

    try:
        pc_creds = decrypt(pc_row.encrypted_credentials) or {}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read proxy config")

    upstream = pc_creds.get("LLM_UPSTREAM", "")
    upstream_key = pc_creds.get("LLM_UPSTREAM_API_KEY", "")

    # Merge into target environment's env_vars (preserve other keys)
    ev_row = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == "env_vars",
        Integration.environment_id == body.environment_id,
    ).first()

    ev_creds: dict = {}
    if ev_row:
        try:
            ev_creds = decrypt(ev_row.encrypted_credentials) or {}
        except Exception:
            pass

    ev_creds["PROXY_CONFIG_LLM_UPSTREAM"] = upstream
    if upstream_key:
        ev_creds["PROXY_CONFIG_LLM_UPSTREAM_API_KEY"] = upstream_key

    encrypted = encrypt(ev_creds)
    if ev_row:
        ev_row.encrypted_credentials = encrypted
    else:
        db.add(Integration(
            workspace_id=workspace_id, service="env_vars", handle="env_vars",
            auth_method="api_key", encrypted_credentials=encrypted,
            environment_id=body.environment_id,
        ))
    db.commit()
    return {"pushed": True}
