from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings

# State key constants — single source of truth; blocks import these instead of raw strings
CRED_TOKEN_KEY      = "__cred_token__"
CRED_API_URL_KEY    = "__cred_api_url__"
CRED_HANDLES_KEY    = "__cred_handles__"
RUN_TOKEN_KEY       = "__conduct_run_token__"
MAX_TURNS_KEY       = "__max_turns"
MAX_COST_KEY        = "__max_cost_usd"
USER_EMAIL_KEY      = "__user_email"


def cred_from_state(state: dict) -> tuple[str, str, list]:
    """Extract (cred_token, cred_api_url, cred_handles) from run state."""
    return (
        state.get(CRED_TOKEN_KEY, ""),
        state.get(CRED_API_URL_KEY, ""),
        state.get(CRED_HANDLES_KEY, []),
    )


@dataclass
class RunContext:
    """
    Typed contract for every run. Executor builds this once after all setup;
    blocks receive it via state keys (backward compat) — no block signatures change.

    If any required field is missing the executor fails at construction,
    not silently 8 blocks later.
    """
    workspace_id: str
    run_id: str
    # Credential broker
    cred_token: str
    cred_api_url: str
    cred_handles: list[str] = field(default_factory=list)
    # Run-scoped proxy auth token (minted at trigger time)
    conduct_run_token: str = ""
    # Budgets
    max_turns: int = 20
    max_cost_usd: float = 5.0
    # User context
    user_email: str | None = None
    env_id: str | None = None

    def __post_init__(self) -> None:
        if not self.workspace_id:
            raise ValueError("RunContext: workspace_id is required")
        if not self.run_id:
            raise ValueError("RunContext: run_id is required")
        if not self.cred_api_url:
            raise ValueError("RunContext: cred_api_url is required — set API_BASE_URL env var")

    def apply_to_state(self, state: dict[str, Any]) -> None:
        """Write all context fields into state so existing blocks read them unchanged."""
        state[CRED_TOKEN_KEY]   = self.cred_token
        state[CRED_API_URL_KEY] = self.cred_api_url
        state[CRED_HANDLES_KEY] = self.cred_handles
        state[RUN_TOKEN_KEY]    = self.conduct_run_token
        state[MAX_TURNS_KEY]    = self.max_turns
        state[MAX_COST_KEY]     = self.max_cost_usd
        state[USER_EMAIL_KEY]   = self.user_email


def get_email_creds(cred_token: str, cred_api_url: str, cred_handles: list) -> dict:
    """Return email credentials, trying 'email' first then 'resend' as fallback."""
    from app.core.credentials import fetch_credential
    creds = fetch_credential(cred_token, "email", cred_api_url) if "email" in cred_handles else {}
    if not creds:
        creds = fetch_credential(cred_token, "resend", cred_api_url) if "resend" in cred_handles else {}
    return creds


def enrich_run_state_contract(
    initial_state: dict[str, Any],
    *,
    source: str,
    trigger_provider: str,
    workflow_id: str,
    workspace_id: str | None,
    max_turns: int,
    max_cost_usd: float | None = None,
) -> dict[str, Any]:
    """
    Add a consistent explainability + governance envelope to every run state.

    This keeps provider-attributed metadata and policy intent uniform across
    manual/test/webhook starts, regardless of vendor.
    """
    state = deepcopy(initial_state)

    effective_max_cost = float(max_cost_usd) if max_cost_usd is not None else float(settings.default_max_cost_usd)
    effective_max_cost = max(0.01, effective_max_cost)

    state["__max_turns"] = int(max(1, max_turns))
    state["__max_cost_usd"] = round(effective_max_cost, 6)

    state["__run_explainability"] = {
        "version": "phase2.v1",
        "source": source,
        "trigger_provider": trigger_provider,
        "workflow_id": workflow_id,
        "workspace_id": workspace_id,
        "budget": {
            "max_turns": int(max(1, max_turns)),
            "max_cost_usd": round(effective_max_cost, 6),
        },
    }

    state["__governance"] = {
        "policy_surface": "unified",
        "provider": trigger_provider,
        "enforcement_mode": "consistent",
        "version": "phase2.v1",
    }

    return state
