"""
sandbox_block — executes a sandbox block, provisioning a shared compute session.

The session is stored in the run's sandbox_sessions dict keyed by block ID.
Brain blocks that declare `runs_in: <sandbox_block_id>` reuse this session
instead of creating their own, sharing filesystem state across the workflow.

Provider selection:
  1. block.data.sandbox_config.provider → explicit (from canvas dropdown)
  2. Credential auto-detection fallback (same as create_session inference)

Credential auto-detection by provider:
  e2b    → E2B_API_KEY in workspace env
  modal  → MODAL_TOKEN_ID + MODAL_TOKEN_SECRET in workspace env
  ssh    → credentials_from integration handle
  local  → no credentials needed (dev only)
"""
from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)

_PROVIDER_CRED_HINTS = {
    "e2b": "E2B_API_KEY",
    "modal": "MODAL_TOKEN_ID + MODAL_TOKEN_SECRET",
    "ssh": "ssh_private_key via credentials_from integration",
    "local": "(none required)",
}


def _execute_sandbox(
    block: dict,
    state: dict,
    credentials: dict,
    sandbox_sessions: dict,
) -> dict:
    """
    Provision the sandbox and run any setup commands.

    Stores the live session in sandbox_sessions[block_id] so downstream
    Brain blocks with `runs_in` can reuse it.

    Returns a state dict with sandbox metadata (provider, sandbox_id).
    """
    from app.runtime.sandbox_session import create_session

    block_id = block["id"]
    data = block.get("data", {})
    config = data.get("sandbox_config") or data.get("config") or {}

    provider = config.get("provider")
    if not provider:
        raise ValueError(
            f"sandbox block '{block_id}' requires sandbox_config.provider. "
            f"Supported: {sorted(_PROVIDER_CRED_HINTS)}"
        )

    # Validate credential presence before spinning up — fail fast with clear message
    _check_credentials(provider, credentials, block_id)

    runs_on = None
    if provider == "ssh":
        runs_on = {
            "ip": config.get("ip") or state.get("__remote_ip"),
            "credentials_from": config.get("credentials_from", "digitalocean"),
            "username": config.get("username"),
            "port": config.get("port"),
        }

    log.info("sandbox_block.provisioning", block_id=block_id, provider=provider)
    session = create_session(
        remote_host=runs_on,
        credentials=credentials,
        runs_on={"provider": provider},
    )

    # Run setup commands sequentially — any failure raises immediately
    setup_commands = config.get("setup") or []
    for cmd in setup_commands:
        result = session.dispatch("run_shell", {"command": cmd})
        log.debug("sandbox_block.setup_cmd", block_id=block_id, cmd=cmd[:80], result=result[:200])
        if result.startswith("Error:") or result.startswith("Refused:"):
            session.close()
            raise RuntimeError(
                f"sandbox block '{block_id}' setup command failed.\n"
                f"Command: {cmd}\nResult: {result}"
            )

    # Store live session — Brain blocks with runs_in will pick this up
    sandbox_sessions[block_id] = session
    sandbox_id = getattr(session, "_sandbox_id", None)

    log.info("sandbox_block.ready", block_id=block_id, provider=provider, sandbox_id=sandbox_id)
    return {
        "provider": provider,
        "sandbox_id": sandbox_id,
        "setup_commands_run": len(setup_commands),
        "working_dir": session.working_dir,
    }


def _check_credentials(provider: str, credentials: dict, block_id: str) -> None:
    env_vars = credentials.get("env_vars") or {}

    if provider == "e2b":
        if not (env_vars.get("E2B_API_KEY") or env_vars.get("e2b_api_key")):
            raise RuntimeError(
                f"sandbox block '{block_id}' uses provider 'e2b' but E2B_API_KEY "
                f"is not set. Add it under Settings → Environments."
            )
    elif provider == "modal":
        modal_creds = credentials.get("modal", {})
        token_id = modal_creds.get("token_id") or env_vars.get("MODAL_TOKEN_ID") or ""
        token_secret = modal_creds.get("token_secret") or env_vars.get("MODAL_TOKEN_SECRET") or ""
        if not (token_id and token_secret):
            raise RuntimeError(
                f"sandbox block '{block_id}' uses provider 'modal' but "
                f"MODAL_TOKEN_ID / MODAL_TOKEN_SECRET are not set. "
                f"Add them under Settings → Environments."
            )
    elif provider == "local":
        from app.core.config import settings
        if settings.environment == "production":
            raise RuntimeError(
                f"sandbox block '{block_id}': provider 'local' is not allowed in production. "
                f"Use 'e2b' or 'modal'."
            )
