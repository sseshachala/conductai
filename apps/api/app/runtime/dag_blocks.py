"""DAG runner block executor wrappers, auto-guard, MCP fallback, for_each (split from dag_runner.py; re-exported there)."""
from __future__ import annotations


import structlog

from app.runtime.runtime import _emit, _resolve_refs
from app.runtime.exceptions import ApprovalRequired, ClarificationRequired

log = structlog.get_logger("app.runtime.dag_runner")


# ── block executor wrappers ───────────────────────────────────────────────────

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
    from app.runtime.blocks.brain_block import _execute_brain as _brain_impl
    return _brain_impl(
        block, state, compiled_artifacts,
        credentials=credentials, db=db, run_id=run_id,
        block_id=block_id, playbook_slug=playbook_slug,
        injected_session=injected_session,
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        user_email=user_email,
        block_label=block_label,
        workflow_name=workflow_name,
        environment_id=environment_id,
        attempt_id=attempt_id,
        resume_from_turn=resume_from_turn,
    )


def _execute_tool(block: dict, state: dict, credentials: dict, allowed_hosts: list[str] | None = None, db=None, workspace_id: str = "") -> dict:
    from app.runtime.blocks.tool_block import _execute_tool as _tool_impl
    return _tool_impl(block, state, credentials, allowed_hosts=allowed_hosts, db=db, workspace_id=workspace_id)


def _execute_output(block: dict, state: dict, credentials: dict, workflow_name: str = "Agent", trace_url: str = "", run_id: str = "", workspace_id: str = "") -> dict:
    from app.runtime.blocks.output_block import _execute_output as _output_impl
    return _output_impl(block, state, credentials, workflow_name=workflow_name, trace_url=trace_url, run_id=run_id, workspace_id=workspace_id)


def _evaluate_condition_jinja(raw: str, state: dict) -> str | None:
    from app.runtime.blocks.logic_block import _evaluate_condition_jinja as _ecj_impl
    return _ecj_impl(raw, state)


def _execute_logic(block: dict, state: dict) -> dict:
    from app.runtime.blocks.logic_block import _execute_logic as _logic_impl
    return _logic_impl(block, state)


def _execute_approval(block: dict, state: dict, credentials: dict, run_id: str) -> dict:
    from app.runtime.blocks.approval_block import _execute_approval as _approval_impl
    return _approval_impl(block, state, credentials, run_id)


from app.runtime.blocks.guard_block import _execute_guard as _guard_impl


def _auto_guard_check(
    state: dict, db, run_id, block_id: str, block_type: str,
    workspace_id_str: str, version, user_email: str | None,
) -> None:
    """Fire guard check before brain/tool/output blocks using run-start cached policy."""
    if not state.get("__guard_enabled"):
        return
    cache = state.get("__guard_policy_cache__")
    if not cache:
        return
    try:
        slug = getattr(getattr(version, "workflow", None), "playbook_slug", None)
        wf_name = getattr(getattr(version, "workflow", None), "name", None) or slug
        _guard_block = {
            "id": f"__guard_{block_id}",
            "config": {"enforcement_mode": cache["enforcement_mode"]},
        }
        result = _guard_impl(
            _guard_block, state, workspace_id_str, db,
            run_id=run_id,
            playbook_slug=slug,
            workflow_id=str(version.workflow.id),
            user_email=user_email,
            workflow_name=wf_name,
            _policy_cache=cache,
        )
        state[f"__guard_{block_id}"] = result
        _emit(db, run_id, f"__guard_{block_id}", "guard_check", {
            "block_type":       block_type,
            "status":           result.get("status"),
            "rules_checked":    result.get("rules_checked", 0),
            "violations":       result.get("violations", 0),
            "enforcement_mode": result.get("enforcement_mode"),
            "warnings":         result.get("warnings", []),
            "audited":          result.get("audited", []),
        })
    except (RuntimeError, ApprovalRequired, ClarificationRequired, PermissionError):
        raise  # block / approval / clarification / permission → propagate to halt or pause the run
    except Exception as _ge:
        log.warning("guard.auto_check_failed", block_id=block_id, block_type=block_type, error=str(_ge))


def _execute_memory(block: dict, state: dict, db, run_id: str, workspace_id: str, playbook_slug: str, credentials: dict | None = None) -> dict:
    from app.runtime.blocks.memory_block import _execute_memory as _memory_impl
    return _memory_impl(block, state, db, run_id, workspace_id, playbook_slug, credentials)


def _execute_memory_inner(block: dict, state: dict, db, run_id: str, workspace_id: str, playbook_slug: str, credentials: dict | None = None) -> dict:
    from app.runtime.blocks.memory_block import _execute_memory_inner as _memory_inner_impl
    return _memory_inner_impl(block, state, db, run_id, workspace_id, playbook_slug)


def _execute_mcp(block: dict, state: dict, cred_store: object, workspace_id: str = "") -> dict:
    from app.runtime.blocks.mcp_block import _execute_mcp as _mcp_impl
    return _mcp_impl(block, state, cred_store, workspace_id=workspace_id)


# MCP tool name → (integration handle, REST action, param rename map)
# param rename map: MCP input key → REST param key (only keys that differ)
_MCP_REST_MAP: dict[str, tuple[str, str, dict]] = {
    "get_issue":          ("github", "fetch_issue",       {"issue_number": "issue_number"}),
    "get_repository":     ("github", "get_repo",          {"owner": "owner", "repo": "repo"}),
    "create_issue":       ("github", "create_issue",      {}),
    "create_pull_request":("github", "open_pull_request", {}),
    "fork_repository":    ("github", "fork_repo",         {}),
    "search_code":        ("github", "search_code",       {}),
    "post_message":       ("slack",  "post_message",      {}),
}


def _mcp_needs_fallback(result: dict) -> bool:
    if result.get("skipped"):
        return True
    err = str(result.get("error", ""))
    return "unknown tool" in err.lower() or "not registered" in err.lower()


def _mcp_rest_fallback(block: dict, state: dict, credentials: dict,
                       allowed_hosts, workspace_id: str) -> dict | None:
    config = (block.get("data") or {}).get("config") or {}
    tool_name = config.get("tool_name", "")
    entry = _MCP_REST_MAP.get(tool_name)
    if not entry:
        return None
    handle, action, _ = entry
    # Build a synthetic tool block for the existing REST dispatcher
    rest_block = {
        **block,
        "data": {
            **block.get("data", {}),
            "type": "tool",
            "integration": handle,
            "action": action,
            "config": {"action": action, "params": config.get("params") or config.get("inputs") or {}},
        },
    }
    try:
        return _execute_tool(rest_block, state, credentials,
                             allowed_hosts=allowed_hosts, workspace_id=workspace_id)
    except Exception as e:
        return {"error": str(e), "fallback": "rest"}


# ── for_each resolution ───────────────────────────────────────────────────────

def _resolve_as_list(expr: str, state: dict) -> list:
    """Resolve a Jinja-style ref or literal expression to a Python list."""
    resolved = _resolve_refs(expr, state)
    if isinstance(resolved, list):
        return resolved
    if isinstance(resolved, str):
        import json as _json
        try:
            parsed = _json.loads(resolved)
            if isinstance(parsed, list):
                return parsed
        except (ValueError, TypeError):
            pass
    return []

