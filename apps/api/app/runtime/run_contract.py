from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.core.config import settings


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
