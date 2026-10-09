"""Brain block agentic phase: the bounded multi-turn tool loop.

Extracted from ``brain_block._execute_brain`` (#2400). Same turn order,
budget exits, exception propagation, session close and run-turn telemetry as the
inline loop. Helpers tests patch on ``app.runtime.blocks.brain_block``
arrive through ``BrainRun`` (resolved there at call time).
"""
from __future__ import annotations

import structlog

from app.runtime.blocks.brain_model import (
    BrainRun,
    cached_response,
    call_llm,
    extract_last_json_object as _extract_last_json_object,
    record_turns,
    shadow_account,
)
from app.runtime.blocks.brain_setup import ENVIRONMENT_PREAMBLE, SUFFICIENCY_INSTRUCTION
from app.runtime.blocks.brain_tools import BRAIN_TOOLS, ToolRunner
from app.runtime.llm_client import LLMTextBlock, LLMToolUseBlock

# Same logger name as before the split so worker log routing is unchanged.
log = structlog.get_logger("app.runtime.blocks.brain_block")


def run_agentic(r: BrainRun) -> dict:
    """Bounded agentic loop; returns the block result or raises."""
    block, state, db = r.block, r.state, r.db
    run_id, block_id = r.run_id, r.block_id
    workspace_id, environment_id = r.workspace_id, r.environment_id
    attempt_id, resume_from_turn = r.attempt_id, r.resume_from_turn
    _emit, _write_trace = r.emit, r.write_trace
    _summarise_tool_call = r.summarise_tool_call
    ClarificationRequired = r.clarification_required
    _cache_get, _cache_set = r.cache_get, r.cache_set
    _load_workspace_mcp_tools = r.load_mcp_tools
    session, _close_session, remote_host = r.session, r.close_session, r.remote_host
    llm, provider, model_id = r.llm, r.provider, r.model_id
    routing_reason = r.routing_reason
    pricing_rates, pricing_version = r.pricing_rates, r.pricing_version
    _conduct_proxy_url, _env_vars = r.proxy_url, r.env_vars
    system_prompt, user_message = r.system_prompt, r.user_message
    environment_preamble = ENVIRONMENT_PREAMBLE
    sufficiency_instruction = SUFFICIENCY_INSTRUCTION

    # Bounded agentic loop — deterministic retry boundaries from run state
    messages: list[dict] = [{"role": "user", "content": user_message}]
    turns = 0
    # Per-block override takes priority over run-level budget
    block_max_turns = block.get("data", {}).get("max_turns")
    if block_max_turns is not None:
        max_turns = max(1, int(block_max_turns))
    else:
        max_turns = int(state.get("__max_turns", 20))
        max_turns = max(1, max_turns)
    max_cost_usd = float(state.get("__max_cost_usd", 5.0) or 5.0)
    max_cost_usd = max(0.01, max_cost_usd)

    # Guardrail fields from execution_policy (wired in by the loader)
    _block_data = block.get("data", {})
    _rollback_on_failure = bool(_block_data.get("rollback_on_failure", False))
    _require_tests_pass = bool(_block_data.get("require_tests_pass", False))
    _max_retries = int(_block_data.get("max_retries", 3))
    _block_max_cost = _block_data.get("max_cost_usd")
    if _block_max_cost is not None:
        # Per-block cap overrides run-level cap when it is tighter
        _block_max_cost_f = float(_block_max_cost)
        if _block_max_cost_f < max_cost_usd:
            max_cost_usd = max(0.01, _block_max_cost_f)

    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_read_tokens = 0
    total_cache_write_tokens = 0
    total_cost_usd = 0.0
    full_system = f"{environment_preamble}\n\n{system_prompt}\n\n{sufficiency_instruction}"

    # Feature: allowed_tools — restrict which Brain tools the LLM may call
    _allowed_tools_cfg = (block["data"].get("config") or {}).get("allowed_tools")
    _active_tools = [
        t for t in BRAIN_TOOLS
        if _allowed_tools_cfg is None or t["name"] in _allowed_tools_cfg
    ]

    # Load MCP tools for this workspace and append them to the active tool list.
    # _load_workspace_mcp_tools is fail-open — always returns a list, never raises.
    # Honors block.data["mcp_server_ids"] — the UI toggle at BlockEditor.tsx that
    # lets users pick specific MCP servers instead of all workspace-registered ones.
    if db and workspace_id:
        _mcp_selected = block.get("data", {}).get("mcp_server_ids")
        _mcp_tools = _load_workspace_mcp_tools(
            workspace_id, environment_id, db, selected_ids=_mcp_selected,
        )
        if _mcp_tools:
            _active_tools = _active_tools + _mcp_tools
            log.debug(
                "brain.mcp_tools.loaded",
                count=len(_mcp_tools),
                workspace_id=workspace_id,
                selected_ids=_mcp_selected,
            )

    # Tool dispatch (MCP + built-in, Guard checks, require_tests_pass).
    # The MCP server lookup map is built lazily on first MCP tool call.
    tools = ToolRunner(r, require_tests_pass=_require_tests_pass)

    while turns < max_turns:
        # Skip turns that were already completed before a crash.
        # The LLM cache hit path below reconstructs messages correctly.
        if turns < resume_from_turn:
            _cached = _cache_get(run_id, block_id, turns)
            if _cached is not None:
                from app.runtime.llm_client import LLMResponse as _LLMResponse
                _skip_resp = _LLMResponse.from_cache_dict(_cached)
                messages.extend(llm.make_assistant_turn(_skip_resp))
                _skip_tool_calls = [b for b in _skip_resp.content if isinstance(b, LLMToolUseBlock)]
                if _skip_tool_calls:
                    # Reconstruct tool results from cache so message history is valid
                    _skip_results = [(tc.id, f"[resumed — turn {turns} replayed from cache]") for tc in _skip_tool_calls]
                    messages.extend(llm.make_tool_results_turn(_skip_results))
                turns += 1
                continue
            # No cache for this turn — must re-execute from here
            log.warning("brain.resume_cache_miss", run_id=run_id, block_id=block_id, turn=turns)

        # Trace: user turn
        if db and run_id and block_id:
            turn_msg = messages[-1] if messages else {}
            user_content = turn_msg.get("content", "") if isinstance(turn_msg.get("content"), str) else ""
            _write_trace(db, run_id, block_id, turns + 1, "user",
                         content=user_content[:8000] if user_content else None)

        response = cached_response(r, turns)
        _did_actual_llm_call = False
        if response is None:
            response = call_llm(
                r, turns, agentic=True,
                model=model_id,
                max_tokens=4096,
                system=full_system,
                tools=_active_tools,
                messages=messages,
            )
            _cache_set(run_id, block_id, turns, response.to_cache_dict())
            _did_actual_llm_call = True

        # #2209 Session 6b — workflow shadow accounting. Skip when the
        # adapter routes through Gateway (Session 4 hook already wrote
        # the receipt) and on cache-hit replay (Reviewer #6, #2221).
        if _did_actual_llm_call and not getattr(llm, "routes_through_gateway", False):
            shadow_account(r, response)

        turns += 1
        total_input_tokens       += response.usage.input_tokens
        total_output_tokens      += response.usage.output_tokens
        total_cache_read_tokens  += response.usage.cache_read_tokens
        total_cache_write_tokens += response.usage.cache_write_tokens
        total_cost_usd           += response.cost_usd

        if total_cost_usd >= max_cost_usd:
            cost_usd = round(total_cost_usd, 6)
            files_changed, diff_stat = session.capture_artifacts()
            if db and run_id:
                _emit(db, run_id, block_id, "brain_budget_exhausted", {
                    "reason": "max_cost_reached",
                    "stop_reason": "max_cost_reached",
                    "turns": turns,
                    "max_turns": max_turns,
                    "max_cost_usd": max_cost_usd,
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "cache_read_tokens": total_cache_read_tokens,
                    "cache_write_tokens": total_cache_write_tokens,
                    "cost_usd": cost_usd,
                    "files_changed": files_changed,
                    "diff_stat": diff_stat,
                    "provider": provider,
                    "model": model_id,
                    "pricing_version": pricing_version,
                    "pricing_rates": pricing_rates,
                    "next_action": "Reduce scope or raise max_cost_usd before retrying.",
                })
            if _rollback_on_failure and db and run_id:
                _emit(db, run_id, block_id, "guardrail.rollback_triggered", {
                    "reason": "max_cost_reached",
                    "turns": turns,
                    "cost_usd": cost_usd,
                    "max_cost_usd": max_cost_usd,
                    "note": "rollback_on_failure=true — full git revert is a follow-up action",
                })
            record_turns(db, run_id, turns, True)  # #2401: same as the turn path
            _close_session()
            raise RuntimeError(
                f"Cost budget exhausted: agent reached ${cost_usd:.4f} with cap ${max_cost_usd:.4f} "
                f"after {turns} turns"
            )

        # Collect tool calls from response
        tool_calls  = [b for b in response.content if isinstance(b, LLMToolUseBlock)]
        text_blocks = [b for b in response.content if isinstance(b, LLMTextBlock)]
        final_text  = " ".join(b.text for b in text_blocks)

        # Trace: assistant response
        if db and run_id and block_id:
            _write_trace(db, run_id, block_id, turns, "assistant",
                         content=final_text[:8000] if final_text else None,
                         input_tokens=response.usage.input_tokens,
                         output_tokens=response.usage.output_tokens)

        # First-turn sufficiency check — pause for clarification before any tools are used
        if turns == 1 and final_text.strip().startswith("NEEDS_CLARIFICATION:"):
            _close_session()
            question = final_text.strip()[len("NEEDS_CLARIFICATION:"):].strip()
            raise ClarificationRequired(block_id=block["id"], question=question)

        if response.stop_reason == "end_turn" or not tool_calls:
            cost_usd = round(total_cost_usd, 6)
            files_changed, diff_stat = session.capture_artifacts()
            if db and run_id:
                from app.runtime.sandbox import _modal_available
                if _modal_available():
                    _emit(db, run_id, block_id, "brain_tool_call", {
                        "tool": "modal_lifecycle",
                        "summary": "--- Cleaning Modal Assets ---",
                        "turn": turns,
                    })
            result = {
                "output": final_text,
                "turns": turns,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "cache_read_tokens": total_cache_read_tokens,
                "cache_write_tokens": total_cache_write_tokens,
                "cost_usd": cost_usd,
                "files_changed": files_changed,
                "diff_stat": diff_stat,
                "remote_host_ip": remote_host.get("ip") if remote_host else None,
                "provider": provider,
                "model": model_id,
                "routing_reason": routing_reason,
                "pricing_version": pricing_version,
                "pricing_rates": pricing_rates,
                "upstream_url": _conduct_proxy_url,
                "llm_upstream": _env_vars.get("PROXY_CONFIG_LLM_UPSTREAM") or None,
            }
            # Extract structured values from brain output so keys like
            # pr_url, files, approach etc. are available as direct refs.
            # Merge extracted first so runtime telemetry keys (upstream_url,
            # provider, model, cost_usd …) can never be overwritten by the LLM output.
            _extracted = _extract_last_json_object(result.get("output", ""))
            if _extracted:
                result = {**_extracted, **result}
            record_turns(db, run_id, turns, False)
            _close_session()
            return result

        # Append assistant message (provider-specific format via adapter)
        messages.extend(llm.make_assistant_turn(response))

        # Emit Modal lifecycle event on first tool-dispatching turn
        if turns == 1 and db and run_id:
            from app.runtime.sandbox import _modal_available
            if _modal_available():
                _emit(db, run_id, block_id, "brain_tool_call", {
                    "tool": "modal_lifecycle",
                    "summary": "--- Initializing Modal Assets ---",
                    "turn": 0,
                })

        # Execute tool calls and collect results
        tools.test_ran_this_turn = False  # reset per-turn; set True when a test command runs
        raw_tool_results: list[tuple[str, str]] = []
        for tc in tool_calls:
            # Trace: tool_use
            if db and run_id and block_id:
                _write_trace(db, run_id, block_id, turns, "tool_use",
                             tool_name=tc.name,
                             tool_input=tc.input or None,
                             tool_use_id=tc.id)

            # mark_complete — structured early exit
            if tc.name == "mark_complete":
                # #2401: capture before close — a closed session has no artifacts.
                files_changed, diff_stat = session.capture_artifacts() if session else ([], "")
                _close_session()
                record_turns(db, run_id, turns, False)
                return {
                    "output": tc.input.get("result", ""),
                    "structured_output": tc.input.get("output"),
                    "turns": turns,
                    "stop_reason": "mark_complete",
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "cost_usd": round(total_cost_usd, 6),
                    "files_changed": files_changed,
                    "diff_stat": diff_stat,
                    "provider": provider,
                    "model": model_id,
                }

            result_content, _guard_blocked_mcp = tools.run(tc, turns)
            raw_tool_results.append((tc.id, result_content))
            if _guard_blocked_mcp:
                continue  # blocked MCP call: no tool_result trace / event

            # Trace: tool_result
            if db and run_id and block_id:
                _write_trace(db, run_id, block_id, turns, "tool_result",
                             content=result_content[:8000] if result_content else None,
                             tool_use_id=tc.id)
            if db and run_id:
                _tool_call_evt: dict = {
                    "tool": tc.name,
                    "summary": _summarise_tool_call(tc.name, tc.input),
                    "turn": turns,
                }
                # #2170 PR 2 — join key back to the Gateway audit row.
                # Populated when the workflow routes through a profile;
                # empty for direct-provider paths.
                _corr_id = (response.correlation_ids or {}).get(tc.id)
                if _corr_id:
                    _tool_call_evt["tool_call_correlation_id"] = _corr_id
                _emit(db, run_id, block_id, "brain_tool_call", _tool_call_evt)

        # Append tool results (provider-specific format via adapter)
        messages.extend(llm.make_tool_results_turn(raw_tool_results))

        # Turn-level partial checkpoint — next resume starts from turn+1, not turn 0.
        # Import here (inside the loop body) to avoid circular imports at module load.
        if db and run_id and block_id:
            try:
                from app.runtime.dag_runner import _checkpoint_state as _ckpt
                _ckpt(
                    run_id, state, db=db,
                    block_id=block_id, attempt_id=attempt_id,
                    partial=True, resume_from_turn=turns,
                )
            except Exception as _ck_err:
                log.warning("brain.turn_checkpoint_failed", turn=turns, error=str(_ck_err))

    cost_usd = round(total_cost_usd, 6)
    files_changed, diff_stat = session.capture_artifacts()
    if db and run_id:
        from app.runtime.sandbox import _modal_available
        if _modal_available():
            _emit(db, run_id, block_id, "brain_tool_call", {
                "tool": "modal_lifecycle",
                "summary": "--- Cleaning Modal Assets ---",
                "turn": max_turns,
            })
        _emit(db, run_id, block_id, "brain_budget_exhausted", {
            "reason": "max_turns_reached",
            "stop_reason": "max_turns_reached",
            "turns": max_turns,
            "max_turns": max_turns,
            "max_cost_usd": max_cost_usd,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "cache_read_tokens": total_cache_read_tokens,
            "cache_write_tokens": total_cache_write_tokens,
            "cost_usd": cost_usd,
            "files_changed": files_changed,
            "diff_stat": diff_stat,
            "provider": provider,
            "model": model_id,
            "pricing_version": pricing_version,
            "pricing_rates": pricing_rates,
            "next_action": "Reduce scope or increase max_turns before retrying.",
        })
    if _rollback_on_failure and db and run_id:
        _emit(db, run_id, block_id, "guardrail.rollback_triggered", {
            "reason": "max_turns_reached",
            "turns": max_turns,
            "cost_usd": cost_usd,
            "note": "rollback_on_failure=true — full git revert is a follow-up action",
        })
    record_turns(db, run_id, turns, True)  # #2401: turns used, not the cap
    _close_session()
    raise RuntimeError(
        f"Turn budget exhausted: agent did not reach end_turn after {max_turns} turns "
        f"({total_input_tokens} input / {total_output_tokens} output tokens, ${cost_usd:.4f})"
    )
