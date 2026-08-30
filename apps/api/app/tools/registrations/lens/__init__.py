"""Lens tool registrations — composition root.

Historical background: all Lens ToolDefs used to live in a single 2071-line
`lens.py`. Split into a per-domain package on 2026-08-29 so new tools land
in the right file instead of tail-appending forever.

Order of operations:
  1. Import every domain submodule (their `TOOLS = [...]` lists build at
     module load — no registry writes yet).
  2. Import actor ActionSpec registrations (populates
     `default_action_registry` — side-effect only).
  3. Concatenate every submodule's TOOLS list into `_ALL_TOOLS`.
  4. Register once via `default_registry.register_all(_ALL_TOOLS)`.

Steps 1-2 are order-independent (each submodule imports only from
`_shared`; there are no cross-submodule imports).

Adding a new Lens tool:
  - Read tool → drop a `ToolDef` into the matching domain file, add name to
    its TOOLS list.
  - Mutating tool → add ActionSpec in `app.modules.glens.actor.registrations`
    and a paired `ToolDef` in `lens/actor.py` with `impl=_actor_impl("<name>")`.
"""
from __future__ import annotations

from app.tools.registry import default_registry

from app.tools.registrations.lens import (
    actor,
    dashboard_kpis,
    discovery,
    governance,
    guard_core,
    marketplace,
    observability_kpis,
    ops,
    policies,
    primitives,
    workflows,
    workspace,
)


_ALL_TOOLS = [
    *guard_core.TOOLS,
    *policies.TOOLS,
    *workflows.TOOLS,
    *workspace.TOOLS,
    *marketplace.TOOLS,
    *ops.TOOLS,
    *discovery.TOOLS,
    *primitives.TOOLS,
    *governance.TOOLS,
    *dashboard_kpis.TOOLS,
    *observability_kpis.TOOLS,
    *actor.TOOLS,
]


def register(replace: bool = False) -> None:
    """Register every Lens ToolDef into `default_registry`.

    Actor ActionSpecs register via side-effect import so mutating ToolDefs
    can resolve their spec at first dispatch.
    """
    # Actor ActionSpec side-effect import — populates default_action_registry
    # before any actor ToolDef.impl runs. Guarded because the actor package
    # lands in a separate PR (#1456); when it isn't present, no actor
    # ToolDefs exist yet either, so skipping the import is safe.
    try:
        from app.modules.glens.actor import registrations as _actor_regs  # noqa: F401
    except ModuleNotFoundError:
        pass
    default_registry.register_all(_ALL_TOOLS, replace=replace)


# Side-effect on import: populate the registry.
register()


# ── Backwards-compat re-exports ─────────────────────────────────────────────
# Callers that used to `from app.tools.registrations.lens import <symbol>`
# under the flat file still work. Add re-exports here when a submodule
# symbol gains an external caller (tests, other routers, docs).

from app.tools.registrations.lens._shared import (  # noqa: F401,E402
    _run,
    _impl,
    _actor_impl,
    _window_start,
    _LIMIT,
    _DECISION,
    _TS_SINCE,
    _TS_UNTIL,
    _RULE_ID,
    _DAYS_WINDOW,
    _TIME_WINDOW,
    _READ_ONLY,
    _READ_ONLY_OPEN_WORLD,
    _LENS_TAGS,
    _ACTOR_TAGS,
)

# Free-function tool impls that are patched by tests (see conftest/mock targets).
from app.tools.registrations.lens.dashboard_kpis import (  # noqa: F401,E402
    get_dashboard_outcomes,
    list_attention_runs,
    list_agent_health,
    get_dashboard_token_usage,
    get_top_policy_hits,
)
from app.tools.registrations.lens.observability_kpis import (  # noqa: F401,E402
    get_observability_health,
    get_dora_metrics,
    get_analytics_summary,
    list_agent_status,
    get_playbook_scorecards,
)
from app.tools.registrations.lens.governance import (  # noqa: F401,E402
    get_governance_summary,
    get_soc2_status,
    get_ai_rollout_status,
    _run_framework_coverage,
)
from app.tools.registrations.lens.workflows import (  # noqa: F401,E402
    list_playbooks,
    get_playbook,
)
from app.tools.registrations.lens.workspace import get_workspace_kpis  # noqa: F401,E402
from app.tools.registrations.lens.discovery import list_discovered_agents  # noqa: F401,E402
from app.tools.registrations.lens.policies import list_credentials  # noqa: F401,E402
from app.tools.registrations.lens.ops import get_autopilot_activity  # noqa: F401,E402
from app.tools.registrations.lens.primitives import (  # noqa: F401,E402
    list_machines_sync_state,
    get_llm_primitives,
    get_rate_limits,
)


# The full TOOLS list, exposed for tests that count/iterate.
_TOOLS = _ALL_TOOLS
