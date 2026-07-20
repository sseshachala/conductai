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

from app.core.auth import get_workspace_id, require_permission, resolve_agent_token
from app.core.pii import redact_secrets
from app.core.config import settings
from app.core.crypto import decrypt, encrypt
from app.core.database import SessionLocal, get_db
from app.models.integration import Integration
from app.models.workspace import Workspace
from app.core.workspace_context import set_workspace_rls
from app.modules.guard.policy_engine import compute_policy, canonical_workspace_id as _canonical_workspace_id
from app.runtime.pricing import get_model_rates


log = structlog.get_logger(__name__)
router = APIRouter(prefix="/proxy", tags=["guard-proxy"])
# Sibling router for non-proxy guard endpoints (e.g. local-audit-findings)
# so URLs stay semantic — `/guard/local-audit-findings`, not `/proxy/...`.
guard_router = APIRouter(prefix="/guard", tags=["guard"])


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
        return _fail_closed(401, "Missing or malformed Conduct member token — run `conduct guard sync` to refresh")

    db = SessionLocal()
    try:
        ident = resolve_agent_token(raw, db)
        if not ident:
            return _fail_closed(401, "Conduct member token not recognized — run `conduct guard sync` to refresh")
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
    # Accepts either CLI_API_KEY (legacy) or a cond_agt_ Agent Identity token.
    _internal_key = request.headers.get("x-conductai-internal", "")
    _is_internal = bool(
        _internal_key
        and settings.cli_api_key
        and _internal_key == settings.cli_api_key
    )
    # ponytail: flag only — DB validation deferred into main db block (one session, not two)
    _needs_run_token_validation = bool(_internal_key and not _is_internal and _internal_key.startswith("cond_run_"))
    _needs_agent_validation = bool(_internal_key and not _is_internal and _internal_key.startswith("cond_agt_"))
    _agent_identity_id: str | None = None

    if not token and not _is_internal and not _needs_agent_validation and not _needs_run_token_validation:
        return _fail_closed(401, "Missing or malformed Conduct member token — run `conduct guard sync` to refresh")

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
                return _fail_closed(401, "Conduct member token not recognized — run `conduct guard sync` to refresh")
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
        if _action == "BLOCK":
            background.add_task(
                _record_audit, workspace_id, clerk_user_id, ai_tool, provider, model,
                "blocked", decision["rule_id"], int((time.monotonic() - started) * 1000),
                body=body, response_bytes=None,
                prompt_summary=prompt_summary, user_email=_user_email,
                conductai_run_id=_run_id, conductai_workflow=_workflow,
                conductai_workflow_id=_workflow_id, hook_session_id=_hook_session_id,
            )
            return JSONResponse(status_code=403, content={
                "error": {"type": "guard_block", "message": decision["message"], "rule": decision["rule_id"]},
            })

        # Map internal action to audit decision string
        _audit_decision = "warned" if _action == "WARN" else "allowed"
        _audit_rule_id  = decision["rule_id"] if _action == "WARN" else None

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


def _evaluate_policies(workspace_id: str, provider: str, model: str, body: dict) -> dict:
    """Pre-call Guard policy evaluation.

    Loads the workspace's compiled policy snapshot (from skill_packs via the
    existing engine) and applies any rule with proxy-applicable matchers:

      match_provider  exact string ('anthropic' | 'openai' | 'perplexity')
      match_model     regex against the model id
      match_prompt    regex against concatenated user messages

    First match wins; action is mapped to BLOCK / WARN / ALLOW. Rules written
    for hook events (match_tool + match_pattern) are silently skipped here —
    they don't apply to raw LLM calls.

    Fail-open on engine errors: returns ALLOW with rule_id='guard.engine_error'
    so the call still goes through and we don't lock customers out of LLMs if
    our cache is busted. The error is logged.
    """
    db = SessionLocal()
    try:
        policy_ws_id = _canonical_workspace_id(workspace_id)

        set_workspace_rls(db, policy_ws_id)
        try:
            rules = compute_policy(db, uuid.UUID(policy_ws_id), "proxy")
        except Exception as e:
            log.warning("guard.proxy.policy_load_failed", err=str(e))
            from app.modules.guard.models import GuardConfig as _GuardConfig
            cfg = db.query(_GuardConfig).filter(_GuardConfig.workspace_id == uuid.UUID(policy_ws_id)).first()
            deny = cfg.deny_on_error if cfg else True
            if deny:
                return {"action": "BLOCK", "rule_id": "guard.engine_error", "message": "Policy engine error — request blocked (fail-closed). Check Guard settings to change this behavior."}
            return {"action": "ALLOW", "rule_id": "guard.engine_error", "message": None}

        prompt_text = _flatten_prompt(body)
        for r in rules:
            if not _is_proxy_rule(r):
                continue
            if not _rule_matches(r, provider, model, prompt_text):
                continue
            action = (r.get("action") or "warn").upper()
            return {
                "action": "BLOCK" if action == "BLOCK" else ("WARN" if action == "WARN" else "ALLOW"),
                "rule_id": r.get("rule_id") or r.get("id"),
                "message": r.get("message") or r.get("description"),
            }
        return {"action": "ALLOW", "rule_id": None, "message": None}
    finally:
        db.close()


def _is_proxy_rule(rule: dict) -> bool:
    """True if the rule has at least one proxy-applicable matcher.
    match_pattern is proxy-applicable only when match_tool is absent
    (rules with match_tool are hook-event rules, not LLM-call rules)."""
    if any(k in rule for k in ("match_provider", "match_model", "match_prompt")):
        return True
    return "match_pattern" in rule and "match_tool" not in rule


def _rule_matches(rule: dict, provider: str, model: str, prompt_text: str) -> bool:
    p = rule.get("match_provider")
    if p is not None and p != provider:
        return False
    m = rule.get("match_model")
    if m and not re.search(m, model or "", re.IGNORECASE):
        return False
    pp = rule.get("match_prompt")
    if pp and not re.search(pp, prompt_text, re.IGNORECASE):
        return False
    pat = rule.get("match_pattern")
    if pat and not re.search(pat, prompt_text, re.IGNORECASE):
        return False
    return True


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
        cleaned, secrets = redact_secrets(text)
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


def _flatten_prompt(body: dict) -> str:
    """Best-effort: join all user message contents for prompt-pattern matching.

    Anthropic + OpenAI share the messages[].content shape; content can be a
    string or a list of typed parts. Non-text parts are skipped.
    """
    out: list[str] = []
    for msg in body.get("messages") or []:
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            out.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") in (None, "text", "input_text"):
                    text = part.get("text")
                    if text:
                        out.append(text)
    return "\n".join(out)


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


async def _forward(
    *, upstream: str, path: str, body: dict, real_key: str,
    auth_header_out: str, bearer: bool, is_stream: bool,
    background: BackgroundTasks, audit_args: tuple,
    extra_headers: dict | None = None,
    upstream_api_key: str | None = None,
    vendor_key: str | None = None,
    provider: str = "",
) -> StreamingResponse | JSONResponse:
    headers = {
        "content-type": "application/json",
        "accept": "text/event-stream" if is_stream else "application/json",
    }

    # When routing through a BYO gateway, use gateway-specific auth headers.
    # gateway_adapt returns non-empty headers for known gateways (Portkey, Helicone, Azure).
    if upstream_api_key:
        from app.runtime.adapters.gateway import gateway_adapt as _gw_adapt
        _gw = _gw_adapt(upstream, upstream_api_key, provider, "")
        if _gw.headers:
            headers.update(_gw.headers)
            if vendor_key:
                headers[auth_header_out] = f"Bearer {vendor_key}" if bearer else vendor_key
        else:
            headers[auth_header_out] = f"Bearer {real_key}" if bearer else real_key
    else:
        headers[auth_header_out] = f"Bearer {real_key}" if bearer else real_key

    # anthropic-version is required for Anthropic-compatible endpoints regardless of upstream
    if provider == "anthropic":
        headers.setdefault("anthropic-version", "2023-06-01")
    if extra_headers:
        headers.update(extra_headers)

    # Strip whitespace/newlines from all header values — stored keys can have trailing \n
    headers = {k: str(v).strip() for k, v in headers.items()}

    # Build full URL: strip any path prefix the upstream already contains so
    # upstream="/v1" + path="/v1/messages" doesn't produce double /v1/v1/messages.
    _up_path = _urlparse(upstream).path.rstrip("/")
    _req_path = path[len(_up_path):] if _up_path and path.startswith(_up_path) else path
    _full_url = upstream.rstrip("/") + _req_path

    # ponytail: a single shared async client would be better for connection
    # pooling. Per-call is fine until QPS warrants it.
    client = httpx.AsyncClient(timeout=httpx.Timeout(600.0))

    try:
        req = client.build_request("POST", _full_url, json=body, headers=headers)
        log.info("guard.proxy.forward", url=_full_url,
                 headers={k: v for k, v in headers.items() if "key" not in k.lower() and "auth" not in k.lower()})
        resp = await client.send(req, stream=True)
    except Exception as e:
        await client.aclose()
        import traceback as _tb
        log.warning("guard.proxy.upstream_unreachable", url=_full_url,
                    exc_type=type(e).__name__, err=str(e),
                    traceback=_tb.format_exc())
        return _fail_closed(502, f"Upstream {_full_url} unreachable: {type(e).__name__}: {e}")

    if resp.status_code >= 400:
        # Read the error body, close client, return as-is so the SDK sees the
        # real vendor error.
        err_body = await resp.aread()
        await resp.aclose()
        await client.aclose()
        return JSONResponse(
            status_code=resp.status_code,
            content=_safe_json(err_body, fallback={"error": "upstream error"}),
        )

    if is_stream:
        return StreamingResponse(
            _stream_chunks(client, resp, background, audit_args, upstream=upstream),
            media_type=resp.headers.get("content-type", "text/event-stream"),
        )

    # Non-streaming path
    full = await resp.aread()
    await resp.aclose()
    await client.aclose()
    background.add_task(
        _record_audit, *audit_args[:6], audit_args[6],
        int((time.monotonic() - audit_args[7]) * 1000),
        body=audit_args[8], response_bytes=full, upstream=upstream,
        prompt_summary=audit_args[9] if len(audit_args) > 9 else "",
        user_email=audit_args[10] if len(audit_args) > 10 else None,
        conductai_run_id=audit_args[11] if len(audit_args) > 11 else None,
        conductai_workflow=audit_args[12] if len(audit_args) > 12 else None,
        conductai_workflow_id=audit_args[13] if len(audit_args) > 13 else None,
        hook_session_id=audit_args[14] if len(audit_args) > 14 else None,
    )
    return JSONResponse(
        status_code=resp.status_code,
        content=_safe_json(full, fallback={}),
    )


async def _stream_chunks(
    client: httpx.AsyncClient, resp: httpx.Response,
    background: BackgroundTasks, audit_args: tuple,
    upstream: str | None = None,
) -> AsyncIterator[bytes]:
    """Pass-through every chunk. Schedule the audit event after the stream
    closes — we don't parse mid-stream in V1."""
    collected = bytearray()
    try:
        async for chunk in resp.aiter_bytes():
            collected.extend(chunk)
            yield chunk
    finally:
        await resp.aclose()
        await client.aclose()
        background.add_task(
            _record_audit, *audit_args[:6], audit_args[6],
            int((time.monotonic() - audit_args[7]) * 1000),
            body=audit_args[8], response_bytes=bytes(collected), upstream=upstream,
            prompt_summary=audit_args[9] if len(audit_args) > 9 else "",
            user_email=audit_args[10] if len(audit_args) > 10 else None,
            conductai_run_id=audit_args[11] if len(audit_args) > 11 else None,
            conductai_workflow=audit_args[12] if len(audit_args) > 12 else None,
            conductai_workflow_id=audit_args[13] if len(audit_args) > 13 else None,
            hook_session_id=audit_args[14] if len(audit_args) > 14 else None,
        )


def _record_audit(
    workspace_id: str, clerk_user_id: str, ai_tool: str, provider: str, model: str,
    decision: str, rule_id: str | None, duration_ms: int,
    *, body: dict, response_bytes: bytes | None, upstream: str | None = None,
    prompt_summary: str = "", user_email: str | None = None,
    conductai_run_id: str | None = None, conductai_workflow: str | None = None,
    conductai_workflow_id: str | None = None, hook_session_id: str | None = None,
) -> None:
    """Background task — best-effort, never blocks the response."""
    db = SessionLocal()
    try:
        set_workspace_rls(db, workspace_id)
        in_tokens, out_tokens = _extract_token_counts(body, response_bytes)
        if in_tokens is None and response_bytes is None:
            # ponytail: blocked call — estimate what vendor would have consumed
            in_tokens, out_tokens = _estimate_input_tokens(body), 0
        cost_usd = _compute_cost(provider, model, in_tokens, out_tokens)
        db.execute(
            text("""
                INSERT INTO guard_audit_events (
                  workspace_id, clerk_user_id, ai_tool, tool_call,
                  source, provider, model,
                  decision, rule_id, ts,
                  tokens_before, tokens_after, duration_ms,
                  cost_usd_after, input_summary, user_email,
                  conductai_run_id, conductai_workflow, conductai_workflow_id,
                  hook_session_id
                ) VALUES (
                  :ws, :uid, :ai, NULL,
                  'proxy', :prov, :model,
                  :dec, :rid, :ts,
                  :tin, :tout, :dur,
                  :cost, :summary, :email,
                  :run_id, :workflow, :workflow_id,
                  :hook_session_id
                )
            """),
            {
                "ws": workspace_id, "uid": clerk_user_id,
                "ai": ai_tool,
                "prov": provider, "model": model,
                "dec": decision, "rid": rule_id,
                "ts": datetime.now(timezone.utc),
                "tin": in_tokens, "tout": out_tokens, "dur": duration_ms,
                "cost": cost_usd,
                "summary": prompt_summary or upstream or "vendor",
                "email": user_email,
                "run_id": conductai_run_id,
                "workflow": conductai_workflow,
                "workflow_id": conductai_workflow_id,
                "hook_session_id": hook_session_id,
            },
        )
        db.commit()

        if decision == "blocked":
            try:
                from app.modules.guard.routers.events import notify_guard_block
                _display_email = user_email
                if not _display_email and clerk_user_id:
                    try:
                        from app.core.auth import get_clerk_user_email as _get_email
                        _display_email = _get_email(clerk_user_id)
                    except Exception:
                        pass
                notify_guard_block(db, workspace_id, decision=decision, rule_id=rule_id,
                                   user_email=_display_email or "unknown user",
                                   provider=provider, source="proxy")
            except Exception:
                pass
    except Exception as e:
        log.warning("guard.proxy.audit_failed", err=str(e))
    finally:
        db.close()


def _estimate_input_tokens(body: dict) -> int:
    """Rough token estimate from request body (chars/4). Used for blocked calls."""
    all_text: list[str] = []
    for msg in body.get("messages") or []:
        content = msg.get("content")
        if isinstance(content, str):
            all_text.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    t = part.get("text") or ""
                    if t:
                        all_text.append(t)
    system = body.get("system")
    if isinstance(system, str):
        all_text.append(system)
    return max(1, len(" ".join(all_text)) // 4)


def _extract_token_counts(body: dict, response_bytes: bytes | None) -> tuple[int | None, int | None]:
    """Best-effort token extraction across all 3 providers.

    Anthropic:        usage.input_tokens   / usage.output_tokens
    OpenAI/Perplexity: usage.prompt_tokens / usage.completion_tokens

    Works on both streaming (SSE) and non-streaming responses. Returns
    (None, None) on parse failures so the row still lands.
    """
    def _pair(usage: dict) -> tuple[int | None, int | None]:
        if not isinstance(usage, dict):
            return None, None
        return (
            usage.get("input_tokens")  or usage.get("prompt_tokens"),
            usage.get("output_tokens") or usage.get("completion_tokens"),
        )

    if not response_bytes:
        return None, None
    try:
        # Non-stream JSON
        try:
            obj = json.loads(response_bytes)
            return _pair(obj.get("usage") or {})
        except json.JSONDecodeError:
            pass
        # SSE — keep the latest usage block we see
        in_tok, out_tok = None, None
        for line in response_bytes.splitlines():
            if not line.startswith(b"data: "):
                continue
            try:
                evt = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            usage = evt.get("message", {}).get("usage") or evt.get("usage") or {}
            i, o = _pair(usage)
            if i is not None: in_tok = i
            if o is not None: out_tok = o
        return in_tok, out_tok
    except Exception:
        return None, None


def _compute_cost(provider: str, model: str, in_tok: int | None, out_tok: int | None) -> float | None:
    """USD for this call. Reuses the workspace's pricing registry.

    Token cost  = (in * input + out * output) / 1M
    Request fee = flat per-call charge (e.g. Perplexity Sonar)

    Returns None only when we couldn't get token counts AND there's no flat
    request fee — i.e. nothing to charge."""
    try:
        rates, _version = get_model_rates(provider, model)
    except Exception:
        return None
    request_fee = rates.get("request_fee_usd", 0.0)
    if not in_tok and not out_tok and not request_fee:
        return None
    token_cost = ((in_tok or 0) * rates["input"] + (out_tok or 0) * rates["output"]) / 1_000_000
    return round(token_cost + request_fee, 6)


def _safe_json(b: bytes, *, fallback: dict) -> dict:
    try:
        return json.loads(b)
    except Exception:
        return fallback


def _fail_closed(status: int, message: str) -> JSONResponse:
    """Security tool failing open is worse than no tool. Surface clear errors."""
    return JSONResponse(
        status_code=status,
        content={"error": {"type": "conduct_guard_proxy", "message": message}},
    )


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
