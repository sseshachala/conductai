"""Gateway request-path helpers extracted from routers/proxy.py so
``gateway_handler`` — and any future caller — can depend on them without
importing from the legacy proxy router module.

Retirement plan: routers/proxy.py imports these back for its own (legacy)
route decorators. Once the proxy route surface is removed, this module is
the sole home for these helpers.
"""
from __future__ import annotations

import asyncio
import copy
import json
import re
from dataclasses import dataclass

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.pii import redact_pii, redact_secrets
from app.core.crypto import decrypt


@dataclass
class GatewayAuth:
    """Resolved auth for a gateway request. Extracted from
    ``handle_gateway_request`` so admission can wrap the whole post-auth
    body cleanly."""
    workspace_id: str
    clerk_user_id: str
    is_internal: bool
    agent_identity_id: str | None = None
    agent_risk_tier: str | None = None
    token: str = ""


def _resolve_gateway_auth(
    request: Request,
    *,
    token: str | None,
    internal_key: str,
    needs_run_token_validation: bool,
    needs_agent_validation: bool,
) -> "GatewayAuth | JSONResponse":
    """Resolves auth for a gateway request. Owns its own DB session — opens
    at entry, closes in a finally regardless of exit path. Callers invoke
    via ``run_in_threadpool`` so the event loop is not blocked during
    the sync SQLAlchemy work.

    Returns ``GatewayAuth`` on success. Returns a ``JSONResponse`` when
    auth fails (401/400).
    """
    from app.core.database import SessionLocal as _SessionLocal
    db = _SessionLocal()
    try:
        return _resolve_gateway_auth_inner(
            request, db,
            token=token,
            internal_key=internal_key,
            needs_run_token_validation=needs_run_token_validation,
            needs_agent_validation=needs_agent_validation,
        )
    finally:
        db.close()


def _resolve_gateway_auth_inner(
    request: Request,
    db: Session,
    *,
    token: str | None,
    internal_key: str,
    needs_run_token_validation: bool,
    needs_agent_validation: bool,
) -> "GatewayAuth | JSONResponse":
    """Auth resolution implementation. Uses caller-provided db. Kept as a
    separate function so the session-owning wrapper stays a thin
    open/close shell."""
    import hashlib as _hashlib
    import uuid as _uuid
    from datetime import datetime as _dt, timezone as _tz

    from app.core.auth import (
        resolve_agent_token,
        token_is_expired,
        _resolve_agent_token as _resolve_ai,
        resolve_agent_identity_row as _rair,
    )
    from app.core.workspace_context import set_workspace_rls
    from app.guard.router import fail_closed as _fail_closed
    from app.modules.agent_identity.models import AgentIdentity as _AgentIdentity
    from app.modules.agent_identity.run_token_model import AgentRunToken as _AgentRunToken
    from fastapi import HTTPException as _HTTPException

    is_internal = False
    agent_identity_id: str | None = None
    agent_risk_tier: str | None = None
    workspace_id = ""
    clerk_user_id = ""

    if needs_run_token_validation:
        _hdr_ws = request.headers.get("x-conductai-workspace-id", "")
        if not _hdr_ws:
            return _fail_closed(400, "X-Conductai-Workspace-Id required for run token calls")
        _token_hash = _hashlib.sha256(internal_key.encode()).hexdigest()
        _now_rt = _dt.now(_tz.utc)
        _rt = db.query(_AgentRunToken).filter(
            _AgentRunToken.token_hash == _token_hash,
            _AgentRunToken.workspace_id == _uuid.UUID(_hdr_ws),
            _AgentRunToken.invalidated_at == None,  # noqa: E711
            _AgentRunToken.expires_at > _now_rt,
        ).first()
        if not _rt:
            return _fail_closed(401, "Run token not found, expired, or already invalidated")
        is_internal = True
        if not _rt.first_used_at:
            _rt.first_used_at = _now_rt
            db.commit()

    if needs_agent_validation and not is_internal:
        _hdr_ws = request.headers.get("x-conductai-workspace-id", "")
        if not _hdr_ws:
            return _fail_closed(400, "X-Conductai-Workspace-Id required for agent identity calls")
        try:
            _ai, _ = _resolve_ai(internal_key, db)
        except _HTTPException as _exc:
            return _fail_closed(int(_exc.status_code), str(_exc.detail or "Agent Identity token not recognized"))
        if str(_ai.workspace_id) != _hdr_ws:
            return _fail_closed(401, "Agent Identity token does not belong to the requested workspace")
        is_internal = True
        agent_identity_id = _ai.id
        agent_risk_tier = getattr(_ai, "risk_tier", None)

    if is_internal:
        workspace_id = request.headers.get("x-conductai-workspace-id", "")
        if not workspace_id:
            return _fail_closed(400, "X-Conductai-Workspace-Id required for internal proxy calls")
        set_workspace_rls(db, workspace_id)
        _internal_email = request.headers.get("x-conductai-user-email") or None
        clerk_user_id = _internal_email or "system"
        if agent_identity_id:
            _id_row = db.query(_AgentIdentity).filter(_AgentIdentity.id == agent_identity_id).first()
            if _id_row:
                _id_row.last_used_at = _dt.now(_tz.utc)
                db.commit()
    else:
        ident = resolve_agent_token(token, db)
        if not ident:
            if token_is_expired(token, db):
                return _fail_closed(401, "Conduct session expired — run `conduct login`")
            return _fail_closed(401, "Conduct member token not recognized — run `conduct login`")
        workspace_id, clerk_user_id = ident
        set_workspace_rls(db, workspace_id)
        try:
            _proxy_ai_row = _rair(token, db)
            if _proxy_ai_row:
                agent_risk_tier = getattr(_proxy_ai_row, "risk_tier", None)
                agent_identity_id = getattr(_proxy_ai_row, "id", None) or agent_identity_id
        except Exception:
            pass

    return GatewayAuth(
        workspace_id=workspace_id,
        clerk_user_id=clerk_user_id,
        is_internal=is_internal,
        agent_identity_id=agent_identity_id,
        agent_risk_tier=agent_risk_tier,
        token=token or "",
    )

log = structlog.get_logger()

# ── Constants ────────────────────────────────────────────────────────────────

VENDOR_DEFAULTS = {
    "anthropic": "https://api.anthropic.com",
    "openai":    "https://api.openai.com",
    "perplexity": "https://api.perplexity.ai",
}

MEMBER_TOKEN_PREFIX = "guard-mt-"   # legacy — kept for transition
AGENT_TOKEN_PREFIX  = "cond_agt_"  # new unified Agent ID token
API_TOKEN_PREFIX    = "cond_api_"  # long-lived machine token — no GMC link

# Callers may send `"balanced"` or `"openai/cheap"` instead of a concrete model
# ID. Gateway resolves via workspace primitives before the request hits Guard
# policy or upstream. Non-tier strings pass through unchanged.
_TIER_FORMS = {"cheap", "balanced", "smart", "quality", "speed", "cost", "auto"}

# ── Module state ─────────────────────────────────────────────────────────────

_STREAM_TEXT_RE: re.Pattern[str] | None = None  # lazy compiled

# ── Tier resolution ──────────────────────────────────────────────────────────

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

# ── Response-gate evaluation (shared by non-streaming and streaming paths) ──

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
        text_str = collected.decode("utf-8", errors="replace")
    except Exception:
        return ""
    parts: list[str] = []
    for line in text_str.splitlines():
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
        for m in _STREAM_TEXT_RE.findall(text_str)
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
    on_close=None,
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
        try:
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
                text_str = _extract_stream_text(bytes(collected))
                if not text_str:
                    return
                synthetic = {"content": [{"type": "text", "text": text_str}]}
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
        finally:
            # Idempotent lifecycle hook — fires on stream completion, client
            # disconnect, or upstream error. Callers pass an admission-slot
            # release (or any other cleanup) here so it always runs, not only
            # on graceful ``StreamingResponse.background``.
            if on_close is not None:
                try:
                    if asyncio.iscoroutinefunction(on_close):
                        await on_close()
                    else:
                        on_close()
                except Exception as _e:
                    log.warning("guard.proxy.stream_on_close_failed", err=str(_e))

    return StreamingResponse(
        _wrapped(),
        media_type=response.media_type,
        headers=dict(response.headers),
        status_code=response.status_code,
    )

# ── Auth / token extraction ──────────────────────────────────────────────────

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

# ── Vault / upstream key + URL resolution ────────────────────────────────────

def _vault_key(db: Session, workspace_id: str, provider: str, environment_id: str | None = None) -> str | None:
    """Find the real vendor API key from env_vars for the workflow's environment."""
    env_var_name = {
        "anthropic":  "ANTHROPIC_API_KEY",
        "openai":     "OPENAI_API_KEY",
        "perplexity": "PERPLEXITY_API_KEY",
    }[provider]

    candidates = []
    if environment_id:
        candidates.append({"ws": workspace_id, "env_id": environment_id})
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


def _resolve_upstream_credentials(
    workspace_id: str,
    provider: str,
    environment_id: str | None,
) -> tuple[str, str | None, str | None]:
    """Combined upstream URL + API key + vault key resolution in one bounded
    session. Called via ``run_in_threadpool`` from the gateway hot path so
    three sequential DB round-trips run off the event loop.

    Returns ``(upstream_url, upstream_api_key, vault_key)``.
    """
    from app.core.database import SessionLocal as _SessionLocal
    from app.core.workspace_context import set_workspace_rls
    db = _SessionLocal()
    try:
        set_workspace_rls(db, workspace_id)
        upstream = _upstream_url(db, workspace_id, provider, environment_id)
        api_key = _upstream_api_key(db, workspace_id, environment_id)
        vault = _vault_key(db, workspace_id, provider, environment_id)
        return upstream, api_key, vault
    finally:
        db.close()


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

# ── Body redaction + guidance injection ──────────────────────────────────────

def _redact_body(body: dict) -> tuple[dict, list[str]]:
    """Redact credentials from prompt body before forwarding to the LLM provider.

    Runs after policy evaluation so credential-leak rules still fire first.
    Returns a deep-copied body with secrets replaced by [REDACTED:label] and
    a list of secret type labels found.
    """
    body = copy.deepcopy(body)
    found: list[str] = []

    def _clean(text_val: str) -> str:
        pii_scrubbed = redact_pii(text_val)
        if pii_scrubbed != text_val:
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

    messages = body.get("messages") or []
    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        messages[0]["content"] = _prepend_system_content(messages[0].get("content"), prefix)
    else:
        body["messages"] = [{"role": "system", "content": prefix}, *messages]
    return body

# ── ai_tool inference from request headers ───────────────────────────────────

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
