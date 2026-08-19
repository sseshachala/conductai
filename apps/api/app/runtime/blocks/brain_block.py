"""
Brain block executor.

Handles both single-call (non-agentic) and bounded agentic loop modes.
Extracted from app.runtime.executor.
"""
from __future__ import annotations

import json
import os
from typing import Any

import structlog

from app.core.config import settings
from app.runtime.llm_client import (
    AnthropicClient,
    LLMTextBlock,
    LLMToolUseBlock,
    LLMUpstreamError,
    OpenAIClient,
    PerplexityClient,
)
from app.runtime.model_router import resolve as _router_resolve
from app.runtime.pricing import freeze_pricing_snapshot, get_model_rates

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
    {
        "name": "mark_complete",
        "description": (
            "Signal that the task is complete and return a structured result. "
            "Call this instead of stop_reason end_turn when you have a definitive outcome. "
            "Always pass a 'result' key summarising what was accomplished."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Summary of what was accomplished"},
                "output": {"type": "object", "description": "Optional structured output data"},
            },
            "required": ["result"],
        },
    },
]


def _classify_tool_error(result: str) -> str:
    """Prefix tool results with a structured error category for LLM signal."""
    if result.startswith("Refused:"):
        return f"[permission_denied] {result}"
    if "timed out" in result.lower() or "timeout" in result.lower():
        return f"[timeout] {result}"
    if result.startswith("Error:") or result.startswith("error:"):
        return f"[tool_error] {result}"
    return result


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
            tools.append({
                "name": f"{server.name}::{tool_name}",
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
    # Resolve {{block.field}} refs in system_prompt so descriptions can reference
    # prior block outputs (e.g. {{file_findings.posted}} in comment_pr). Same __-prefix
    # filter as the prompt path (line 458) so runtime secrets never leak into the LLM.
    if system_prompt and "{{" in system_prompt:
        _sp_safe_state = {k: v for k, v in state.items() if not k.startswith("__")}
        system_prompt = _resolve_refs(system_prompt, _sp_safe_state)
    is_agentic = block["data"].get("isAgentic", False)

    # Model selection via router
    routing_pref = block["data"].get("routingPreference") or "balanced"
    explicit_model = block["data"].get("model") or None
    explicit_provider = block["data"].get("provider") or None
    provider, model_id, routing_reason = _router_resolve(playbook_slug, routing_pref, explicit_model, explicit_provider)
    log.debug("brain.model_selected", block_id=block["id"], provider=provider, model=model_id, reason=routing_reason)

    # Fetch credentials from broker for session creation (SSH key, sandbox API keys).
    # This is the only in-function credential fetch; LLM keys are fetched separately below.
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

    _ctx_raw = json.dumps({k: v for k, v in state.items() if not k.startswith("__")}, default=str)[:4000]
    if state.get("__guard_enabled"):
        from app.core.pii import redact_pii
        _ctx_raw = redact_pii(_ctx_raw)
    context = _ctx_raw

    # Credential placeholder pattern: model and DB see placeholder tokens, never raw secrets.
    # Real values live only in _cred_real and are swapped into subprocess env at dispatch time.
    # Credentials are fetched from the broker (already done above via _session_creds).
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
    for handle, creds in _session_creds.items():
        if isinstance(creds, dict):
            for field, val in creds.items():
                if val and isinstance(val, str):
                    env_name = _ENV_NAME_MAP.get((handle, field), f"{handle.upper()}_{field.upper()}")
                    placeholder = f"__CREDENTIAL_{env_name}__"
                    cred_env[env_name] = placeholder
                    _cred_real[placeholder] = val
                    cred_names.append(env_name)

    # Run-scoped env vars (CONDUCT_RUN_TOKEN, CONDUCT_RUN_ID, CONDUCT_API_URL)
    # need to reach run_shell subprocess so agentic blocks can call the Conduct API.
    # Source is RunContext state keys (written by executor via apply_to_state), NOT
    # the credential broker — env_vars mutations on the local credentials object
    # never round-trip through the broker's HTTP fetch.
    _run_token_from_state = state.get("__conduct_run_token__", "")
    _api_url_from_state   = state.get("__cred_api_url__", "")
    _conduct_env: dict[str, str] = {}
    if _run_token_from_state:
        _conduct_env["CONDUCT_RUN_TOKEN"] = _run_token_from_state
    if run_id:
        _conduct_env["CONDUCT_RUN_ID"] = str(run_id)
    if _api_url_from_state:
        _conduct_env["CONDUCT_API_URL"] = _api_url_from_state
    for _k, _v in _conduct_env.items():
        placeholder = f"__CREDENTIAL_{_k}__"
        cred_env[_k] = placeholder
        _cred_real[placeholder] = _v
        cred_names.append(_k)

    cred_section = (
        "\n\nCredentials are pre-exported into every run_shell call — use them directly without any setup:\n"
        + "\n".join(f"  ${n}" for n in cred_names)
        + "\nDO NOT check if these vars exist. DO NOT try to read them from files. They are already in the shell environment."
    ) if cred_names else ""

    # Inject broker token into subprocess env only — NOT into cred_env (LLM prompt context)
    _cred_token = state.get("__cred_token__")
    _cred_api_url = state.get("__cred_api_url__")
    if _cred_token:
        _cred_real["CONDUCT_CRED_TOKEN"] = _cred_token
    if _cred_api_url:
        _cred_real["CONDUCT_API_URL"] = _cred_api_url

    # Honor block.data["prompt"] as the user-message template when present.
    # Rendered with {{block.field}} refs from state; falls back to a JSON context dump
    # so playbooks written before prompt: was supported keep working unchanged.
    # See project_session_july27_runtime_bugs.md — prompt: was half-shipped for 7 weeks.
    _MAX_PROMPT_CHARS = 32000  # ~8k tokens — bounded blast radius on runaway blobs
    _prompt_template = (block["data"].get("prompt") or "").strip()
    if _prompt_template:
        # __-prefixed state keys are private runtime plumbing (tokens, URLs,
        # config). Filter them out so a template like `{{__conduct_run_token__}}`
        # can never resolve to a real secret in the LLM prompt.
        _safe_state = {k: v for k, v in state.items() if not k.startswith("__")}
        _rendered_prompt = _resolve_refs(_prompt_template, _safe_state)
        # PII redaction on the same trigger the fallback path uses.
        if state.get("__guard_enabled"):
            from app.core.pii import redact_pii
            _rendered_prompt = redact_pii(_rendered_prompt)
        # Cap size — a `{{huge.blob}}` ref shouldn't blow the token budget.
        if len(_rendered_prompt) > _MAX_PROMPT_CHARS:
            _rendered_prompt = (
                _rendered_prompt[:_MAX_PROMPT_CHARS]
                + f"\n\n[truncated at {_MAX_PROMPT_CHARS} chars]"
            )
        user_message = f"{_rendered_prompt}{cred_section}"
    else:
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

    # BYO key: fetch per-provider credentials from broker → platform default fallback
    def _clean(v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v

    _env_vars = _session_creds.get("env_vars") or {}
    _anthropic_creds = _session_creds.get("anthropic") or {}
    _openai_creds = _session_creds.get("openai") or {}
    _perplexity_creds = _session_creds.get("perplexity") or {}

    _anthropic_key = _clean(
        _anthropic_creds.get("api_key")
        or _env_vars.get("anthropic_api_key")
        or _env_vars.get("ANTHROPIC_API_KEY")
        or settings.anthropic_api_key
    )
    _openai_key = _clean(
        _openai_creds.get("api_key")
        or _env_vars.get("openai_api_key")
        or _env_vars.get("OPENAI_API_KEY")
        or settings.openai_api_key
    )
    _perplexity_key = _clean(
        _perplexity_creds.get("api_key")
        or _env_vars.get("perplexity_api_key")
        or _env_vars.get("PERPLEXITY_API_KEY")
    )

    pricing_snapshot = freeze_pricing_snapshot()

    from app.runtime.provider_keys import MissingProviderKey
    _provider_keys = {"anthropic": _anthropic_key, "openai": _openai_key, "perplexity": _perplexity_key}
    if not _provider_keys[provider]:
        raise MissingProviderKey(provider, model_id)

    # Guard proxy URL is a platform constant — same for every workspace.
    # brain_block always routes through it; the proxy handles BYO forwarding internally.
    _conduct_proxy_url: str = settings.conduct_proxy_url.rstrip("/")

    # When routing through Portkey/Helicone: gateway key goes in x-portkey-api-key header,
    # vendor key stays in api_key (forwarded to Anthropic by the gateway).
    _effective_key = _provider_keys[provider]

    # Guard proxy is always first. brain_block never routes to BYO gateway directly.
    # The proxy reads CONDUCT_LLM_UPSTREAM from proxy_config and handles BYO forwarding.
    if _conduct_proxy_url:
        _effective_base_url = f"{_conduct_proxy_url}/{provider}"
    else:
        _effective_base_url = None

    _extra_headers: dict = {}

    # Pass run context so proxy audit rows link back to the run + workflow.
    if run_id:
        _extra_headers["x-conductai-run-id"] = str(run_id)
    if workflow_name or playbook_slug:
        _extra_headers["x-conductai-workflow"] = workflow_name or playbook_slug or ""
    if workflow_id:
        _extra_headers["x-conductai-workflow-id"] = str(workflow_id)
    # Authenticate with the Conduct proxy.
    # Prefer ephemeral run token (minted per-run), fall back to long-lived agent identity token.
    if _conduct_proxy_url and workspace_id:
        _agent_token = (
            _env_vars.get("CONDUCT_RUN_TOKEN")
            or state.get("__conduct_run_token__", "")
            or _env_vars.get("CONDUCT_AGENT_TOKEN", "")
        )
        if _agent_token:
            _extra_headers["x-conductai-internal"] = _agent_token
        _extra_headers["x-conductai-workspace-id"] = str(workspace_id)
        if environment_id:
            _extra_headers["x-conductai-environment-id"] = str(environment_id)
        if user_email:
            _extra_headers["x-conductai-user-email"] = user_email

    client_for = {"anthropic": AnthropicClient, "openai": OpenAIClient, "perplexity": PerplexityClient}
    _client_kwargs: dict = {
        "api_key": _effective_key,
        "pricing_snapshot": pricing_snapshot,
        "base_url": _effective_base_url,
    }
    if _extra_headers:
        _client_kwargs["default_headers"] = _extra_headers
    llm = client_for[provider](**_client_kwargs)

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
        # Track whether a test run was observed in the current turn
        _test_ran_this_turn: bool = False

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

        # Build a lookup: {server_name -> McpServer row} for MCP dispatch during tool calls.
        # Populated lazily on first MCP tool call.
        _mcp_server_cache: dict | None = None

        def _get_mcp_server_map():
            nonlocal _mcp_server_cache
            if _mcp_server_cache is not None:
                return _mcp_server_cache
            _mcp_server_cache = {}
            if not db or not workspace_id:
                return _mcp_server_cache
            try:
                from app.models.mcp_server import McpServer as _McpServer
                servers = db.query(_McpServer).filter(
                    _McpServer.workspace_id == workspace_id
                ).all()
                for s in servers:
                    _mcp_server_cache[s.name] = s
            except Exception as exc:
                log.warning("brain.mcp_dispatch.map_failed", error=str(exc))
            return _mcp_server_cache

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

            _cached = _cache_get(run_id, block_id, turns)
            if _cached is not None:
                from app.runtime.llm_client import LLMResponse as _LLMResponse
                response = _LLMResponse.from_cache_dict(_cached)
                response.cost_usd = 0.0  # ponytail: no charge on replay
                log.debug("brain.llm_cache_hit", run_id=run_id, block_id=block_id, turn=turns)
            else:
                try:
                    # Stable idempotency key across our retry attempts within
                    # this turn — lets OpenAI dedupe if a request was
                    # intercepted mid-flight. Include __for_each_index so
                    # iterations of the same block inside for_each don't
                    # collide on the provider's dedup window.
                    _fe_idx = state.get("__for_each_index")
                    _idem_key = (
                        f"conduct-{run_id}-{block_id}-{turns}"
                        + (f"-fe{_fe_idx}" if _fe_idx is not None else "")
                    ) if run_id and block_id else None
                    # Emit llm_upstream_retry on each retry attempt so ops
                    # can spot infra degradation. Fires only when retry
                    # occurs; silent on happy path.
                    def _on_retry_agentic(info: dict) -> None:
                        if db and run_id:
                            _emit(db, run_id, block_id, "llm_upstream_retry", {
                                **info, "turn": turns,
                                "block_attempt": state.get("__block_attempt", 1),
                            })
                    # If a future dag_runner block-retry wraps this call, it
                    # sets state["__block_attempt"] to N. Passing outer_attempt
                    # caps internal retries at 1 when N>1 so 3×3=9 stacked
                    # attempts never happen. Silent no-op today (nothing sets
                    # __block_attempt).
                    _outer_attempt = int(state.get("__block_attempt", 1))
                    response = llm.create(
                        model=model_id,
                        max_tokens=4096,
                        system=full_system,
                        tools=_active_tools,
                        messages=messages,
                        cache_system=True,
                        idempotency_key=_idem_key,
                        on_retry=_on_retry_agentic,
                        outer_attempt=_outer_attempt,
                    )
                except LLMUpstreamError as _up_err:
                    # CF/Render/WAF intercepted. Emit a structured event with
                    # cf-ray + render request ID BEFORE re-raising — the raise
                    # goes into block_failed via str(exc) which is short and clean.
                    # is_final marks this as the terminal adapter failure; if a
                    # future dag_runner block-retry wraps this call and later
                    # succeeds, consumers can filter for is_final events only.
                    if db and run_id:
                        _emit(db, run_id, block_id, "llm_upstream_blocked", {
                            "provider": _up_err.provider,
                            "status": _up_err.status,
                            "content_type": _up_err.content_type,
                            "attempts": _up_err.attempts,
                            "cf_ray": _up_err.cf_ray,
                            "render_request_id": _up_err.request_id,
                            "body_snippet": _up_err.body_snippet,
                            "turn": turns,
                            "base_url": _effective_base_url,
                            "is_final": True,
                            "block_attempt": state.get("__block_attempt", 1),
                        })
                    log.error("brain.llm_upstream_blocked",
                              provider=_up_err.provider, status=_up_err.status,
                              cf_ray=_up_err.cf_ray, render_req=_up_err.request_id,
                              attempts=_up_err.attempts,
                              run_id=run_id, block_id=block_id)
                    raise
                except Exception as _llm_err:
                    _cause = getattr(_llm_err, "__cause__", None) or getattr(_llm_err, "__context__", None)
                    log.error("brain.llm_call_failed",
                              error=str(_llm_err), cause=str(_cause),
                              base_url=_effective_base_url, turn=turns,
                              run_id=run_id, block_id=block_id)
                    raise
                _cache_set(run_id, block_id, turns, response.to_cache_dict())
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
                    "upstream_url": _effective_base_url,
                    "llm_upstream": _env_vars.get("PROXY_CONFIG_LLM_UPSTREAM") or None,
                }
                # Extract structured values from brain output so keys like
                # pr_url, files, approach etc. are available as direct refs.
                # Merge extracted first so runtime telemetry keys (upstream_url,
                # provider, model, cost_usd …) can never be overwritten by the LLM output.
                _extracted = _extract_last_json_object(result.get("output", ""))
                if _extracted:
                    result = {**_extracted, **result}
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
            _test_ran_this_turn = False  # reset per-turn; set True when a test command runs
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
                    _close_session()
                    _record_turns(db, run_id, turns, False)
                    files_changed, diff_stat = session.capture_artifacts() if session else ([], "")
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

                try:
                    if "::" in tc.name:
                        # MCP tool dispatch — server_name::tool_name
                        _mcp_server_name, _mcp_tool_name = tc.name.split("::", 1)

                        # Guard check before every MCP tool call
                        if state.get("__guard_enabled") and db and workspace_id:
                            try:
                                from app.modules.guard.routers.mcp import _match_policy, _get_rules
                                import uuid as _uuid
                                _guard_rules = _get_rules(db, _uuid.UUID(workspace_id))

                                # Evaluate match_mcp_server and match_tool against MCP calls
                                _mcp_inp_text = json.dumps(tc.input)
                                _guard_hit = None
                                _ACTION_PRIORITY = {"block": 0, "approval": 1, "warn": 2, "audit": 3}
                                _best_priority = 999
                                import re as _re
                                for _rule in _guard_rules:
                                    # match_mcp_server — matches against server name prefix
                                    _ms = (_rule.get("match_mcp_server") or "").strip()
                                    if _ms and _ms != "*":
                                        if not _re.fullmatch(_ms, _mcp_server_name, _re.IGNORECASE):
                                            continue
                                    # match_tool — matches against the MCP tool name (after ::)
                                    _mt = (_rule.get("match_tool") or "").strip()
                                    if _mt and _mt != "*":
                                        _mt_allowed = [t.strip() for t in _mt.split(",")]
                                        if _mcp_tool_name.lower() not in _mt_allowed:
                                            # Also try regex for patterns like delete_.*
                                            try:
                                                if not any(_re.fullmatch(p, _mcp_tool_name, _re.IGNORECASE) for p in _mt_allowed):
                                                    continue
                                            except _re.error:
                                                continue
                                    # match_pattern — against serialised input
                                    _mp = _rule.get("match_pattern")
                                    if _mp:
                                        try:
                                            if not _re.search(_mp, _mcp_inp_text, _re.IGNORECASE):
                                                continue
                                        except _re.error:
                                            continue
                                    _p = _ACTION_PRIORITY.get(_rule.get("action", "audit"), 3)
                                    if _p < _best_priority:
                                        _best_priority = _p
                                        _guard_hit = _rule

                                if _guard_hit:
                                    _guard_action = _guard_hit.get("action", "audit")
                                    _guard_msg = _guard_hit.get("message", "")
                                    if db and run_id:
                                        _emit(db, run_id, block_id, "brain_tool_call", {
                                            "tool": tc.name,
                                            "guard_action": _guard_action,
                                            "guard_rule": _guard_hit.get("id"),
                                            "guard_message": _guard_msg,
                                            "turn": turns,
                                        })
                                    if _guard_action == "block":
                                        raw_tool_results.append((tc.id, f"[guard_blocked] {_guard_msg}"))
                                        continue
                            except Exception as _guard_exc:
                                log.warning("brain.mcp_dispatch.guard_failed", error=str(_guard_exc))

                        _mcp_map = _get_mcp_server_map()
                        _mcp_server_row = _mcp_map.get(_mcp_server_name)
                        if not _mcp_server_row:
                            result_content = f"[mcp_error] MCP server '{_mcp_server_name}' not found in workspace"
                        else:
                            try:
                                from app.core.crypto import decrypt as _decrypt
                                from app.runtime.integrations import mcp_client as _mcp_client
                                _mcp_token = (
                                    _decrypt(_mcp_server_row.encrypted_auth).get("token")
                                    if _mcp_server_row.encrypted_auth else None
                                )
                                _mcp_result = _mcp_client.call_tool(
                                    _mcp_server_row.url,
                                    _mcp_token,
                                    _mcp_tool_name,
                                    tc.input or {},
                                    transport=_mcp_server_row.transport or "auto",
                                )
                                if isinstance(_mcp_result, dict):
                                    result_content = json.dumps(_mcp_result)
                                else:
                                    result_content = str(_mcp_result)
                            except Exception as _mcp_exc:
                                result_content = f"[mcp_error] {_mcp_exc!s:.500}"
                        result_content = _classify_tool_error(result_content)
                    else:
                        # Guard check for non-MCP tools (run_shell, edit, write, etc).
                        # The MCP branch above already guards MCP tool calls, but shell
                        # commands and file edits were bypassing every hook-surface rule
                        # entirely — the audit trail never saw them and no rule could
                        # block, even when match_tool included "shell" or "workflow".
                        # This mirrors the MCP guard block against the same rule set.
                        _guard_blocked_non_mcp = False
                        if state.get("__guard_enabled") and db and workspace_id:
                            try:
                                from app.modules.guard.routers.mcp import _get_rules
                                import uuid as _uuid
                                import re as _re
                                _guard_rules = _get_rules(db, _uuid.UUID(workspace_id))
                                _tool_input_text = json.dumps(tc.input or {})
                                _ACTION_PRIORITY = {"block": 0, "approval": 1, "warn": 2, "audit": 3}
                                _best_priority = 999
                                _guard_hit = None
                                # Only fire rules that ACTUALLY apply to this tool.
                                # "workflow" is a scope for workflow-level enforcement,
                                # not a tool alias — treating it as a wildcard here
                                # made every conduct-base workflow rule fire on every
                                # brain tool_use, blocking all read_file / write_file /
                                # search_code / run_shell calls.
                                _TOOL_ALIASES = {
                                    "run_shell": {"shell", "run_shell"},
                                    "read_file": {"filesystem-read", "read_file", "read"},
                                    "write_file": {"filesystem-write", "write_file", "write"},
                                    "edit": {"filesystem-write", "edit"},
                                    "search_code": {"filesystem-read", "search_code", "grep"},
                                }
                                for _rule in _guard_rules:
                                    _mt = (_rule.get("match_tool") or "").strip()
                                    if _mt and _mt != "*":
                                        _mt_allowed = {t.strip().lower() for t in _mt.split(",")}
                                        _tc_lower = tc.name.lower()
                                        _my_aliases = _TOOL_ALIASES.get(_tc_lower, {_tc_lower})
                                        if not (_mt_allowed & _my_aliases) and "*" not in _mt_allowed:
                                            continue
                                    # Require an actual matcher (pattern OR non-wildcard
                                    # match_tool). A rule with match_tool="*" and no
                                    # match_pattern would block every tool_use — refuse
                                    # to fire on that shape.
                                    _mp = _rule.get("match_pattern")
                                    if not _mp and (not _mt or _mt == "*"):
                                        continue
                                    if _mp:
                                        try:
                                            if not _re.search(_mp, _tool_input_text, _re.IGNORECASE):
                                                continue
                                        except _re.error:
                                            continue
                                    _p = _ACTION_PRIORITY.get(_rule.get("action", "audit"), 3)
                                    if _p < _best_priority:
                                        _best_priority = _p
                                        _guard_hit = _rule

                                if _guard_hit:
                                    _guard_action = _guard_hit.get("action", "audit")
                                    _guard_msg = _guard_hit.get("message", "")
                                    # _project_rule (mcp.py) renames id -> rule_id.
                                    # Also fall back to "id" for defence in depth.
                                    _guard_rule_id = _guard_hit.get("rule_id") or _guard_hit.get("id")
                                    # Emit to run event stream so the CLI + dashboard see it
                                    if db and run_id:
                                        _emit(db, run_id, block_id, "brain_tool_call", {
                                            "tool": tc.name,
                                            "guard_action": _guard_action,
                                            "guard_rule": _guard_rule_id,
                                            "guard_message": _guard_msg,
                                            "turn": turns,
                                        })
                                    # Decision label used in both the audit row and the
                                    # notification payload — kept as one variable so the
                                    # two surfaces never disagree.
                                    _decision_label = (
                                        "blocked" if _guard_action == "block"
                                        else "warned" if _guard_action == "warn"
                                        else "audited"
                                    )

                                    # Also write to the Guard audit trail so it appears
                                    # in the flight recorder (Guard → Activity), same as
                                    # hook and proxy verdicts.
                                    try:
                                        from app.modules.guard.models import GuardAuditEvent
                                        from datetime import datetime as _dt, timezone as _tz
                                        db.add(GuardAuditEvent(
                                            workspace_id=_uuid.UUID(workspace_id),
                                            user_email=user_email,
                                            ai_tool="conduct_runtime",
                                            tool_call=tc.name,
                                            source="runtime",
                                            decision=_decision_label,
                                            rule_id=_guard_rule_id,
                                            rule_message=_guard_msg,
                                            input_summary=_tool_input_text[:500],
                                            conductai_run_id=str(run_id) if run_id else None,
                                            conductai_workflow=playbook_slug,
                                            conductai_workflow_id=str(workflow_id) if workflow_id else None,
                                            ts=_dt.now(_tz.utc),
                                        ))
                                        db.commit()
                                    except Exception as _audit_exc:
                                        log.warning("brain.non_mcp_guard.audit_write_failed",
                                                    error=str(_audit_exc))
                                        db.rollback()

                                    # Fan out block/warn (skip audit — too noisy) to the
                                    # workspace's configured notification channels
                                    # (Slack, webhook, PagerDuty, email). Same helper the
                                    # proxy and MCP surfaces use.
                                    if _guard_action in ("block", "warn"):
                                        try:
                                            from app.modules.guard.routers.events import notify_guard_block
                                            notify_guard_block(
                                                db, workspace_id,
                                                decision=_decision_label,
                                                rule_id=_guard_rule_id,
                                                user_email=user_email,
                                                tool=tc.name,
                                                source="runtime",
                                            )
                                        except Exception as _notify_exc:
                                            log.warning("brain.non_mcp_guard.notify_failed",
                                                        error=str(_notify_exc))

                                    if _guard_action == "block":
                                        result_content = f"[guard_blocked] {_guard_msg}  [rule: {_guard_rule_id}]"
                                        _guard_blocked_non_mcp = True
                            except Exception as _guard_exc:
                                log.warning("brain.non_mcp_dispatch.guard_failed", error=str(_guard_exc))

                        # require_tests_pass guardrail: intercept commit-like calls
                        # when no test run has been observed yet in this turn.
                        _GIT_COMMIT_PATTERNS = ("git commit", "git push", "gh pr create")
                        _is_commit_call = (
                            tc.name == "run_shell"
                            and any(
                                p in (tc.input or {}).get("command", "")
                                for p in _GIT_COMMIT_PATTERNS
                            )
                        )
                        if _guard_blocked_non_mcp:
                            pass  # result_content already set to the guard block message
                        elif _require_tests_pass and _is_commit_call and not _test_ran_this_turn:
                            result_content = (
                                "[guardrail_blocked] Tests must pass before committing. "
                                "Run tests first."
                            )
                            if db and run_id:
                                _emit(db, run_id, block_id, "guardrail.require_tests_pass", {
                                    "tool": tc.name,
                                    "command": (tc.input or {}).get("command", ""),
                                    "turn": turns,
                                    "message": "Blocked: tests must pass before committing",
                                })
                        else:
                            result_content = _dispatch_with_creds(tc.name, tc.input)
                            # Detect test runs so subsequent commit calls are allowed
                            if (
                                _require_tests_pass
                                and tc.name == "run_shell"
                                and not _test_ran_this_turn
                            ):
                                _cmd = (tc.input or {}).get("command", "").lower()
                                _TEST_MARKERS = ("pytest", "npm test", "yarn test", "make test",
                                                 "go test", "cargo test", "rspec", "jest", "vitest")
                                if any(m in _cmd for m in _TEST_MARKERS):
                                    _test_ran_this_turn = True
                        result_content = _classify_tool_error(result_content)
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
        _record_turns(db, run_id, max_turns, True)
        _close_session()
        raise RuntimeError(
            f"Turn budget exhausted: agent did not reach end_turn after {max_turns} turns "
            f"({total_input_tokens} input / {total_output_tokens} output tokens, ${cost_usd:.4f})"
        )

    else:
        # Single call (no tools)
        _cached = _cache_get(run_id, block_id, 0)
        if _cached is not None:
            from app.runtime.llm_client import LLMResponse as _LLMResponse
            response = _LLMResponse.from_cache_dict(_cached)
            response.cost_usd = 0.0  # ponytail: no charge on replay
            log.debug("brain.llm_cache_hit", run_id=run_id, block_id=block_id, turn=0)
        else:
            _fe_idx = state.get("__for_each_index")
            _idem_key = (
                f"conduct-{run_id}-{block_id}-0"
                + (f"-fe{_fe_idx}" if _fe_idx is not None else "")
            ) if run_id and block_id else None
            def _on_retry_single(info: dict) -> None:
                if db and run_id:
                    _emit(db, run_id, block_id, "llm_upstream_retry", {
                        **info, "turn": 0,
                        "block_attempt": state.get("__block_attempt", 1),
                    })
            _outer_attempt = int(state.get("__block_attempt", 1))
            try:
                response = llm.create(
                    model=model_id,
                    max_tokens=2048,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                    cache_system=True,
                    idempotency_key=_idem_key,
                    on_retry=_on_retry_single,
                    outer_attempt=_outer_attempt,
                )
            except LLMUpstreamError as _up_err:
                if db and run_id:
                    _emit(db, run_id, block_id, "llm_upstream_blocked", {
                        "provider": _up_err.provider,
                        "status": _up_err.status,
                        "content_type": _up_err.content_type,
                        "attempts": _up_err.attempts,
                        "cf_ray": _up_err.cf_ray,
                        "render_request_id": _up_err.request_id,
                        "body_snippet": _up_err.body_snippet,
                        "turn": 0,
                        "base_url": _effective_base_url,
                        "is_final": True,
                        "block_attempt": state.get("__block_attempt", 1),
                    })
                log.error("brain.llm_upstream_blocked",
                          provider=_up_err.provider, status=_up_err.status,
                          cf_ray=_up_err.cf_ray, render_req=_up_err.request_id,
                          attempts=_up_err.attempts,
                          run_id=run_id, block_id=block_id)
                raise
            _cache_set(run_id, block_id, 0, response.to_cache_dict())
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
            _write_trace(db, run_id, block_id, 1, "user",
                         content=user_message[:8000] if user_message else None)
            _write_trace(db, run_id, block_id, 1, "assistant",
                         content=text[:8000] if text else None,
                         input_tokens=response.usage.input_tokens,
                         output_tokens=response.usage.output_tokens)
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
            "upstream_url": _effective_base_url,
            "llm_upstream": _env_vars.get("PROXY_CONFIG_LLM_UPSTREAM") or None,
        }
        _extracted = _extract_last_json_object(result.get("output", ""))
        if _extracted:
            result = {**_extracted, **result}
        _close_session()
        return result
