"""Actor tool registrations — every import here fires side-effects that
populate `default_action_registry` (and paired `default_registry.ToolDef`
entries via `app.tools.registrations.lens`).
"""
from app.modules.glens.actor.registrations import deactivate_agent_identity  # noqa: F401
from app.modules.glens.actor.registrations import decide_approval  # noqa: F401
from app.modules.glens.actor.registrations import install_pack  # noqa: F401
from app.modules.glens.actor.registrations import run_workflow  # noqa: F401
from app.modules.glens.actor.registrations import toggle_policy  # noqa: F401 — registers enable_policy + disable_policy
from app.modules.glens.actor.registrations import update_budget  # noqa: F401
