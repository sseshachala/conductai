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
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.workspace_context import set_workspace_rls

log = structlog.get_logger(__name__)


# ─── Token / cost helpers (private — audit-internal) ──────────────────────────
#
# #2209 Session 2: these are compat shims over
# ``app.runtime.accounting.estimator`` and ``.pricing``. The extraction and
# helper logic they used to inline lives in that module now — this file keeps
# the legacy aggregation semantics (joined-string count for text shapes) so
# reservations remain byte-identical while the shared engine is behind shadow.
# Deleted in Session 6/7 once the shared engine is authoritative.

def _estimate_input_tokens(body: dict) -> int:
    """Rough token estimate from request body (chars/4). Used for blocked calls.

    Compat shim over ``runtime.accounting.estimator``. Preserves the legacy
    joined-string aggregation across text shapes for byte-identical output.
    """
    from app.runtime.accounting.estimator import (
        _extract_response_input,
        _extract_text,
        _tool_schema_tokens,
        _vision_tokens,
    )

    text_chunks: list[str] = _extract_text(body)
    if isinstance(body, dict):
        system = body.get("system")
        if isinstance(system, str):
            text_chunks.append(system)
        instructions = body.get("instructions")
        if isinstance(instructions, str):
            text_chunks.append(instructions)
    text_chunks.extend(_extract_response_input(body))
    text_tokens = len(" ".join(text_chunks)) // 4
    return max(1, text_tokens + _tool_schema_tokens(body) + _vision_tokens(body))


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
            usage = (
                evt.get("message", {}).get("usage")
                or evt.get("response", {}).get("usage")
                or evt.get("usage")
                or {}
            )
            i, o = _pair(usage)
            if i is not None:
                in_tok = i
            if o is not None:
                out_tok = o
        return in_tok, out_tok
    except Exception:
        return None, None


def _compute_cost(provider: str, model: str, in_tok: int | None, out_tok: int | None, *, strict: bool = False) -> float | None:
    """USD for this call. Compat shim over ``runtime.accounting.pricing``.

    Returns None only when we couldn't get token counts AND there's no flat
    request fee — i.e. nothing to charge. Preserves ``round(_, 6)`` display
    precision so audit rows remain byte-identical.
    """
    from app.runtime.accounting.pricing import default_pricing_service

    try:
        result = default_pricing_service().price_tokens(
            provider,
            model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            strict=strict,
        )
    except Exception:
        return None
    if result.microdollars is None:
        return None
    return round(result.microdollars / 1_000_000, 6)


def _compute_audit_cost(
    provider: str,
    model: str,
    in_tok: int | None,
    out_tok: int | None,
    routing_meta: dict | None,
) -> float | None:
    if (routing_meta or {}).get("billable", True) is False:
        return None
    return _compute_cost(provider, model, in_tok, out_tok)


# ─── Public API ───────────────────────────────────────────────────────────────

def record(
    workspace_id: str, clerk_user_id: str, ai_tool: str, provider: str, model: str,
    decision: str, rule_id: str | None, duration_ms: int,
    *, body: dict, response_bytes: bytes | None, upstream: str | None = None,
    prompt_summary: str = "", user_email: str | None = None,
    conductai_run_id: str | None = None, conductai_workflow: str | None = None,
    conductai_workflow_id: str | None = None, hook_session_id: str | None = None,
    evaluated_rules: list[dict] | None = None, defense_score: int | None = None,
    routing_meta: dict | None = None,
    receipt_id: str | None = None,
    share_token_hash: str | None = None,
    execution_status: str | None = None,
    result_summary: str | None = None,
    # Phase 0 of #1959 fix: previously omitted, so successful Gateway rows
    # could not satisfy an exact agent-identity filter. Nullable to preserve
    # backward-compat for legacy callers that don't resolve an identity
    # (guard-mt-* member tokens, cedar-import, in-process calls without one).
    agent_identity_id: str | None = None,
    # Follow-up to #1971 — FastAPI request path (e.g. /proxy/anthropic/v1/messages
    # vs /gateway/v1/anthropic/v1/messages). Distinguishes legacy from new
    # Gateway traffic at query time. NULL for in-process callers.
    route: str | None = None,
) -> None:
    """Background task — best-effort audit write, never blocks the response.

    Writes one row to guard_audit_events with tokens, cost, rule, decision,
    and provenance metadata. On BLOCK decisions, also fires a Slack notification
    via events.notify_guard_block (best-effort — swallows failures).

    `receipt_id` is a pre-minted row id so the caller can return
    `receipt_url` in the block response before this background task runs.
    `share_token_hash` (sha256 of a raw short-lived token) is populated
    only for trial calls, so the anonymous public receipt endpoint can
    authorize a stranger reading their own block."""
    if agent_identity_id is None:
        # PR-0.5b invariant — record() only writes source='gateway' rows,
        # and /gateway/v1/* auth is mandatory. A None here is a leaky
        # caller path that the counter surfaces so we can chase it.
        log.warning(
            "guard.audit.missing_agent_identity_id",
            writer="record",
            workspace_id=workspace_id,
            ai_tool=ai_tool,
        )
        try:
            from app.modules.guard.observability.metrics import GUARD_AUDIT_MISSING_AGENT_ID
            GUARD_AUDIT_MISSING_AGENT_ID.labels(writer="record").inc()
        except Exception:  # noqa: BLE001 — never let the counter break audit
            pass
    db = SessionLocal()
    try:
        set_workspace_rls(db, workspace_id)
        in_tokens, out_tokens = _extract_token_counts(body, response_bytes)
        if in_tokens is None and response_bytes is None and execution_status != "error":
            # ponytail: blocked call — estimate what vendor would have consumed
            in_tokens, out_tokens = _estimate_input_tokens(body), 0
        cost_usd = _compute_audit_cost(
            provider,
            model,
            in_tokens,
            out_tokens,
            routing_meta,
        )
        # Mint id in Python — pgcrypto/gen_random_uuid isn't guaranteed to be
        # loaded on every deploy, so we don't rely on it. Caller may pre-mint
        # (block path) so the response can reference the row before the
        # background write lands.
        import uuid as _uuid
        row_id = receipt_id or str(_uuid.uuid4())
        db.execute(
            text("""
                INSERT INTO guard_audit_events (
                  id,
                  workspace_id, clerk_user_id, agent_identity_id, ai_tool, tool_call,
                  source, provider, model,
                  decision, rule_id, ts,
                  tokens_before, tokens_after, duration_ms,
                  cost_usd_after, input_summary, user_email,
                  conductai_run_id, conductai_workflow, conductai_workflow_id,
                  hook_session_id,
                  evaluated_rules, defense_score,
                  routing_meta,
                  share_token_hash,
                  execution_status, result_summary,
                  route
                ) VALUES (
                  CAST(:row_id AS uuid),
                  :ws, :uid, CAST(:agent_id AS uuid), :ai, NULL,
                  'gateway', :prov, :model,
                  :dec, :rid, :ts,
                  :tin, :tout, :dur,
                  :cost, :summary, :email,
                  :run_id, :workflow, :workflow_id,
                  :hook_session_id,
                  CAST(:eval AS jsonb), :score,
                  CAST(:routing AS jsonb),
                  :share_token_hash,
                  :execution_status, :result_summary,
                  :route
                )
            """),
            {
                "row_id": row_id,
                "ws": workspace_id, "uid": clerk_user_id,
                "agent_id": agent_identity_id,
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
                "routing": json.dumps(routing_meta) if routing_meta else None,
                "share_token_hash": share_token_hash,
                "execution_status": execution_status,
                "result_summary": result_summary,
                "route": route,
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
                                   provider=provider, source="gateway")
            except Exception:
                pass
    except Exception as e:
        # Phase 0 of #1959 — the swallow-and-log pattern was hiding real drops.
        # Bumping a labeled counter lets ops watch the aggregate rate without
        # exposing the exception message (avoids high-cardinality labels).
        try:
            from app.modules.guard.observability.metrics import GUARD_AUDIT_FAILED
            GUARD_AUDIT_FAILED.labels(reason="insert").inc()
        except Exception:
            pass
        log.warning("guard.proxy.audit_failed", err=str(e))
    finally:
        db.close()


# ─── Phase 1 of #1959 — durable inference audit primitives ────────────────────
#
# Two-phase writer: `insert_accepted()` before inference, `finalize()` after.
# Guarded by settings.guard_use_durable_audit; Phase 1 lands the primitives so
# tests and later phases can iterate without touching hot paths.
#
# Lifecycle:
#     insert_accepted() → lifecycle_state='accepted'  (accepted_at, lease_expires_at set)
#     finalize()        → lifecycle_state='finalized' (finalized_at, decision, tokens, cost set)
#
# Phase 4's reconciler scans the ix_guard_audit_events_accepted_lease partial
# index for rows still in 'accepted' past lease_expires_at, flips them to
# 'orphaned' or 'expired' depending on cause.
# ──────────────────────────────────────────────────────────────────────────────

def insert_accepted(
    workspace_id: str,
    clerk_user_id: str | None,
    ai_tool: str,
    provider: str,
    model: str,
    *,
    request_id: str,
    body: dict,
    prompt_summary: str = "",
    user_email: str | None = None,
    agent_identity_id: str | None = None,
    route: str | None = None,
    hook_session_id: str | None = None,
    routing_meta: dict | None = None,
    lease_seconds: int | None = None,
    receipt_id: str | None = None,
    # Phase 2: field coverage parity with record() for pre-inference-knowable
    # fields. evaluated_rules + defense_score belong on finalize() because
    # they're policy-eval outputs known post-inference.
    share_token_hash: str | None = None,
    conductai_run_id: str | None = None,
    conductai_workflow: str | None = None,
    conductai_workflow_id: str | None = None,
    blast_radius: dict | None = None,
) -> str:
    """Write an 'accepted' row before inference. Returns the row id.

    Emits a row with lifecycle_state='accepted', accepted_at=now, and
    lease_expires_at=now+lease_seconds. Response-shaped fields (tokens,
    cost, response_bytes) stay NULL until finalize() runs.

    Decision starts as 'accepted' — the caller flips it to
    'allowed' | 'blocked' | 'warned' via finalize().

    Idempotent on request_id via ux_guard_audit_events_request_id (partial
    unique). A duplicate insert raises IntegrityError; callers should treat
    that as "another worker already accepted this request" and continue.

    Raises IntegrityError on request_id collision. Any other failure is
    logged and re-raised — unlike record(), this writer is on the critical
    path and cannot silently swallow.
    """
    from app.core.config import settings
    import uuid as _uuid

    lease = lease_seconds if lease_seconds is not None else settings.guard_durable_audit_lease_seconds
    now = datetime.now(timezone.utc)
    row_id = receipt_id or str(_uuid.uuid4())
    input_tokens = _estimate_input_tokens(body) if body else None

    if agent_identity_id is None:
        # PR-0.5b invariant — same as record(): source='gateway' hardcoded,
        # auth mandatory upstream, so None is a writer path bug.
        log.warning(
            "guard.audit.missing_agent_identity_id",
            writer="insert_accepted",
            workspace_id=workspace_id,
            ai_tool=ai_tool,
            request_id=request_id,
        )
        try:
            from app.modules.guard.observability.metrics import GUARD_AUDIT_MISSING_AGENT_ID
            GUARD_AUDIT_MISSING_AGENT_ID.labels(writer="insert_accepted").inc()
        except Exception:  # noqa: BLE001
            pass

    db = SessionLocal()
    try:
        set_workspace_rls(db, workspace_id)
        db.execute(
            text("""
                INSERT INTO guard_audit_events (
                  id,
                  workspace_id, clerk_user_id, agent_identity_id, ai_tool, tool_call,
                  source, provider, model,
                  decision, rule_id, ts,
                  tokens_before,
                  input_summary, user_email,
                  hook_session_id,
                  routing_meta,
                  route,
                  request_id,
                  lifecycle_state,
                  accepted_at,
                  lease_expires_at,
                  share_token_hash,
                  conductai_run_id,
                  conductai_workflow,
                  conductai_workflow_id,
                  blast_radius
                ) VALUES (
                  CAST(:row_id AS uuid),
                  :ws, :uid, CAST(:agent_id AS uuid), :ai, NULL,
                  'gateway', :prov, :model,
                  'accepted', NULL, :ts,
                  :tin,
                  :summary, :email,
                  :hook_session_id,
                  CAST(:routing AS jsonb),
                  :route,
                  CAST(:request_id AS uuid),
                  'accepted',
                  :accepted_at,
                  :lease_expires_at,
                  :share_token_hash,
                  :run_id,
                  :workflow,
                  :workflow_id,
                  CAST(:blast_radius AS jsonb)
                )
            """),
            {
                "row_id": row_id,
                "ws": workspace_id, "uid": clerk_user_id,
                "agent_id": agent_identity_id,
                "ai": ai_tool,
                "prov": provider, "model": model,
                "ts": now,
                "tin": input_tokens,
                "summary": prompt_summary or "vendor",
                "email": user_email,
                "hook_session_id": hook_session_id,
                "routing": json.dumps(routing_meta) if routing_meta else None,
                "route": route,
                "request_id": request_id,
                "accepted_at": now,
                "lease_expires_at": now + timedelta(seconds=lease),
                "share_token_hash": share_token_hash,
                "run_id": conductai_run_id,
                "workflow": conductai_workflow,
                "workflow_id": conductai_workflow_id,
                "blast_radius": json.dumps(blast_radius) if blast_radius else None,
            },
        )
        db.commit()
        return row_id
    except Exception:
        db.rollback()
        try:
            from app.modules.guard.observability.metrics import GUARD_AUDIT_FAILED
            GUARD_AUDIT_FAILED.labels(reason="insert_accepted").inc()
        except Exception:
            pass
        raise
    finally:
        db.close()


def finalize(
    row_id: str,
    workspace_id: str,
    *,
    decision: str,
    provider: str,
    model: str,
    body: dict,
    response_bytes: bytes | None,
    duration_ms: int,
    rule_id: str | None = None,
    routing_meta: dict | None = None,
    execution_status: str | None = None,
    result_summary: str | None = None,
    # Phase 2: policy-eval outputs known only post-inference. These
    # complete record()'s field coverage for the durable path.
    evaluated_rules: list[dict] | None = None,
    defense_score: int | None = None,
    user_email: str | None = None,
    rule_message: str | None = None,
    clerk_user_id: str | None = None,
    ai_tool: str | None = None,
) -> bool:
    """Flip an 'accepted' row to 'finalized' with the real outcome.

    Returns True when the row was updated, False when no row matched (either
    the id doesn't exist, or the row was already finalized/expired). The
    WHERE clause pinning lifecycle_state='accepted' guarantees we never
    regress a finalized row back to a pending state — the reconciler in
    Phase 4 depends on this invariant.

    Response-derived fields (tokens, cost) are best-effort. On parse failure
    the row still gets lifecycle_state='finalized' and finalized_at=now so
    the reconciler doesn't treat the row as orphaned; downstream analytics
    read tokens as NULL for those rows.
    """
    in_tokens, out_tokens = _extract_token_counts(body, response_bytes)
    if in_tokens is None and response_bytes is None and execution_status != "error":
        in_tokens, out_tokens = _estimate_input_tokens(body) if body else None, 0
    cost_usd = _compute_audit_cost(provider, model, in_tokens, out_tokens, routing_meta)

    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        set_workspace_rls(db, workspace_id)
        result = db.execute(
            text("""
                UPDATE guard_audit_events
                SET lifecycle_state  = 'finalized',
                    finalized_at     = :finalized_at,
                    decision         = :decision,
                    rule_id          = :rule_id,
                    rule_message     = COALESCE(:rule_message, rule_message),
                    duration_ms      = :duration_ms,
                    tokens_before    = COALESCE(:tin, tokens_before),
                    tokens_after     = :tout,
                    cost_usd_after   = :cost,
                    routing_meta     = CAST(:routing AS jsonb),
                    execution_status = :execution_status,
                    result_summary   = :result_summary,
                    evaluated_rules  = COALESCE(CAST(:eval AS jsonb), evaluated_rules),
                    defense_score    = COALESCE(:score, defense_score),
                    user_email       = COALESCE(:user_email, user_email)
                WHERE id = CAST(:row_id AS uuid)
                  AND lifecycle_state = 'accepted'
            """),
            {
                "row_id": row_id,
                "finalized_at": now,
                "decision": decision,
                "rule_id": rule_id,
                "duration_ms": duration_ms,
                "tin": in_tokens,
                "tout": out_tokens,
                "cost": cost_usd,
                "routing": json.dumps(routing_meta) if routing_meta else None,
                "execution_status": execution_status,
                "result_summary": result_summary,
                "eval": json.dumps(evaluated_rules) if evaluated_rules else None,
                "score": defense_score,
                "user_email": user_email,
                "rule_message": rule_message,
            },
        )
        db.commit()
        _updated = result.rowcount == 1

        # Gap #2 from Phase 1 self-review — mirror record()'s behavior: fire
        # the Slack block notifier post-commit when the finalized decision is
        # a block. Best-effort, swallowed on failure so the return value
        # still reflects whether the row was updated.
        if _updated and decision == "blocked":
            try:
                from app.modules.guard.routers.events import notify_guard_block
                _display_email = user_email
                if not _display_email and clerk_user_id:
                    try:
                        from app.core.auth import get_clerk_user_email as _get_email
                        _display_email = _get_email(clerk_user_id)
                    except Exception:
                        pass
                notify_guard_block(
                    db, workspace_id,
                    decision=decision,
                    rule_id=rule_id,
                    user_email=_display_email or "unknown user",
                    provider=provider,
                    source="gateway",
                )
            except Exception:
                pass

        # Post-P1-review Finding 2 (recovery semantics): when the row
        # was already flipped to orphaned/expired by the reconciler, the
        # UPDATE returns rowcount=0 and we lose the real outcome. Log
        # this explicitly and bump the anomaly counter so ops sees the
        # tail — the fix is NOT to allow orphaned→finalized (mutable
        # terminal states hurt auditability), but to keep the lease
        # correct so this rarely happens. See guard_durable_audit_lease
        # _seconds default of 630s + the streaming heartbeat.
        if not _updated:
            try:
                from app.modules.guard.observability.metrics import GUARD_AUDIT_FAILED
                GUARD_AUDIT_FAILED.labels(reason="late_finalize").inc()
            except Exception:
                pass
            log.warning(
                "guard.audit.late_finalize",
                row_id=row_id,
                workspace_id=workspace_id,
                decision=decision,
            )
        return _updated
    except Exception:
        db.rollback()
        try:
            from app.modules.guard.observability.metrics import GUARD_AUDIT_FAILED
            GUARD_AUDIT_FAILED.labels(reason="finalize").inc()
        except Exception:
            pass
        raise
    finally:
        db.close()


def renew_lease(
    row_id: str,
    workspace_id: str,
    *,
    additional_seconds: int,
) -> bool:
    """Extend an in-flight row's lease_expires_at.

    Called by the streaming path every guard_durable_audit_stream_renew
    _seconds while chunks flow so a legitimate long request never trips
    the Phase 4 reconciler mid-stream (P1 review Finding 2 + Finding 4).

    Returns True if the row still exists and was in 'accepted' state;
    False if it was already orphaned/finalized (nothing to renew). Silent
    on any exception — this is a best-effort heartbeat, the actual write
    always wins via the finalize() UPDATE.
    """
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        set_workspace_rls(db, workspace_id)
        result = db.execute(
            text("""
                UPDATE guard_audit_events
                SET lease_expires_at = :new_lease
                WHERE id = CAST(:row_id AS uuid)
                  AND lifecycle_state = 'accepted'
            """),
            {
                "row_id": row_id,
                "new_lease": now + timedelta(seconds=additional_seconds),
            },
        )
        db.commit()
        return (result.rowcount or 0) == 1
    except Exception:
        db.rollback()
        try:
            from app.modules.guard.observability.metrics import GUARD_AUDIT_FAILED
            GUARD_AUDIT_FAILED.labels(reason="renew_lease").inc()
        except Exception:
            pass
        log.warning("guard.audit.renew_lease_failed", row_id=row_id)
        return False
    finally:
        db.close()
