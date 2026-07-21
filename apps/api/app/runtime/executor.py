"""
DAG Executor — runs a workflow version block by block.

Execution model:
- Topologically sort the graph
- Execute each block, passing accumulated state from previous blocks
- Logic blocks route execution: pass/fail source handles control which branch runs
- Approval blocks pause the run; resume via POST /runs/{id}/approve
- Write a run_event for every state transition
- On any failure, mark the run failed and run cleanup blocks
"""
import json
import os
import re
import socket
import structlog
from typing import Any

from app.core.config import settings
from app.core.credentials import CredentialStore, get_all_credentials
from app.core.database import SessionLocal
from app.models.environment import Environment  # noqa: F401 — used for FK relationship loading
from app.models.run import Run
from app.models.workflow import WorkflowVersion

from app.runtime.runtime import (  # noqa: F401
    _agent_config, _now, _redact, _redact_payload, _write_trace, _emit,
)
from app.runtime.dag_runner import (  # noqa: F401
    ApprovalRequired, ClarificationRequired, _classify_failure,
)

log = structlog.get_logger(__name__)

# CredentialStore lives in app.core.credentials — imported above


# ── Outcome detection ────────────────────────────────────────────────────────
# Maps playbook_slug → (outcome_type, artifact_url_keys, requires_artifact)
# requires_artifact=True: only record outcome if the artifact URL is found in state
# requires_artifact=False: record outcome on success regardless (the action itself is the outcome)
_OUTCOME_MAP: dict[str, tuple[str, list[str], bool]] = {
    "autopilot":              ("pr_opened",              ["pr_url"],   True),
    "autopilot_quick":        ("pr_opened",              ["pr_url"],   True),
    "autopilot_full":         ("pr_opened",              ["pr_url"],   True),
    "autopilot_approved":     ("pr_opened",              ["pr_url"],   True),
    "ai_ready":               ("pr_opened",              ["pr_url"],   True),
    "smoke_test":             ("pipeline_verified",      [],           False),
    "pr_reviewer":            ("review_completed",       [],           False),
    "copilot_reviewer":       ("review_completed",       [],           False),
    "security_scanner":       ("review_completed",       [],           False),
    "issue_triage":           ("issue_triaged",          [],           False),
    "ci_notify":              ("ci_alert_sent",          [],           False),
    "flaky_test_detective":   ("flaky_test_filed",       ["issue_url"], True),
    "release_readiness":      ("release_reviewed",       [],           False),
    "release_notes":          ("release_notes_drafted",  [],           False),
    "release_gating":         ("release_tagged",         ["tag_url"],  True),
    "incident_responder":     ("incident_investigated",  [],           False),
    "postmortem_drafter":     ("postmortem_drafted",     ["issue_url"], True),
    "dependency_updater":     ("dependency_updated",     ["pr_url"],   True),
    "security_patch_updater": ("security_patch_applied", ["pr_url"],   True),
    "docs_drift_detector":    ("docs_updated",           ["issue_url"], True),
    "terraform_reviewer":     ("terraform_reviewed",     [],           False),
    "multi_repo_scanner":     ("security_findings_fleet", ["aggregate.top_findings"], False),
    "dependency_audit":       ("deps_audited",            ["fetch_outdated.count"],   False),
    "bulk_pr_reviewer":       ("prs_reviewed",            ["fetch_prs.count"],        False),
    "multi_env_smoke_test":   ("smoke_fleet",             ["diff_results.summary"],   False),
}


def _find_artifact(state: dict, *keys: str) -> str | None:
    """Search state shallowly (top-level + one level deep) for the first URL value matching any key."""
    # Top-level first
    for key in keys:
        v = state.get(key)
        if isinstance(v, str) and v.startswith("http"):
            return v
    # One level into block outputs
    for block_val in state.values():
        if not isinstance(block_val, dict):
            continue
        for key in keys:
            v = block_val.get(key)
            if isinstance(v, str) and v.startswith("http"):
                return v
    return None


def _detect_outcome(playbook_slug: str | None, state: dict, run_status: str) -> dict | None:
    """
    Return a structured outcome dict for a completed run, or None if not applicable.
    Called after run.status is set. Only fires on succeeded runs with a known slug.
    """
    if run_status != "succeeded" or not playbook_slug:
        return None
    entry = _OUTCOME_MAP.get(playbook_slug)
    if not entry:
        return None
    outcome_type, artifact_keys, requires_artifact = entry
    artifact_url = _find_artifact(state, *artifact_keys) if artifact_keys else None
    if requires_artifact and not artifact_url:
        return None  # action didn't produce the expected artifact — don't miscount
    result: dict = {"type": outcome_type}
    if artifact_url:
        result["artifact_url"] = artifact_url
    return result


def _emit_run_analytics(run, version, state: dict, db, *, outcome: str, error: str = "") -> None:
    """
    Write one RunAnalyticsEvent row at the end of every run.
    Fire-and-forget — never raises, never blocks the run result.
    One row per run (not per block); feeds benchmark, eval harness, cross-tenant analytics.
    """
    try:
        import hashlib
        from app.models.run_analytics_event import RunAnalyticsEvent

        blocks_executed = sum(1 for k, v in state.items() if not k.startswith("__") and isinstance(v, dict))

        total_input = total_output = total_tools = 0
        total_cost: float | None = None
        human_verdict: str | None = None
        for k, v in state.items():
            if k.startswith("__") or not isinstance(v, dict):
                continue
            total_input  += v.get("input_tokens", 0) or 0
            total_output += v.get("output_tokens", 0) or 0
            total_tools  += v.get("turns", 0) or 0
            if v.get("cost_usd"):
                total_cost = (total_cost or 0) + float(v["cost_usd"])
            if "decision" in v:
                human_verdict = v["decision"]

        duration_ms: int | None = None
        if run.completed_at and run.created_at:
            duration_ms = int((run.completed_at - run.created_at).total_seconds() * 1000)

        wf = getattr(version, "workflow", None) if version else None
        # Use the actual playbook_slug column; fall back to name-derived slug for custom workflows
        playbook_slug = (
            getattr(wf, "playbook_slug", None)
            or re.sub(r"[^a-z0-9]+", "_", (getattr(wf, "name", None) or "custom").lower()).strip("_")
            or "custom"
        )

        raw_trigger = str(run.triggered_by or "manual")
        if raw_trigger.startswith("webhook"):
            trigger_type = "webhook"
        elif raw_trigger.startswith(("schedule", "cron")):
            trigger_type = "cron"
        else:
            trigger_type = "manual"

        workspace_raw = str(getattr(wf, "workspace_id", run.id) if wf else run.id)
        workspace_hash = hashlib.sha256(workspace_raw.encode()).hexdigest()[:16]

        db.add(RunAnalyticsEvent(
            run_id=run.id,
            workspace_id=workspace_hash,
            playbook_slug=playbook_slug,
            model=state.get("__model") or "unknown",
            trigger_type=trigger_type,
            blocks_executed=blocks_executed,
            tool_calls=total_tools,
            input_tokens=total_input,
            output_tokens=total_output,
            duration_ms=duration_ms,
            outcome=outcome,
            human_verdict=human_verdict,
            cost_usd=total_cost,
            error=error[:2000] if error else None,
        ))
        db.commit()
        log.debug("run_analytics.written", run_id=str(run.id), outcome=outcome)
    except Exception:
        log.exception("run_analytics.failed")


_ONLINE_EVAL_QUEUE = "marshal:eval:online:queue"
_ONLINE_EVAL_QUEUE_MAX = 10_000  # cap to prevent unbounded growth when worker is down


def _enqueue_online_eval(run_id: str) -> None:
    """Push run_id to the online eval queue. Fire-and-forget — never raises."""
    try:
        import redis as _redis
        r = _redis.from_url(settings.redis_url, decode_responses=True)
        pipe = r.pipeline()
        pipe.rpush(_ONLINE_EVAL_QUEUE, run_id)
        pipe.ltrim(_ONLINE_EVAL_QUEUE, -_ONLINE_EVAL_QUEUE_MAX, -1)
        pipe.execute()
    except Exception:
        log.warning("online_eval.enqueue_failed", run_id=run_id)


# ── main entry point ──────────────────────────────────────────────────────────

def execute_run(run_id: str):
    """
    Entry point called by the worker.
    Loads the run, executes the DAG, writes events throughout.

    Supports resuming paused runs: blocks whose output is already in state
    are skipped (their previous output is preserved).
    """
    from app.runtime.dag_runner import _execute_dag

    db = SessionLocal()
    _run_token_row_id: str | None = None  # declared before try so finally can reference it
    try:
        run = db.query(Run).filter(Run.id == run_id).with_for_update().first()
        if not run:
            log.error("run.not_found", run_id=run_id)
            return
        if run.status not in ("pending", "paused", "paused_for_clarification", "paused_for_approval"):
            log.warning("run.already_claimed", run_id=run_id, status=run.status)
            return

        from sqlalchemy.orm import joinedload
        version = db.query(WorkflowVersion).options(
            joinedload(WorkflowVersion.workflow)
        ).filter(
            WorkflowVersion.id == run.workflow_version_id
        ).first()

        run.status = "running"
        run.started_at = run.started_at or _now()
        run.locked_at = _now()
        run.locked_by = f"{socket.gethostname()}:{os.getpid()}"
        run.attempt_count = (run.attempt_count or 0) + 1
        db.commit()
        _emit(db, run_id, None, "run_started", {"node_count": len((version.graph or {}).get("nodes", []))})

        # Accumulated state — includes previous run segment outputs on resume
        state: dict[str, Any] = dict(run.state or {})

        env_id = version.workflow.environment_id
        workspace_id_str = version.workflow.workspace_id

        # Load credentials and egress allowlist from the workflow's environment
        allowed_hosts: list[str] | None = None
        from app.models.environment import Environment as _Env
        _env_row = db.query(_Env).filter(_Env.id == env_id).first() if env_id else \
                   db.query(_Env).filter(_Env.workspace_id == workspace_id_str, _Env.name == "Default").first()
        if _env_row:
            allowed_hosts = _env_row.allowed_hosts or None
        credentials = get_all_credentials(db, workspace_id_str, environment_id=env_id)

        # Build RunContext — typed contract for this run. Fails fast if required fields missing.
        from app.core.credentials import mint_cred_token as _mint_cred_token
        from app.runtime.run_contract import RunContext as _RunContext
        _cred_handles = list(credentials.keys())
        _cred_token = ""
        if _cred_handles:
            try:
                _cred_token = _mint_cred_token(
                    db, str(run.id), workspace_id_str,
                    allowed_handles=_cred_handles,
                    environment_id=str(env_id) if env_id else None,
                    ttl_seconds=7200,
                )
            except Exception:
                log.warning("run.cred_token_mint_failed", run_id=run_id)

        # Stamp agent_role_id on the run if CONDUCT_AGENT_TOKEN is in credentials.
        _env_vars_creds = credentials.get("env_vars") or {}
        if isinstance(_env_vars_creds, dict) and _env_vars_creds.get("CONDUCT_AGENT_TOKEN"):
            from app.modules.agent_identity.models import AgentIdentity as _AgentIdentity
            _identity = db.query(_AgentIdentity).filter(
                _AgentIdentity.workspace_id == workspace_id_str,
                _AgentIdentity.environment_id == str(env_id or ""),
            ).first()
            if _identity and not run.agent_role_id:
                run.agent_role_id = str(_identity.id)
                db.commit()

        # Read pre-minted run token (created at trigger time).
        from app.modules.agent_identity.run_token_model import AgentRunToken as _AgentRunToken
        from app.core.crypto import decrypt as _rt_decrypt, encrypt as _rt_encrypt
        _conduct_run_token = ""
        _rt = db.query(_AgentRunToken).filter(
            _AgentRunToken.run_id == str(run.id),
            _AgentRunToken.invalidated_at == None,  # noqa: E711
        ).first()
        if _rt:
            _run_token_row_id = _rt.id
            try:
                _plaintext = (_rt_decrypt(_rt.token_encrypted) or {}).get("token") if _rt.token_encrypted else None
                if _plaintext:
                    _conduct_run_token = _plaintext
                    _ev = credentials.get("env_vars") or {}
                    if isinstance(_ev, dict):
                        _ev["CONDUCT_RUN_TOKEN"] = _plaintext
                        credentials._data["env_vars"] = _ev
                    # ponytail: keep token_encrypted intact — run may retry across blocks
            except Exception:
                log.warning("run.token_decrypt_failed", run_id=run_id)

        # Resumed runs: executor finally-block invalidated the token in the previous segment.
        # The token was already written into state before the run paused — recover it.
        if not _conduct_run_token:
            _saved_token = state.get("__conduct_run_token__", "")
            if _saved_token:
                _conduct_run_token = _saved_token
                log.info("run.token_recovered_from_state", run_id=run_id)

        # Mint a fresh token if trigger-time mint failed or token is unrecoverable.
        if not _conduct_run_token:
            import hashlib as _rth, uuid as _rtu
            from datetime import datetime as _rtdt, timezone as _rttz
            _pt = "cond_run_" + _rtu.uuid4().hex
            _mint_row = _AgentRunToken(
                id=str(_rtu.uuid4()),
                agent_identity_id=None,
                workspace_id=run.workspace_id,
                run_id=str(run.id),
                token_hash=_rth.sha256(_pt.encode()).hexdigest(),
                token_prefix=_pt[:16],
                token_encrypted=_rt_encrypt({"token": _pt}),
                created_at=_rtdt.now(_rttz.utc),
            )
            try:
                db.add(_mint_row)
                db.commit()
                _run_token_row_id = _mint_row.id
                _conduct_run_token = _pt
                log.info("run.token_minted_at_executor", run_id=run_id)
            except Exception:
                log.warning("run.token_mint_at_executor_failed", run_id=run_id)

        # Construct RunContext — single typed source of truth for all run infrastructure.
        # apply_to_state() writes every field into state so blocks read them unchanged.
        _user_email_ctx = state.get("__user_email") or None
        try:
            _ctx = _RunContext(
                workspace_id=workspace_id_str,
                run_id=str(run.id),
                cred_token=_cred_token,
                cred_api_url=settings.api_base_url,
                cred_handles=_cred_handles,
                conduct_run_token=_conduct_run_token,
                max_turns=int(state.get("__max_turns", 20)),
                max_cost_usd=float(state.get("__max_cost_usd", settings.default_max_cost_usd)),
                user_email=_user_email_ctx,
                env_id=str(env_id) if env_id else None,
            )
            _ctx.apply_to_state(state)
        except ValueError as _ctx_err:
            log.error("run.context_build_failed", run_id=run_id, error=str(_ctx_err))
            raise

        # Guard bootstrap — load once per run if enabled
        state["__guard_enabled"] = bool(version.workflow.guard_enabled)
        if state["__guard_enabled"]:
            try:
                import uuid as _uuid
                from app.modules.guard.models import GuardConfig as _GuardCfg
                from app.modules.guard.policy_engine import (
                    compute_policy as _compute_policy,
                    canonical_workspace_id as _canonical_ws,
                )
                _ws_uuid = _uuid.UUID(str(workspace_id_str))
                _policy_ws = _uuid.UUID(_canonical_ws(str(_ws_uuid)))
                _gc = db.query(_GuardCfg).filter(_GuardCfg.workspace_id == _ws_uuid).first()
                _deny = bool(getattr(_gc, "deny_on_error", True)) if _gc else True
                _persona = _gc.runtime_persona if _gc else "agent"
                try:
                    _policies = _compute_policy(db, _policy_ws, _persona)
                except Exception as _pe:
                    log.error("guard.policy_load_failed", error=str(_pe))
                    if _deny:
                        raise RuntimeError(
                            f"Guard policy load failed (fail-closed): {_pe}. "
                            "Disable Guard or set deny_on_error=false to run without it."
                        ) from _pe
                    state["__guard_enabled"] = False
                else:
                    state["__guard_policy_cache__"] = {
                        "policies":         _policies,
                        "enforcement_mode": _gc.enforcement_mode if _gc else "warn",
                        "advisory":         bool(getattr(_gc, "advisory_mode", False)) if _gc else False,
                        "deny_on_error":    _deny,
                        "workspace_id":     str(_ws_uuid),
                    }
            except RuntimeError:
                raise
            except Exception as _ge:
                log.error("guard.policy_load_failed", error=str(_ge))
                raise RuntimeError(f"Guard policy load failed (fail-closed): {_ge}") from _ge

        final_state = _execute_dag(
            run=run,
            version=version,
            initial_state=state,
            db=db,
            credentials=None,  # blocks fetch via broker using state["__cred_token__"]
            allowed_hosts=allowed_hosts,
            workspace_id_str=str(workspace_id_str),
            env_id=env_id,
        )
        _emit_run_analytics(run, version, final_state, db, outcome=run.status, error="")
        _enqueue_online_eval(str(run.id))

    except Exception as e:
        log.exception("run.executor_crash", run_id=run_id)
        if settings.sentry_dsn:
            import sentry_sdk
            with sentry_sdk.push_scope() as scope:
                scope.set_tag("run_id", str(run_id))
                sentry_sdk.capture_exception(e)
        try:
            run = db.query(Run).filter(Run.id == run_id).first()
            if run:
                run.status = "failed"
                run.completed_at = _now()
                run.locked_at = None
                run.locked_by = None
                db.commit()
                _emit_run_analytics(run, None, {}, db, outcome="failed", error=str(e))
                _enqueue_online_eval(str(run.id))
        except Exception:
            pass
    finally:
        # Invalidate ephemeral run token so it cannot be replayed after the run ends.
        if _run_token_row_id:
            try:
                from app.modules.agent_identity.run_token_model import AgentRunToken as _AgentRunToken
                from datetime import datetime as _dt, timezone as _rtz
                _inv_db = SessionLocal()
                try:
                    _rt = _inv_db.query(_AgentRunToken).filter(_AgentRunToken.id == _run_token_row_id).first()
                    if _rt and not _rt.invalidated_at:
                        _rt.invalidated_at = _dt.now(_rtz.utc)
                        _inv_db.commit()
                    _cred_tok = state.get("__cred_token__")
                    if _cred_tok:
                        from sqlalchemy import text as _csql
                        _inv_db.execute(_csql(
                            "UPDATE cred_retrieval_tokens SET expires_at = now() WHERE token = :t"
                        ), {"t": _cred_tok})
                        _inv_db.commit()
                finally:
                    _inv_db.close()
            except Exception:
                pass  # never let token cleanup crash the run
        db.close()


# ── Re-exports for backward compatibility (tests, eval pipeline, block files) ─
# Functions that moved to tool_engine or dag_runner are re-exported here so
# existing callers (tests, eval harness) that import from executor continue to work.

from app.runtime.tool_engine import (  # noqa: F401, E402
    _resolve_refs,
    _resolve_remote_host,
    _dispatch_tool,
    _check_egress,
    _dry_run_mock,
    _INTEGRATION_HOSTS,
    _summarise_tool_call,
    _extract_git_evidence,
    _safe_subprocess_env,
    _tool_read_file,
    _tool_write_file,
    _tool_run_shell,
    _tool_search_code,
)

from app.runtime.blocks.guard_block import _execute_guard  # noqa: F401
from app.runtime.dag_runner import (  # noqa: F401, E402
    _execute_dag,
    _execute_memory_inner,
    _resolve_as_list,
    CredentialStore as _CredentialStore,  # already imported above from core.credentials
    _execute_brain,
    _execute_tool,
    _checkpoint_state,
    _load_checkpoint,
    _topological_sort,
    _find_skipped_blocks,
    _with_retry,
    _dispatch_single_block,
)
