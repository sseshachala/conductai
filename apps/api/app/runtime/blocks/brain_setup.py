"""Brain block setup phases: Gateway profile, prompts, credentials, client.

Extracted from ``brain_block._execute_brain`` (#2400). Each function is
one setup phase, called by ``_execute_brain`` in the original order.
Imports of models / runtime helpers stay lazy (worker import cost and
circular imports at module load).
"""
from __future__ import annotations

import json

import structlog

from app.core.config import settings

# Same logger name as before the split so worker log routing is unchanged.
log = structlog.get_logger("app.runtime.blocks.brain_block")

# ~8k tokens — bounded blast radius on runaway blobs
_MAX_PROMPT_CHARS = 32000

SUFFICIENCY_INSTRUCTION = (
    "IMPORTANT: Before doing any work, assess whether you have enough information "
    "to complete this task. If the description is vague, missing critical details, "
    "or you cannot determine what success looks like — respond immediately with:\n"
    "NEEDS_CLARIFICATION: <concise explanation of what is missing>\n"
    "Do not attempt partial work or use any tools if the task is unclear."
)

ENVIRONMENT_PREAMBLE = (
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


def require_gateway_profile(db, workflow_id: str | None):
    """Return the workflow's published Gateway profile row or raise.

    PR 4 — every brain_block MUST route through a published Gateway
    profile pinned on the workflow. Direct-provider clients are gone.
    Reviewer P2 #2184: validate BEFORE any resource allocation
    (sandbox creation, credential broker fetch) so a rejection
    doesn't leak sessions or credentials.
    """
    if not workflow_id or db is None:
        raise RuntimeError(
            "brain_block requires a workflow context — this call was "
            "invoked without workflow_id or a DB session. Profile-routed "
            "runtime cannot resolve a Gateway profile without both."
        )
    from app.models.workflow import Workflow as _WF
    from app.models.gateway_profile import GatewayProfile as _GP
    _wf_row = db.query(_WF).filter(_WF.id == workflow_id).first()
    if _wf_row is None or _wf_row.gateway_profile_id is None:
        raise RuntimeError(
            f"workflow {workflow_id} has no Gateway profile assigned. "
            f"Every brain block must pin a published profile in workflow "
            f"settings (#2170). Direct-provider routing is retired."
        )
    _prof_row = db.query(_GP).filter(_GP.id == _wf_row.gateway_profile_id).first()
    if _prof_row is None:
        raise RuntimeError(
            f"workflow {workflow_id} pins Gateway profile "
            f"{_wf_row.gateway_profile_id} which no longer exists. "
            f"Fix: select a valid profile in workflow settings."
        )
    if not _prof_row.active_revision_id or not _prof_row.cond_code:
        raise RuntimeError(
            f"workflow {workflow_id} pins Gateway profile "
            f"{_prof_row.name!r} which has no published revision. "
            f"Fix: publish the profile or pick a different one."
        )
    return _prof_row


def profile_routing(db, prof_row) -> tuple[str, bool]:
    """Return ``(profile_cond_key, streaming_safe)`` for a profile row."""
    from app.models.gateway_profile import GatewayProfileRevision as _GPR

    _alias = (prof_row.model_alias or "").strip()
    _profile_cond_key = (
        f"cond-{prof_row.cond_code}-{_alias}"
        if _alias else f"cond-{prof_row.cond_code}"
    )
    # Reviewer P2 #2183 — streaming is safe only when every target on
    # the published revision speaks OpenAI Chat shape natively.
    # Canonical → Anthropic Messages streaming still returns 501 from
    # the gateway. Default to False on any lookup error — never pick
    # a mode that could 501 mid-loop.
    _profile_streaming_safe: bool = False
    try:
        _rev = db.query(_GPR).filter(_GPR.id == prof_row.active_revision_id).first()
        _snapshot = (_rev.snapshot if _rev else None) or {}
        _targets = _snapshot.get("targets") or []
        if _targets:
            _profile_streaming_safe = all(
                (t.get("provider") or "").lower() not in {"anthropic"}
                and (t.get("integration") or "").lower() not in {"anthropic"}
                for t in _targets
                if isinstance(t, dict)
            )
    except Exception as _rev_exc:
        log.warning(
            "brain.gateway_profile.streaming_probe_failed",
            error=str(_rev_exc), profile_id=str(prof_row.id),
        )
        _profile_streaming_safe = False
    return _profile_cond_key, _profile_streaming_safe


def build_system_prompt(block: dict, state: dict, compiled_artifacts: dict, resolve_refs) -> str:
    """System prompt: artifact/description, prompt_file, custom instructions, refs."""
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
    # filter as the prompt path (build_user_message) so runtime secrets never leak
    # into the LLM.
    if system_prompt and "{{" in system_prompt:
        _sp_safe_state = {k: v for k, v in state.items() if not k.startswith("__")}
        system_prompt = resolve_refs(system_prompt, _sp_safe_state)
    return system_prompt


def build_context(state: dict) -> str:
    """JSON dump of public state for the fallback user message (PII-redacted)."""
    _ctx_raw = json.dumps({k: v for k, v in state.items() if not k.startswith("__")}, default=str)[:4000]
    if state.get("__guard_enabled"):
        from app.core.pii import redact_pii
        _ctx_raw = redact_pii(_ctx_raw)
    return _ctx_raw


def build_cred_env(
    session_creds: dict, state: dict, run_id: str | None,
) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """Return ``(cred_env, cred_real, cred_names)``.

    Credential placeholder pattern: model and DB see placeholder tokens,
    never raw secrets. Real values live only in ``cred_real`` and are
    swapped into subprocess env at dispatch time.
    """
    cred_env: dict[str, str] = {}   # placeholder values — safe to log / send to LLM
    _cred_real: dict[str, str] = {}  # placeholder → real value — never leaves the runtime
    cred_names: list[str] = []
    for handle, creds in session_creds.items():
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

    # Inject broker token into subprocess env only — NOT into cred_env (LLM prompt context)
    _cred_token = state.get("__cred_token__")
    _cred_api_url = state.get("__cred_api_url__")
    if _cred_token:
        _cred_real["CONDUCT_CRED_TOKEN"] = _cred_token
    if _cred_api_url:
        _cred_real["CONDUCT_API_URL"] = _cred_api_url
    return cred_env, _cred_real, cred_names


def build_user_message(
    block: dict, state: dict, context: str, cred_names: list[str], resolve_refs,
) -> str:
    """User message: rendered ``prompt`` template (or context dump) + creds + clarification."""
    cred_section = (
        "\n\nCredentials are pre-exported into every run_shell call — use them directly without any setup:\n"
        + "\n".join(f"  ${n}" for n in cred_names)
        + "\nDO NOT check if these vars exist. DO NOT try to read them from files. They are already in the shell environment."
    ) if cred_names else ""

    # Honor block.data["prompt"] as the user-message template when present.
    # Rendered with {{block.field}} refs from state; falls back to a JSON context dump
    # so playbooks written before prompt: was supported keep working unchanged.
    # See project_session_july27_runtime_bugs.md — prompt: was half-shipped for 7 weeks.
    _prompt_template = (block["data"].get("prompt") or "").strip()
    if _prompt_template:
        # __-prefixed state keys are private runtime plumbing (tokens, URLs,
        # config). Filter them out so a template like `{{__conduct_run_token__}}`
        # can never resolve to a real secret in the LLM prompt.
        _safe_state = {k: v for k, v in state.items() if not k.startswith("__")}
        _rendered_prompt = resolve_refs(_prompt_template, _safe_state)
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
    return user_message


def build_llm_client(
    *,
    state: dict,
    env_vars: dict,
    profile_cond_key: str,
    profile_streaming_safe: bool,
    pricing_snapshot,
    run_id: str | None,
    workflow_id: str | None,
    workflow_name: str | None,
    playbook_slug: str | None,
    workspace_id: str,
    environment_id: str | None,
    user_email: str | None,
):
    """Return ``(llm, conduct_proxy_url)`` — the Gateway profile client."""
    # Guard proxy URL is a platform constant — same for every workspace.
    # brain_block always routes through it; the profile picks the target.
    _conduct_proxy_url: str = settings.conduct_proxy_url.rstrip("/")

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
            env_vars.get("CONDUCT_RUN_TOKEN")
            or state.get("__conduct_run_token__", "")
            or env_vars.get("CONDUCT_AGENT_TOKEN", "")
        )
        if _agent_token:
            _extra_headers["x-conductai-internal"] = _agent_token
        _extra_headers["x-conductai-workspace-id"] = str(workspace_id)
        if environment_id:
            _extra_headers["x-conductai-environment-id"] = str(environment_id)
        if user_email:
            _extra_headers["x-conductai-user-email"] = user_email

    # PR 4 — sole path. The profile picks the target (provider + model +
    # credentials + policy); the runtime never touches per-provider
    # clients directly. Direct adapters stay in the repo for other
    # callers (tests, future non-workflow surfaces) but brain_block
    # no longer references them.
    from app.runtime.llm_client import GatewayProfileClient as _GPC
    llm = _GPC(
        profile_cond_code=profile_cond_key,
        base_url=_conduct_proxy_url,
        default_headers=_extra_headers,
        # Pricing snapshot lets the adapter compute cost from the
        # response's ``model`` + ``usage`` so brain_block's per-block
        # ``max_cost_usd`` cap stays enforced.
        pricing_snapshot=pricing_snapshot,
        # #2170 PR 3 — SSE reassembly path when ALL three hold:
        #   (a) ops flipped guard_brain_streaming_enabled on
        #   (b) gateway-side guard_gateway_tools_stream_enabled is on
        #       (enforced at the shim; a false-here 400 caller-side)
        #   (c) this profile's targets are streaming-safe (no Anthropic
        #       target the canonical shim would 501)
        stream_enabled=bool(
            settings.guard_brain_streaming_enabled and profile_streaming_safe
        ),
    )
    return llm, _conduct_proxy_url
