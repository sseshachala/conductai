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


# ── Tier-form model strings (PR B.5 of #1347) ─────────────────────────────────
# Callers may send `"balanced"` or `"openai/cheap"` instead of a concrete model
# ID. Proxy resolves via workspace primitives before the request hits Guard
# policy or upstream. Non-tier strings pass through unchanged (backward compat).
_TIER_FORMS = {"cheap", "balanced", "smart", "quality", "speed", "cost", "auto"}


def _apply_tier_resolution(
    db: Session,
    workspace_id: str,
    endpoint_provider: str,
    body: dict,
) -> tuple[str, dict | None]:
    """Rewrite body["model"] if it is a tier form. Returns (effective_model, routing_meta).

    routing_meta is a dict populated only when a substitution occurred, ready
    to persist into guard_audit_events.routing_meta. When None, model was
    already concrete and body is unchanged."""
    original = body.get("model", "unknown")
    result = _resolve_tier_form(db, workspace_id, endpoint_provider, original)
    if not result:
        return original, None
    resolved, reason = result
    body["model"] = resolved
    meta = {
        "tier_form": original if isinstance(original, str) else None,
        "resolved_model": resolved,
        "endpoint_provider": endpoint_provider,
        "reason": reason,
        "resolution_source": "workspace_primitives",
    }
    return resolved, meta


def _resolve_tier_form(db: Session, workspace_id: str, endpoint_provider: str, model_field: object) -> tuple[str, str] | None:
    """If model_field is a tier name (bare or `<endpoint_provider>/<tier>`),
    resolve via workspace primitives and return the concrete model ID.
    Return None if it is already a concrete model (pass-through).

    Cross-provider forms (e.g. `"anthropic/balanced"` sent to /openai) are
    ignored — the endpoint provider is authoritative."""
    if not isinstance(model_field, str) or not model_field.strip():
        return None
    m = model_field.strip().lower()
    if m in _TIER_FORMS:
        tier = m
    elif "/" in m:
        prefix, _, tail = m.partition("/")
        if prefix != endpoint_provider or tail not in _TIER_FORMS:
            return None
        tier = tail
    else:
        return None
    try:
        from app.runtime.model_router import resolve_for_workspace
        _, resolved, reason = resolve_for_workspace(
            db=db,
            workspace_id=workspace_id,
            routing_preference=tier,
            explicit_provider=endpoint_provider,
        )
        return (resolved, reason)
    except Exception:
        return None


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

def _evaluate_response_body(
    resp_body: dict,
    *,
    workspace_id: str,
    provider: str,
    model: str,
    clerk_user_id: str | None,
    agent_identity_id: str | None,
    agent_risk_tier: str | None = None,
    ai_tool: str | None = None,
):
    """#1733 PRs 4+5 — shared response-gate evaluator. Called by both the
    non-streaming path (post-upstream, pre-return) and the streaming path
    (end-of-stream, post-yield). Returns a ``PolicyDecision`` or ``None`` on
    engine error. Never raises."""
    try:
        from app.guard.policy import evaluate_composed as _eval_composed
        from app.guard.policy_types import PolicyContext as _PC

        _ctx = _PC(
            workspace_id=workspace_id,
            clerk_user_id=clerk_user_id or None,
            agent_identity_id=str(agent_identity_id) if agent_identity_id else None,
            provider=provider,
            model=model,
            body=resp_body,
            input_tokens=0,
            db=None,
            gate="response",  # #1733: inbound model reply
            risk_tier=agent_risk_tier,
            # Same ai_tool the outbound prompt gate was evaluated against.
            ai_tool=ai_tool,
        )
        return _eval_composed(_ctx)
    except Exception as _e:
        log.warning("guard.proxy.response_gate_error", err=str(_e))
        return None


def _apply_response_gate(
    response: JSONResponse,
    *,
    workspace_id: str,
    provider: str,
    model: str,
    clerk_user_id: str | None,
    agent_identity_id: str | None,
    agent_risk_tier: str | None = None,
    ai_tool: str | None = None,
) -> JSONResponse:
    """#1733 PR 4 — evaluate the response body against gate='response' rules.

    If a response-gate rule fires BLOCK, replace the upstream body with a
    Guard-blocked envelope; otherwise return the original response.

    Never raises — response-gate failures log at WARN and pass the response
    through, so the response path never breaks on a policy engine hiccup.
    """
    try:
        import json as _json
        from app.guard.policy_types import PolicyAction as _PA

        resp_body = _json.loads(response.body or b"{}")
        decision = _evaluate_response_body(
            resp_body,
            workspace_id=workspace_id, provider=provider, model=model,
            clerk_user_id=clerk_user_id, agent_identity_id=agent_identity_id,
            agent_risk_tier=agent_risk_tier,
            ai_tool=ai_tool,
        )
        if decision is None or decision.action != _PA.BLOCK:
            return response
        log.warning(
            "guard.proxy.response_blocked",
            workspace_id=workspace_id, provider=provider, model=model,
            rule_id=decision.rule_id, reason=decision.reason,
        )
        return JSONResponse(
            status_code=451,
            content={
                "error": {
                    "type": "conduct_guard_response_block",
                    "message": decision.reason or "Response blocked by ConductGuard response-gate policy.",
                    "rule_id": decision.rule_id,
                    "gate": "response",
                }
            },
        )
    except Exception as _e:
        log.warning("guard.proxy.response_gate_error", err=str(_e))
        return response


_STREAM_TEXT_RE = None  # lazy compiled — see _extract_stream_text below


def _extract_stream_text(collected: bytes) -> str:
    """Best-effort text extraction from an SSE-formatted upstream stream.

    Matches ``"text":"..."`` (Anthropic ``content_block_delta``/``text_delta``)
    and ``"content":"..."`` (OpenAI streaming ``choices[].delta.content``) via
    a single regex. Handles escaped quotes and backslashes.

    ponytail: full-body regex sweep, not an SSE-aware parser. Upgrade path is
    a proper event-frame decoder if false positives (e.g. matching input
    echoes in trace metadata) become a real signal. Chunk-scan (per-chunk
    eval with mid-stream halt) is the true long-term shape.
    """
    global _STREAM_TEXT_RE
    import re as _re

    if _STREAM_TEXT_RE is None:
        _STREAM_TEXT_RE = _re.compile(r'"(?:text|content)":\s*"((?:[^"\\]|\\.)*)"')
    try:
        text = collected.decode("utf-8", errors="replace")
    except Exception:
        return ""
    parts: list[str] = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        try:
            event = json.loads(line[6:])
        except Exception:
            continue
        if event.get("type") == "response.output_text.delta" and isinstance(event.get("delta"), str):
            parts.append(event["delta"])
    parts.extend([
        m.encode("utf-8").decode("unicode_escape", errors="replace")
        for m in _STREAM_TEXT_RE.findall(text)
    ])
    return "\n".join(parts)


def _wrap_streaming_response(
    response: StreamingResponse,
    *,
    workspace_id: str,
    provider: str,
    model: str,
    clerk_user_id: str | None,
    agent_identity_id: str | None,
    agent_risk_tier: str | None = None,
    ai_tool: str | None = None,
) -> StreamingResponse:
    """#1733 PR 5 — buffered end-of-stream response gate.

    Wraps the upstream StreamingResponse: yields each chunk to the client
    unchanged, accumulates the full body in memory, then at end-of-stream
    evaluates gate='response' rules and logs a WARN if any rule fires BLOCK.

    ponytail: buffered scan. Client has already received the offending
    tokens by the time we decide — we only get telemetry + audit-trail
    coverage. Upgrade path: chunk-scan (per-chunk eval + mid-stream halt)
    so a live rule fire terminates the stream before further leak.
    """
    original_iterator = response.body_iterator

    async def _wrapped():
        collected = bytearray()
        async for chunk in original_iterator:
            if isinstance(chunk, str):
                chunk_bytes = chunk.encode("utf-8")
            else:
                chunk_bytes = chunk
            collected.extend(chunk_bytes)
            yield chunk_bytes
        # End-of-stream response-gate scan. Wrapped in a broad try/except
        # so a downstream failure NEVER truncates the stream after yield.
        try:
            text = _extract_stream_text(bytes(collected))
            if not text:
                return
            synthetic = {"content": [{"type": "text", "text": text}]}
            decision = _evaluate_response_body(
                synthetic,
                workspace_id=workspace_id, provider=provider, model=model,
                clerk_user_id=clerk_user_id, agent_identity_id=agent_identity_id,
                agent_risk_tier=agent_risk_tier,
                ai_tool=ai_tool,
            )
            if decision is None:
                return
            from app.guard.policy_types import PolicyAction as _PA
            if decision.action == _PA.BLOCK:
                log.warning(
                    "guard.proxy.response_stream_blocked_post_hoc",
                    workspace_id=workspace_id, provider=provider, model=model,
                    rule_id=decision.rule_id, reason=decision.reason,
                    note="ponytail: buffered scan — client saw response; upgrade to chunk-scan",
                )
        except Exception as _e:
            log.warning("guard.proxy.response_stream_gate_error", err=str(_e))

    return StreamingResponse(
        _wrapped(),
        media_type=response.media_type,
        headers=dict(response.headers),
        status_code=response.status_code,
    )


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
    if isinstance(body.get("instructions"), str):
        body["instructions"] = _clean(body["instructions"])

    for msg in body.get("messages") or []:
        content = msg.get("content")
        if isinstance(content, str):
            msg["content"] = _clean(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    block["text"] = _clean(block["text"])

    response_input = body.get("input")
    if isinstance(response_input, str):
        body["input"] = _clean(response_input)
    elif isinstance(response_input, list):
        for item in response_input:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, str):
                item["content"] = _clean(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        part["text"] = _clean(part["text"])

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
