"""Actor tool registrations — every import here fires side-effects that
populate `default_action_registry` (and paired `default_registry.ToolDef`
entries via `app.tools.registrations.lens`).
"""
from app.modules.glens.actor.registrations import decide_approval  # noqa: F401
