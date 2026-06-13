"""
Brain block executor.

Handles both single-call (non-agentic) and bounded agentic loop modes.
Extracted from app.runtime.executor.
"""
from __future__ import annotations

import json
from typing import Any

import structlog

from app.core.config import settings
from app.runtime.llm_client import (
    AnthropicClient,
    LLMTextBlock,
    LLMToolUseBlock,
    OpenAIClient,
    PerplexityClient,
)
from app.runtime.model_router import resolve as _router_resolve
from app.runtime.pricing import freeze_pricing_snapshot, get_model_rates

log = structlog.get_logger(__name__)

# Re-imported here so block files can be imported standalone; also re-exported for
# any caller that used to import BRAIN_TOOLS from executor.
BRAIN_TOOLS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file at the given path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path to read"}
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file at the given path. Creates parent directories if needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write to the file"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_shell",
        "description": "Execute a shell command and return stdout/stderr. Use for tests, builds, git commands.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "working_dir": {"type": "string", "description": "Working directory (optional)"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "search_code",
        "description": "Search for a pattern in files using grep. Returns matching lines with file paths.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "Directory or file to search in", "default": "."},
                "file_glob": {"type": "string", "description": "File glob to filter (e.g. '*.py')", "default": "*"},
            },
            "required": ["pattern"],
        },
    },
]


def _extract_last_json_object(text: str) -> dict | None:
    """
    Find the last well-formed JSON object in text.
    Handles three cases: compact JSON on last line, whole output is JSON,
    and prose followed by a multi-line JSON block.
    """
    text = text.strip()
    # 1. Last line (compact single-line JSON)
    last_line = text.rsplit("\n", 1)[-1].strip()
    if last_line.startswith("{") and last_line.endswith("}"):
        try:
            obj = json.loads(last_line)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    # 2. Whole output is JSON (multi-line, no prose prefix)
    if text.startswith("{") and text.endswith("}"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    # 3. Prose + trailing JSON block — brace-match from the last closing brace
    last_close = text.rfind("}")
    if last_close != -1:
        depth = 0
        for i in range(last_close, -1, -1):
            if text[i] == "}":
                depth += 1
            elif text[i] == "{":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[i : last_close + 1])
                        if isinstance(obj, dict):
                            return obj
                    except Exception:
                        pass
                    break
    return None


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
) -> dict:
    # Import helpers from executor to avoid circular imports at module load time.
    from app.runtime.executor import (
        _emit,
        _resolve_remote_host,
        _resolve_refs,
        _summarise_tool_call,
        _write_trace,
        ClarificationRequired,
    )

    if state.get("__dry_run"):
        return {
            "dry_run": True,
            "note": "Dry run — Brain block would invoke Claude AI with the workflow context",
            "description": block["data"].get("description", ""),
            "is_agentic": block["data"].get("isAgentic", False),
            "remote_host": bool((block.get("data", {}).get("config") or {}).get("remote_host")),
        }

    artifact = compiled_artifacts.get(block["id"], {})
    system_prompt = artifact.get("system_prompt", block["data"].get("description", ""))

    # prompt_file overrides inline description when present
    prompt_file = (block["data"].get("config") or {}).get("prompt_file") or block["data"].get("prompt_file")
    if prompt_file:
        import pathlib
        base = pathlib.Path(__file__).parent.parent.parent.parent  # repo root
        candidate = (base / prompt_file).resolve()
        try:
            candidate.relative_to(base.resolve())  # prevent path traversal
            system_prompt = candidate.read_text(encoding="utf-8")
        except (ValueError, FileNotFoundError, OSError) as exc:
            log.warning("brain.prompt_file_unreadable", path=str(prompt_file), error=str(exc))

    custom = block["data"].get("custom_instructions", "") or ""
    if custom.strip():
        system_prompt = f"{system_prompt}\n\nAdditional instructions:\n{custom.strip()}"
    is_agentic = block["data"].get("isAgentic", False)

    # Model selection via router
    routing_pref = block["data"].get("routingPreference") or "balanced"
    explicit_model = block["data"].get("model") or None
    explicit_provider = block["data"].get("provider") or None
    provider, model_id, routing_reason = _router_resolve(playbook_slug, routing_pref, explicit_model, explicit_provider)
    log.debug("brain.model_selected", block_id=block["id"], provider=provider, model=model_id, reason=routing_reason)

    # Resolve remote host (SSH) or runs_on provider (E2B / Modal / local).
    remote_host = _resolve_remote_host(block, state, credentials or {})
    runs_on: dict | None = block.get("data", {}).get("runs_on") or None

    if injected_session is not None:
        session = injected_session
    else:
        from app.runtime.sandbox_session import create_session as _create_session
        session = _create_session(remote_host, credentials, runs_on=runs_on)
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

    context = json.dumps({k: v for k, v in state.items() if not k.startswith("__")}, default=str)[:4000]

    # Credential placeholder pattern: model and DB see placeholder tokens, never raw secrets.
    # Real values live only in _cred_real and are swapped into subprocess env at dispatch time.
    cred_env: dict[str, str] = {}   # placeholder values — safe to log / send to LLM
    _cred_real: dict[str, str] = {}  # placeholder → real value — never leaves this function
    cred_names: list[str] = []
    _ENV_NAME_MAP = {
        ("git", "token"): "GIT_TOKEN", ("git", "provider"): "GIT_PROVIDER",
        ("github", "token"): "GIT_TOKEN", ("github", "api_key"): "GIT_TOKEN",
        ("slack", "token"): "SLACK_BOT_TOKEN",
        ("slack", "signing_secret"): "SLACK_SIGNING_SECRET",
        ("linear", "api_key"): "LINEAR_API_KEY",
        ("digitalocean", "token"): "DIGITALOCEAN_TOKEN",
        ("vercel", "token"): "VERCEL_TOKEN",
        ("anthropic", "api_key"): "ANTHROPIC_API_KEY",
        ("modal", "token_id"): "MODAL_TOKEN_ID",
        ("modal", "token_secret"): "MODAL_TOKEN_SECRET",
        ("email", "resend_api_key"): "RESEND_API_KEY",
    }
    for handle, creds in (credentials or {}).items():
        if isinstance(creds, dict):
            for field, val in creds.items():
                if val and isinstance(val, str):
                    env_name = _ENV_NAME_MAP.get((handle, field), f"{handle.upper()}_{field.upper()}")
                    placeholder = f"__CREDENTIAL_{env_name}__"
                    cred_env[env_name] = placeholder
                    _cred_real[placeholder] = val
                    cred_names.append(env_name)
    cred_section = (
        "\n\nCredentials are pre-exported into every run_shell call — use them directly without any setup:\n"
        + "\n".join(f"  ${n}" for n in cred_names)
        + "\nDO NOT check if these vars exist. DO NOT try to read them from files. They are already in the shell environment."
    ) if cred_names else ""

    user_message = f"Workflow context so far:\n{context}{cred_section}\n\nExecute your task."

    # Clarification resume: if a prior run paused this block for clarification,
    # append the answer so the LLM has full context on the second attempt.
    clarification_key = f"__clarification_{block['id']}"
    if clarification_key in state:
        user_message = f"{user_message}\n\nClarification from user: {state[clarification_key]}"

    sufficiency_instruction = (
        "IMPORTANT: Before doing any work, assess whether you have enough information "
        "to complete this task. If the description is vague, missing critical details, "
        "or you cannot determine what success looks like — respond immediately with:\n"
        "NEEDS_CLARIFICATION: <concise explanation of what is missing>\n"
        "Do not attempt partial work or use any tools if the task is unclear."
    )

    environment_preamble = (
        "EXECUTION ENVIRONMENT:\n"
        "You are running inside a PERSISTENT session — files and directories you create in one\n"
        "run_shell call ARE available in subsequent calls within this task. Use multiple focused\n"
        "tool calls rather than one giant shell script when it makes the work clearer.\n"
        "Pre-installed: git, python3, pip3, curl, wget, node, npm, unzip.\n"
        "\n"
        "DO NOT waste turns on diagnostics:\n"
        "- Do NOT run: which git, apt-get install anything, find / -name git\n"
        "- Do NOT check if env vars are set (python3 -c 'import os; print(os.environ...)') — they are set\n"
        "- Do NOT run echo $GIT_TOKEN or similar — just use it\n"
        "\n"
        "STANDARD REPO SETUP — recommended approach across multiple calls:\n"
        "  Turn 1: git clone https://$GIT_TOKEN@github.com/<owner>/<repo>.git /tmp/repo\n"
        "  Turn 2: cd /tmp/repo && git config user.email 'bot@conductai.ai' && git checkout -b fix/<slug>\n"
        "  Turn 3+: read/edit files, git add, git commit\n"
        "  Final: git push && open PR via curl or gh CLI\n"
        "\n"
        "Fallback (if git clone fails): use python3 urllib to GET/PATCH/PUT via GitHub API.\n"
        "Do NOT switch between approaches mid-task."
    )

    # BYO key: workspace credential (handle or flat env_var) → platform default
    _env_vars = (credentials or {}).get("env_vars") or {}
    _anthropic_key = (
        (credentials or {}).get("anthropic", {}).get("api_key")
        or _env_vars.get("anthropic_api_key")
        or _env_vars.get("ANTHROPIC_API_KEY")
        or settings.anthropic_api_key
    )
    _openai_key = (
        (credentials or {}).get("openai", {}).get("api_key")
        or _env_vars.get("openai_api_key")
        or _env_vars.get("OPENAI_API_KEY")
        or settings.openai_api_key
    )
    _perplexity_key = (
        (credentials or {}).get("perplexity", {}).get("api_key")
        or _env_vars.get("perplexity_api_key")
        or _env_vars.get("PERPLEXITY_API_KEY")
    )

    pricing_snapshot = freeze_pricing_snapshot()

    # Provider fallback keeps existing Anthropic behavior if OpenAI is selected
    # but no key is configured for this workspace/run.
    if provider == "perplexity" and _perplexity_key:
        llm = PerplexityClient(api_key=_perplexity_key, pricing_snapshot=pricing_snapshot)
    elif provider == "openai" and _openai_key:
        llm = OpenAIClient(api_key=_openai_key, pricing_snapshot=pricing_snapshot)
    else:
        if provider == "openai" and not _openai_key:
            log.warning("brain.provider_fallback", reason="missing_openai_key", selected_provider=provider, fallback_provider="anthropic")
            provider, model_id, fallback_reason = _router_resolve(playbook_slug, routing_pref, None, "anthropic")
            routing_reason = f"{routing_reason}; fallback: {fallback_reason}"
        elif provider == "perplexity" and not _perplexity_key:
            log.warning("brain.provider_fallback", reason="missing_perplexity_key", selected_provider=provider, fallback_provider="anthropic")
            provider, model_id, fallback_reason = _router_resolve(playbook_slug, routing_pref, None, "anthropic")
            routing_reason = f"{routing_reason}; fallback: {fallback_reason}"
        llm = AnthropicClient(api_key=_anthropic_key, pricing_snapshot=pricing_snapshot)

    pricing_rates, pricing_version = get_model_rates(provider, model_id, pricing_snapshot)

    def _record_turns(db, run_id: str | None, actual: int, exhausted: bool) -> None:
        """Persist actual_turns + budget_exhausted on the Run row for future estimation."""
        if not db or not run_id:
            return
        try:
            from app.models.run import Run as _Run
            db.query(_Run).filter(_Run.id == run_id).update(
                {"actual_turns": actual, "budget_exhausted": exhausted},
                synchronize_session=False,
            )
            db.commit()
        except Exception:
            pass  # never block the run on telemetry writes

    if is_agentic:
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

        while turns < max_turns:
            # Trace: user turn
            if db and run_id and block_id:
                turn_msg = messages[-1] if messages else {}
                user_content = turn_msg.get("content", "") if isinstance(turn_msg.get("content"), str) else ""
                _write_trace(db, run_id, block_id, turns + 1, "user",
                             content=user_content[:8000] if user_content else None)

            response = llm.create(
                model=model_id,
                max_tokens=4096,
                system=full_system,
                tools=_active_tools,
                messages=messages,
                cache_system=True,
            )
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
                }
                # Extract structured values from brain output so keys like
                # pr_url, files, approach etc. are available as direct refs.
                _extracted = _extract_last_json_object(result.get("output", ""))
                if _extracted:
                    result.update(_extracted)
                _record_turns(db, run_id, turns, False)
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
            raw_tool_results: list[tuple[str, str]] = []
            for tc in tool_calls:
                # Trace: tool_use
                if db and run_id and block_id:
                    _write_trace(db, run_id, block_id, turns, "tool_use",
                                 tool_name=tc.name,
                                 tool_input=tc.input or None,
                                 tool_use_id=tc.id)

                try:
                    result_content = _dispatch_with_creds(tc.name, tc.input)
                except RuntimeError as sandbox_err:
                    if db and run_id:
                        _emit(db, run_id, block_id, "brain_tool_call", {
                            "tool": "modal_error",
                            "summary": str(sandbox_err),
                            "turn": turns,
                        })
                    raise
                raw_tool_results.append((tc.id, result_content))

                # Trace: tool_result
                if db and run_id and block_id:
                    _write_trace(db, run_id, block_id, turns, "tool_result",
                                 content=result_content[:8000] if result_content else None,
                                 tool_use_id=tc.id)
                if db and run_id:
                    _emit(db, run_id, block_id, "brain_tool_call", {
                        "tool": tc.name,
                        "summary": _summarise_tool_call(tc.name, tc.input),
                        "turn": turns,
                    })

            # Append tool results (provider-specific format via adapter)
            messages.extend(llm.make_tool_results_turn(raw_tool_results))

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
        _record_turns(db, run_id, max_turns, True)
        _close_session()
        raise RuntimeError(
            f"Turn budget exhausted: agent did not reach end_turn after {max_turns} turns "
            f"({total_input_tokens} input / {total_output_tokens} output tokens, ${cost_usd:.4f})"
        )

    else:
        # Single call (no tools)
        response = llm.create(
            model=model_id,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            cache_system=True,
        )
        text = next((b.text for b in response.content if isinstance(b, LLMTextBlock)), "")
        if db and run_id and block_id:
            _emit(db, run_id, block_id, "brain_tool_call", {
                "turn": 1,
                "tool": "single_call",
                "summary": text[:300],
                "input": user_message[:600],
                "output": text,
                "model": model_id,
                "provider": provider,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            })
        result = {
            "output": text,
            "turns": 1,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cost_usd": response.cost_usd,
            "provider": provider,
            "model": model_id,
            "routing_reason": routing_reason,
            "pricing_version": pricing_version,
            "pricing_rates": pricing_rates,
        }
        _extracted = _extract_last_json_object(result.get("output", ""))
        if _extracted:
            result.update(_extracted)
        _close_session()
        return result
