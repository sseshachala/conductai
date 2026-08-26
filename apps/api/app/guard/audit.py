"""Guard audit sink — records every proxy decision to guard_audit_events.

Single source of truth for \"what decision was made and by whom.\"

Public API:
- record(...)                — background-safe DB write of one audit event

Callers:
- HTTP proxy handler (app/modules/guard/routers/proxy.py) — external agents
- Lens LLM client (planned, #1218 Step 3) — in-process, dogfood

Extracted from proxy.py in #1218 Step 1b. Behavior byte-identical to the
pre-refactor implementation; regression harness (tests/regression/) locks
that in.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import structlog
from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.workspace_context import set_workspace_rls
from app.runtime.pricing import get_model_rates

log = structlog.get_logger(__name__)


# ─── Token / cost helpers (private — audit-internal) ──────────────────────────

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
            usage.get("input_tokens") or usage.get("prompt_tokens"),
            usage.get("output_tokens") or usage.get("completion_tokens"),
        )

    if not response_bytes:
        return None, None
    try:
        try:
            obj = json.loads(response_bytes)
            return _pair(obj.get("usage") or {})
        except json.JSONDecodeError:
            pass
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
            if i is not None:
                in_tok = i
            if o is not None:
                out_tok = o
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


# ─── Public API ───────────────────────────────────────────────────────────────

def record(
    workspace_id: str, clerk_user_id: str, ai_tool: str, provider: str, model: str,
    decision: str, rule_id: str | None, duration_ms: int,
    *, body: dict, response_bytes: bytes | None, upstream: str | None = None,
    prompt_summary: str = "", user_email: str | None = None,
    conductai_run_id: str | None = None, conductai_workflow: str | None = None,
    conductai_workflow_id: str | None = None, hook_session_id: str | None = None,
    evaluated_rules: list[dict] | None = None, defense_score: int | None = None,
) -> None:
    """Background task — best-effort audit write, never blocks the response.

    Writes one row to guard_audit_events with tokens, cost, rule, decision,
    and provenance metadata. On BLOCK decisions, also fires a Slack notification
    via events.notify_guard_block (best-effort — swallows failures)."""
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
                  hook_session_id,
                  evaluated_rules, defense_score
                ) VALUES (
                  :ws, :uid, :ai, NULL,
                  'proxy', :prov, :model,
                  :dec, :rid, :ts,
                  :tin, :tout, :dur,
                  :cost, :summary, :email,
                  :run_id, :workflow, :workflow_id,
                  :hook_session_id,
                  CAST(:eval AS jsonb), :score
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
                "eval": json.dumps(evaluated_rules) if evaluated_rules else None,
                "score": defense_score,
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
