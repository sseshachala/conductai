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
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

import re

from app.core.config import settings
from app.core.crypto import decrypt
from app.core.database import SessionLocal
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
        return _fail_closed(401, "Missing or malformed Conduct member token")

    db = SessionLocal()
    try:
        ident = _resolve_member(db, raw)
        if not ident:
            return _fail_closed(401, "Conduct member token not recognized")
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

@router.post("/v1/messages")
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
    if not token:
        return _fail_closed(401, "Missing or malformed Conduct member token")

    # 2. Resolve workspace + user via guard_member_config
    db = SessionLocal()
    try:
        ident = _resolve_member(db, token)
        if not ident:
            return _fail_closed(401, "Conduct member token not recognized")
        workspace_id, clerk_user_id = ident
        set_workspace_rls(db, workspace_id)

        # 3. Parse request body
        try:
            body = await request.json()
        except Exception:
            return _fail_closed(400, "Body must be valid JSON")

        model = body.get("model", "unknown")
        ai_tool = request.headers.get("x-conduct-ai-tool") or _infer_ai_tool(request)

        # 4. Pre-call Guard policy evaluation
        decision = _evaluate_policies(workspace_id, provider, model, body)
        if decision["action"] == "BLOCK":
            background.add_task(
                _record_audit, workspace_id, clerk_user_id, ai_tool, provider, model,
                "BLOCK", decision["rule_id"], int((time.monotonic() - started) * 1000),
                body=body, response_bytes=None,
            )
            return JSONResponse(status_code=403, content={
                "error": {"type": "guard_block", "message": decision["message"], "rule": decision["rule_id"]},
            })

        # 5. Vault lookup — real vendor key + upstream URL
        real_key = _vault_key(db, workspace_id, provider)
        if not real_key:
            return _fail_closed(
                503,
                f"No {provider} key configured for this workspace — admin must add "
                f"it in Settings → Environments → Integrations.",
            )
        upstream = _upstream_url(db, workspace_id, provider)
    finally:
        db.close()

    # 6. Forward + stream back. Use a fresh DB session inside the background task.
    is_stream = bool(body.get("stream"))
    return await _forward(
        upstream=upstream,
        path=upstream_path,
        body=body,
        real_key=real_key,
        auth_header_out=auth_header_out,
        bearer=bearer,
        is_stream=is_stream,
        background=background,
        audit_args=(workspace_id, clerk_user_id, ai_tool, provider, model, "ALLOW", None, started, body),
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
    # ponytail: fall back to global env var so local dev works; remove when every
    # workspace provisions its own key during onboarding.
    return {
        "anthropic":  settings.anthropic_api_key,
        "openai":     settings.openai_api_key,
        "perplexity": "",
    }[provider] or None


def _upstream_url(db: Session, workspace_id: str, provider: str) -> str:
    """CONDUCT_LLM_UPSTREAM override (per-workspace) wins, else vendor default."""
    row = db.execute(
        text("""
            SELECT encrypted_credentials FROM integrations
            WHERE workspace_id = :ws AND handle = 'env_vars'
              AND encrypted_credentials IS NOT NULL
            LIMIT 1
        """),
        {"ws": workspace_id},
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
    persona = "standard"   # ponytail: hard-coded persona; per-workspace persona pick lands when needed
    db = SessionLocal()
    try:
        set_workspace_rls(db, workspace_id)
        try:
            rules = compute_policy(db, uuid.UUID(workspace_id), persona)
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
    """True if the rule has at least one proxy-applicable matcher."""
    return any(k in rule for k in ("match_provider", "match_model", "match_prompt"))


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
) -> StreamingResponse | JSONResponse:
    headers = {
        "content-type": "application/json",
        "accept": "text/event-stream" if is_stream else "application/json",
    }
    headers[auth_header_out] = f"Bearer {real_key}" if bearer else real_key
    if upstream.startswith(VENDOR_DEFAULTS["anthropic"]):
        headers["anthropic-version"] = "2023-06-01"

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
            _stream_chunks(client, resp, background, audit_args),
            media_type=resp.headers.get("content-type", "text/event-stream"),
        )

    # Non-streaming path
    full = await resp.aread()
    await resp.aclose()
    await client.aclose()
    background.add_task(
        _record_audit, *audit_args[:6], audit_args[6],
        int((time.monotonic() - audit_args[7]) * 1000),
        body=audit_args[8], response_bytes=full,
    )
    return JSONResponse(
        status_code=resp.status_code,
        content=_safe_json(full, fallback={}),
    )


async def _stream_chunks(
    client: httpx.AsyncClient, resp: httpx.Response,
    background: BackgroundTasks, audit_args: tuple,
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
            body=audit_args[8], response_bytes=bytes(collected),
        )


def _record_audit(
    workspace_id: str, clerk_user_id: str, ai_tool: str, provider: str, model: str,
    decision: str, rule_id: str | None, duration_ms: int,
    *, body: dict, response_bytes: bytes | None,
) -> None:
    """Background task — best-effort, never blocks the response."""
    db = SessionLocal()
    try:
        set_workspace_rls(db, workspace_id)
        in_tokens, out_tokens = _extract_token_counts(body, response_bytes)
        cost_usd = _compute_cost(provider, model, in_tokens, out_tokens)
        db.execute(
            text("""
                INSERT INTO guard_audit_events (
                  workspace_id, clerk_user_id, ai_tool, tool_call,
                  source, provider, model,
                  decision, rule_id, ts,
                  tokens_before, tokens_after, duration_ms,
                  cost_usd_after
                ) VALUES (
                  :ws, :uid, :ai, NULL,
                  'proxy', :prov, :model,
                  :dec, :rid, :ts,
                  :tin, :tout, :dur,
                  :cost
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
            },
        )
        db.commit()
    except Exception as e:
        log.warning("guard.proxy.audit_failed", err=str(e))
    finally:
        db.close()


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
