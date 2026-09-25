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
from fastapi.responses import JSONResponse, Response, StreamingResponse
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
from app.runtime.provider_transport import get_provider_transport_registry


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

# Re-exported from app.guard.audit — #1218 Step 1b. #2209 Tier 1
# removed the legacy compat shims; proxy only needed ``record`` anyway.
from app.guard.audit import record as _record_audit

# Re-exported from app.guard.router — #1218 Step 1c.
from app.guard.router import (
    _safe_json,
    _stream_chunks,
    fail_closed as _fail_closed,
    upstream as _forward,
)


# Action restrictiveness for winner selection when multiple rules match.
# _ACTION_RANK now re-exported from app.guard.policy (see import block above).


# Constants + helpers live in ../gateway_helpers.py (extracted 2026-09-17).
# Re-imported here so this legacy router's own decorators keep working; new
# callers should import from gateway_helpers directly, not from this module.
from app.modules.guard.gateway_helpers import (  # noqa: E402
    VENDOR_DEFAULTS,
    MEMBER_TOKEN_PREFIX,
    AGENT_TOKEN_PREFIX,
    API_TOKEN_PREFIX,
    _TIER_FORMS,
    _resolve_tier_form,
    _apply_tier_resolution,
    _evaluate_response_body,
    _apply_response_gate,
    _extract_stream_text,
    _wrap_streaming_response,
    _extract_member_token,
    _vault_key,
    _upstream_api_key,
    _upstream_url,
    _redact_body,
    _prepend_system_content,
    _inject_guidance,
    _infer_ai_tool,
)


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


# ─── Core proxy logic (moved) ─────────────────────────────────────────────

# Real orchestrator lives in app.modules.guard.gateway_handler.handle_gateway_request.
# The alias below preserves the historical private name for the three route
# decorators above (proxy_anthropic/openai/perplexity). New Gateway behavior
# is added in gateway_handler.py, never here.
from app.modules.guard.gateway_handler import handle_gateway_request as _proxy  # noqa: E402

# ─── Helpers ───────────────────────────────────────────────────────────────

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

    if pc_row:
        # Atomic read-merge-write. The "preserve existing api_key" fallback
        # stays inside the merge lambda so a retry re-reads the newest
        # ciphertext instead of racing on the one we loaded first.
        from app.core.integration_writer import merge_and_write

        def _merge_proxy_config(prev: dict) -> dict:
            api_key_now = body.llm_upstream_api_key or prev.get("LLM_UPSTREAM_API_KEY", "")
            prev["LLM_UPSTREAM"] = body.llm_upstream
            if api_key_now:
                prev["LLM_UPSTREAM_API_KEY"] = api_key_now
            return prev

        merge_and_write(db, pc_row.id, _merge_proxy_config)
    else:
        seed: dict = {"LLM_UPSTREAM": body.llm_upstream}
        if body.llm_upstream_api_key:
            seed["LLM_UPSTREAM_API_KEY"] = body.llm_upstream_api_key
        encrypted = encrypt(seed)
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

    if ev_row:
        from app.core.integration_writer import merge_and_write

        def _merge_env_vars(prev: dict) -> dict:
            prev["PROXY_CONFIG_LLM_UPSTREAM"] = upstream
            if upstream_key:
                prev["PROXY_CONFIG_LLM_UPSTREAM_API_KEY"] = upstream_key
            return prev

        merge_and_write(db, ev_row.id, _merge_env_vars)
    else:
        seed: dict = {"PROXY_CONFIG_LLM_UPSTREAM": upstream}
        if upstream_key:
            seed["PROXY_CONFIG_LLM_UPSTREAM_API_KEY"] = upstream_key
        encrypted = encrypt(seed)
        db.add(Integration(
            workspace_id=workspace_id, service="env_vars", handle="env_vars",
            auth_method="api_key", encrypted_credentials=encrypted,
            environment_id=body.environment_id,
        ))
    db.commit()
    return {"pushed": True}
