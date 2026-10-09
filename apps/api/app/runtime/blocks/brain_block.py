"""
Brain block executor.

Handles both single-call (non-agentic) and bounded agentic loop modes.
Extracted from app.runtime.executor. ``_execute_brain`` orchestrates the
phases split out in #2400: brain_setup (profile, prompts, credentials,
client), brain_model (LLM call, single turn), brain_agentic (tool loop),
brain_tools (tool dispatch) and brain_guard (Guard rule matching).
"""
from __future__ import annotations

import json

import structlog

from app.core.config import settings
from app.runtime.blocks.brain_agentic import run_agentic
from app.runtime.blocks.brain_model import BrainRun, run_single_turn
from app.runtime.blocks.brain_setup import (
    build_context,
    build_cred_env,
    build_llm_client,
    build_system_prompt,
    build_user_message,
    profile_routing,
    require_gateway_profile,
)
from app.runtime.model_router import resolve_for_workspace as _router_resolve
from app.runtime.pricing import freeze_pricing_snapshot, get_model_rates

# Re-exported for callers/tests that import these from brain_block.
from app.runtime.blocks.brain_model import (
    extract_last_json_object as _extract_last_json_object,
)
from app.runtime.blocks.brain_tools import (
    BRAIN_TOOLS,
    _MCP_JOIN_SEP,
    _classify_tool_error,
    _mcp_safe_name,
)

log = structlog.get_logger(__name__)

_LLM_CACHE_TTL = 604800  # 7 days — matches state checkpoint TTL


def _cache_key(run_id: str, block_id: str, turn: int) -> str:
    return f"llm_cache:{run_id}:{block_id}:{turn}"


def _get_redis():
    import redis as _redis
    return _redis.from_url(settings.redis_url, decode_responses=True)


def _cache_get(run_id: str | None, block_id: str | None, turn: int, _r=None):
    if not run_id or not block_id:
        return None
    try:
        r = _r or _get_redis()
        raw = r.get(_cache_key(run_id, block_id, turn))
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _cache_set(run_id: str | None, block_id: str | None, turn: int, response_json: dict, _r=None) -> None:
    if not run_id or not block_id:
        return
    try:
        r = _r or _get_redis()
        r.setex(_cache_key(run_id, block_id, turn), _LLM_CACHE_TTL, json.dumps(response_json))
    except Exception:
        pass


def _load_workspace_mcp_tools(
    workspace_id: str,
    environment_id: str | None,
    db,
    selected_ids: list[str] | None = None,
) -> list[dict]:
    """Query registered MCP servers and return their tools in Anthropic tool format.

    Tool names are prefixed as ``{server_name}::{tool_name}`` so the dispatcher
    can split on ``::`` to route the call.  Fail-open: server connection errors
    are logged and skipped — they must never kill the brain block.

    ``selected_ids`` filters which registered servers are loaded:
      - ``None`` or ``["all"]`` or ``[]`` → all workspace servers (back-compat default)
      - list of UUID strings → only those servers
    Matches the UI toggle at BlockEditor.tsx that persists ``data["mcp_server_ids"]``.
    """
    import json as _json

    # Deferred imports — must stay inside this function to avoid circular imports
    # at module load time (brain_block -> models -> database -> app startup).
    from app.core.crypto import decrypt as _decrypt

    tools: list[dict] = []

    # Normalise selection sentinel — treat None, [], and ["all"] identically as "all"
    _selected: set[str] | None = None
    if selected_ids and not (len(selected_ids) == 1 and selected_ids[0] == "all"):
        _selected = {str(sid) for sid in selected_ids}

    try:
        from app.models.mcp_server import McpServer as _McpServer
        query = db.query(_McpServer).filter(_McpServer.workspace_id == workspace_id)
        if environment_id:
            query = query.filter(
                (_McpServer.environment_id == environment_id)
                | (_McpServer.environment_id.is_(None))
            )
        servers = query.all()
        if _selected is not None:
            servers = [s for s in servers if str(s.id) in _selected]
    except Exception as exc:
        log.warning("brain.mcp_tools.query_failed", workspace_id=workspace_id, error=str(exc))
        return tools

    from app.runtime.integrations import mcp_client as _mcp_client

    for server in servers:
        cache_key = f"mcp_tools:{server.id}"
        raw_tools: list[dict] | None = None

        # Cache read — best effort
        try:
            import redis as _redis
            r = _redis.from_url(settings.redis_url, decode_responses=True)
            cached = r.get(cache_key)
            if cached:
                raw_tools = _json.loads(cached)
        except Exception:
            pass

        if raw_tools is None:
            try:
                token = _decrypt(server.encrypted_auth).get("token") if server.encrypted_auth else None
                raw_tools, _ = _mcp_client.list_tools(server.url, token, server.transport or "auto")
                # Cache write — best effort
                try:
                    r = _redis.from_url(settings.redis_url, decode_responses=True)
                    r.setex(cache_key, 300, _json.dumps(raw_tools))
                except Exception:
                    pass
            except Exception as exc:
                log.warning(
                    "brain.mcp_tools.server_unreachable",
                    server_id=str(server.id),
                    server_name=server.name,
                    error=str(exc),
                )
                continue

        # Fail-open: a cache payload of "null" or a list_tools() call that
        # returned None (instead of raising) would crash the whole brain block
        # with 'NoneType' object is not iterable. Skip the server instead.
        if not raw_tools:
            continue

        for t in raw_tools:
            tool_name = t.get("name", "")
            if not tool_name:
                continue
            _joined = f"{_mcp_safe_name(server.name)}{_MCP_JOIN_SEP}{_mcp_safe_name(tool_name)}"[:128]
            tools.append({
                "name": _joined,
                "description": (
                    f"[MCP:{server.name}] {t.get('description', '')}"
                ).strip(),
                "input_schema": t.get("inputSchema") or t.get("input_schema") or {"type": "object", "properties": {}},
            })

    return tools


def _execute_brain(
    block: dict,
    state: dict,
    compiled_artifacts: dict,
    credentials: dict | None = None,
    db=None,
    run_id: str | None = None,
    block_id: str | None = None,
    playbook_slug: str | None = None,
    injected_session=None,
    workspace_id: str = "",
    workflow_id: str | None = None,
    user_email: str | None = None,
    block_label: str | None = None,
    workflow_name: str | None = None,
    environment_id: str | None = None,
    attempt_id: str | None = None,
    resume_from_turn: int = 0,
) -> dict:
    # Import helpers from executor to avoid circular imports at module load time.
    from app.runtime.runtime import _emit, _write_trace
    from app.runtime.exceptions import ClarificationRequired
    from app.runtime.tool_engine import _resolve_remote_host, _resolve_refs, _summarise_tool_call

    _prof_row = require_gateway_profile(db, workflow_id)
    # #2401: dry run returns only after the #2170 profile checks above, so a
    # dry run can't report success for a workflow that would refuse to run.
    if state.get("__dry_run"):
        return {
            "dry_run": True,
            "note": "Dry run — Brain block would invoke Claude AI with the workflow context",
            "description": block["data"].get("description", ""),
            "is_agentic": block["data"].get("isAgentic", False),
            "remote_host": bool((block.get("data", {}).get("config") or {}).get("remote_host")),
        }
    _profile_cond_key, _profile_streaming_safe = profile_routing(db, _prof_row)

    system_prompt = build_system_prompt(block, state, compiled_artifacts, _resolve_refs)
    is_agentic = block["data"].get("isAgentic", False)

    # Model selection via router
    routing_pref = block["data"].get("routingPreference") or "balanced"
    explicit_model = block["data"].get("model") or None
    explicit_provider = block["data"].get("provider") or None
    provider, model_id, routing_reason = _router_resolve(db, workspace_id, routing_pref, explicit_model, explicit_provider)
    log.debug("brain.model_selected", block_id=block["id"], provider=provider, model=model_id, reason=routing_reason)

    # Fetch credentials from broker for session creation (SSH key, sandbox API keys).
    # This is the only in-function credential fetch; LLM keys come from the profile.
    from app.core.credentials import fetch_credential as _fetch_cred
    from app.runtime.run_contract import cred_from_state
    _cred_token_b, _cred_api_url_b, _cred_handles_b = cred_from_state(state)
    _session_creds: dict = {}
    for _h in _cred_handles_b:
        _session_creds[_h] = _fetch_cred(_cred_token_b, _h, _cred_api_url_b)

    # Resolve remote host (SSH) or runs_on provider (E2B / Modal / local).
    remote_host = _resolve_remote_host(block, state, _session_creds)
    runs_on: dict | None = block.get("data", {}).get("runs_on") or None

    if injected_session is not None:
        session = injected_session
    else:
        from app.runtime.sandbox_session import create_session as _create_session
        session = _create_session(remote_host, _session_creds, runs_on=runs_on)
    _session_closed = False

    def _close_session():
        nonlocal _session_closed
        if not _session_closed:
            _session_closed = True
            try:
                session.close()
            except Exception:
                pass

    def _dispatch_with_creds(tool_name: str, tool_input: dict) -> str:
        # Swap credential placeholders for real values in subprocess env only.
        # Placeholders appear in tool_input (logged to DB); real values never do.
        if tool_name == "run_shell" and cred_env:
            merged_env = {**cred_env, **tool_input.get("env", {})}
            resolved_env = {k: _cred_real.get(v, v) for k, v in merged_env.items()}
            tool_input = {**tool_input, "env": resolved_env}
        return session.dispatch(tool_name, tool_input)

    context = build_context(state)
    cred_env, _cred_real, cred_names = build_cred_env(_session_creds, state, run_id)
    user_message = build_user_message(block, state, context, cred_names, _resolve_refs)

    # PR 4 — legacy per-provider credential extraction is gone. The
    # Gateway profile carries every credential (vault refs on each
    # target) and the shim resolves them per attempt. We still need
    # ``_env_vars`` for the CONDUCT_RUN_TOKEN / CONDUCT_AGENT_TOKEN
    # header wiring in build_llm_client.
    _env_vars = _session_creds.get("env_vars") or {}

    pricing_snapshot = freeze_pricing_snapshot()

    llm, _conduct_proxy_url = build_llm_client(
        state=state, env_vars=_env_vars,
        profile_cond_key=_profile_cond_key,
        profile_streaming_safe=_profile_streaming_safe,
        pricing_snapshot=pricing_snapshot,
        run_id=run_id, workflow_id=workflow_id, workflow_name=workflow_name,
        playbook_slug=playbook_slug, workspace_id=workspace_id,
        environment_id=environment_id, user_email=user_email,
    )

    pricing_rates, pricing_version = get_model_rates(provider, model_id, pricing_snapshot)

    # Patch-sensitive helpers (_cache_get / _cache_set /
    # _load_workspace_mcp_tools) are read from this module's globals here,
    # at call time, so tests patching app.runtime.blocks.brain_block.<name>
    # keep applying to the extracted phases.
    r = BrainRun(
        block=block, state=state, db=db, run_id=run_id, block_id=block_id,
        playbook_slug=playbook_slug, workspace_id=workspace_id,
        workflow_id=workflow_id, user_email=user_email,
        environment_id=environment_id, attempt_id=attempt_id,
        resume_from_turn=resume_from_turn,
        emit=_emit, write_trace=_write_trace,
        summarise_tool_call=_summarise_tool_call,
        clarification_required=ClarificationRequired,
        cache_get=_cache_get, cache_set=_cache_set,
        load_mcp_tools=_load_workspace_mcp_tools,
        session=session, close_session=_close_session,
        dispatch_with_creds=_dispatch_with_creds, remote_host=remote_host,
        system_prompt=system_prompt, user_message=user_message,
        llm=llm, provider=provider, model_id=model_id,
        routing_reason=routing_reason, pricing_rates=pricing_rates,
        pricing_version=pricing_version, proxy_url=_conduct_proxy_url,
        env_vars=_env_vars,
    )

    if is_agentic:
        return run_agentic(r)
    else:
        return run_single_turn(r)
