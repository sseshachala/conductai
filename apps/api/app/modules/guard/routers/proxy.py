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

import httpx
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

import re

from app.core.auth import get_workspace_id, require_permission
from app.core.config import settings
from app.core.crypto import decrypt, encrypt
from app.core.database import SessionLocal, get_db
from app.models.integration import Integration
from app.core.workspace_context import set_workspace_rls
from app.modules.guard.policy_engine import compute_policy
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

MEMBER_TOKEN_PREFIX = "guard-mt-"


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
    if not raw.startswith(MEMBER_TOKEN_PREFIX):
        return _fail_closed(401, "Missing or malformed Conduct member token — run `conduct guard sync` to refresh")

    db = SessionLocal()
    try:
        ident = _resolve_member(db, raw)
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
    # Requires CLI_API_KEY header + X-Conductai-Workspace-Id. No member token needed.
    _internal_key = request.headers.get("x-conductai-internal", "")
    _is_internal = bool(
        _internal_key
        and settings.cli_api_key
        and _internal_key == settings.cli_api_key
    )

    if not token and not _is_internal:
        return _fail_closed(401, "Missing or malformed Conduct member token — run `conduct guard sync` to refresh")

    # 2. Resolve workspace + user
    db = SessionLocal()
    try:
        if _is_internal:
            workspace_id = request.headers.get("x-conductai-workspace-id", "")
            if not workspace_id:
                return _fail_closed(400, "X-Conductai-Workspace-Id required for internal proxy calls")
            set_workspace_rls(db, workspace_id)
            _internal_email = request.headers.get("x-conductai-user-email") or None
            clerk_user_id = _internal_email or "system"
        else:
            ident = _resolve_member(db, token)
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
                conductai_workflow_id=_workflow_id,
            )
            return JSONResponse(status_code=403, content={
                "error": {"type": "guard_block", "message": decision["message"], "rule": decision["rule_id"]},
            })

        # Map internal action to audit decision string
        _audit_decision = "warned" if _action == "WARN" else "allowed"
        _audit_rule_id  = decision["rule_id"] if _action == "WARN" else None

        # 5. Vault lookup — upstream key wins over vendor key when set
        upstream = _upstream_url(db, workspace_id, provider)
        real_key = _upstream_api_key(db, workspace_id) or _vault_key(db, workspace_id, provider)
        if not real_key:
            return _fail_closed(
                503,
                f"No API key configured — add {provider.upper()}_API_KEY in Settings → Environments, "
                f"or set LLM_UPSTREAM_API_KEY in Settings → Proxy.",
            )
    finally:
        db.close()

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
        audit_args=(workspace_id, clerk_user_id, ai_tool, provider, model, _audit_decision, _audit_rule_id, started, body, prompt_summary, _user_email, _run_id, _workflow, _workflow_id),
    )


# ─── Helpers ───────────────────────────────────────────────────────────────

def _extract_member_token(raw: str, *, bearer: bool) -> str | None:
    if not raw:
        return None
    if bearer:
        if not raw.lower().startswith("bearer "):
            return None
        raw = raw[7:].strip()
    if not raw.startswith(MEMBER_TOKEN_PREFIX):
        return None
    return raw


def _resolve_member(db: Session, token: str) -> tuple[str, str] | None:
    """member_token → (workspace_id, clerk_user_id). Strips the guard-mt- prefix."""
    bare = token[len(MEMBER_TOKEN_PREFIX):] if token.startswith(MEMBER_TOKEN_PREFIX) else token
    row = db.execute(
        text("""
            SELECT workspace_id::text, clerk_user_id
            FROM guard_member_config
            WHERE member_token = :tok AND active = true
            LIMIT 1
        """),
        {"tok": bare},
    ).fetchone()
    return (row[0], row[1]) if row else None


def _vault_key(db: Session, workspace_id: str, provider: str) -> str | None:
    """Find the workspace's real vendor key.

    Reuses the existing pattern from generate.py: workspace integrations carry
    encrypted_credentials keyed by handle. Falls back to settings.* env var so
    local dev / tests still work without per-workspace setup.
    """
    rows = db.execute(
        text("""
            SELECT handle, encrypted_credentials
            FROM integrations
            WHERE workspace_id = :ws
              AND handle IN (:provider, 'env_vars')
              AND encrypted_credentials IS NOT NULL
        """),
        {"ws": workspace_id, "provider": provider},
    ).fetchall()
    env_var_name = {
        "anthropic":  "ANTHROPIC_API_KEY",
        "openai":     "OPENAI_API_KEY",
        "perplexity": "PERPLEXITY_API_KEY",
    }[provider]
    for handle, enc in rows:
        try:
            creds = decrypt(enc) or {}
        except Exception:
            continue
        if handle == provider:
            k = creds.get("api_key")
        else:
            k = creds.get(env_var_name) or creds.get(env_var_name.lower())
        if k:
            return k
    # Fail-closed: no global env-key fallback. A misconfigured workspace
    # gets a clean 503 instead of silently routing through our default key.
    return None


def _upstream_api_key(db: Session, workspace_id: str) -> str | None:
    """Return LLM_UPSTREAM_API_KEY from proxy_config if set — used when routing through a custom gateway."""
    row = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == "proxy_config",
    ).first()
    if row:
        try:
            return (decrypt(row.encrypted_credentials) or {}).get("LLM_UPSTREAM_API_KEY") or None
        except Exception:
            pass
    return None


def _upstream_url(db: Session, workspace_id: str, provider: str) -> str:
    """CONDUCT_LLM_UPSTREAM override (per-workspace) wins, else vendor default.

    Checks proxy_config handle first (set via Settings → Proxy), then falls
    back to env_vars for legacy compatibility.
    """
    for handle in ("proxy_config", "env_vars"):
        row = db.execute(
            text("""
                SELECT encrypted_credentials FROM integrations
                WHERE workspace_id = :ws AND handle = :handle
                  AND encrypted_credentials IS NOT NULL
                LIMIT 1
            """),
            {"ws": workspace_id, "handle": handle},
        ).fetchone()
        if row:
            try:
                creds = decrypt(row[0]) or {}
                override = creds.get("CONDUCT_LLM_UPSTREAM") or creds.get("conduct_llm_upstream")
                if override:
                    return f"{override.rstrip('/')}/{provider}"
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
        set_workspace_rls(db, workspace_id)
        try:
            _pc = db.query(Integration).filter(
                Integration.workspace_id == workspace_id,
                Integration.handle == "proxy_config",
            ).first()
            rules = compute_policy(db, uuid.UUID(workspace_id), "proxy")
        except Exception as e:
            log.warning("guard.proxy.policy_load_failed", err=str(e))
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
) -> StreamingResponse | JSONResponse:
    headers = {
        "content-type": "application/json",
        "accept": "text/event-stream" if is_stream else "application/json",
    }
    headers[auth_header_out] = f"Bearer {real_key}" if bearer else real_key
    if upstream.startswith(VENDOR_DEFAULTS["anthropic"]):
        headers["anthropic-version"] = "2023-06-01"
    if extra_headers:
        headers.update(extra_headers)

    # ponytail: a single shared async client would be better for connection
    # pooling. Per-call is fine until QPS warrants it.
    client = httpx.AsyncClient(base_url=upstream, timeout=httpx.Timeout(600.0))

    try:
        req = client.build_request("POST", path, json=body, headers=headers)
        resp = await client.send(req, stream=True)
    except httpx.HTTPError as e:
        await client.aclose()
        log.warning("guard.proxy.upstream_unreachable", err=str(e))
        return _fail_closed(502, f"Upstream {upstream} unreachable")

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
        )


def _record_audit(
    workspace_id: str, clerk_user_id: str, ai_tool: str, provider: str, model: str,
    decision: str, rule_id: str | None, duration_ms: int,
    *, body: dict, response_bytes: bytes | None, upstream: str | None = None,
    prompt_summary: str = "", user_email: str | None = None,
    conductai_run_id: str | None = None, conductai_workflow: str | None = None,
    conductai_workflow_id: str | None = None,
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
                  conductai_run_id, conductai_workflow, conductai_workflow_id
                ) VALUES (
                  :ws, :uid, :ai, NULL,
                  'proxy', :prov, :model,
                  :dec, :rid, :ts,
                  :tin, :tout, :dur,
                  :cost, :summary, :email,
                  :run_id, :workflow, :workflow_id
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
            },
        )
        db.commit()

        if decision == "blocked":
            try:
                from app.modules.guard.routers.events import notify_guard_block
                notify_guard_block(db, workspace_id, decision=decision, rule_id=rule_id,
                                   user_email=user_email or clerk_user_id,
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
    proxy_persona: str = "agent"


@guard_router.get("/proxy-config")
def get_proxy_config(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    row = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == "proxy_config",
    ).first()
    upstream = ""
    has_upstream_key = False
    proxy_persona = "standard"
    if row:
        try:
            creds = decrypt(row.encrypted_credentials) or {}
            upstream = creds.get("CONDUCT_LLM_UPSTREAM", "")
            has_upstream_key = bool(creds.get("LLM_UPSTREAM_API_KEY"))
            proxy_persona = creds.get("PROXY_PERSONA", "agent")
        except Exception:
            pass
    return {
        "conduct_proxy_url": _workspace_proxy_url(db, workspace_id),
        "llm_upstream": upstream,
        "has_upstream_key": has_upstream_key,
        "proxy_persona": proxy_persona,
    }


@guard_router.put("/proxy-config")
def save_proxy_config(
    body: ProxyConfigBody,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    # Preserve existing upstream key if not being updated
    row = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == "proxy_config",
        Integration.environment_id == None,  # noqa: E711
    ).first()
    existing: dict = {}
    if row:
        try:
            existing = decrypt(row.encrypted_credentials) or {}
        except Exception:
            pass

    creds = {
        "CONDUCT_LLM_UPSTREAM": body.llm_upstream,
        "LLM_UPSTREAM_API_KEY": body.llm_upstream_api_key or existing.get("LLM_UPSTREAM_API_KEY", ""),
        "PROXY_PERSONA": body.proxy_persona or "agent",
    }
    encrypted = encrypt(creds)
    if row:
        row.encrypted_credentials = encrypted
    else:
        db.add(Integration(
            workspace_id=workspace_id, service="proxy_config", handle="proxy_config",
            auth_method="api_key", encrypted_credentials=encrypted, environment_id=None,
        ))
    db.commit()
    return {"saved": True}
