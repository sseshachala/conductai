"""Global registry for `ActionSpec` — mirrors `default_registry` for ToolDefs.

`registrations/*` modules populate this at import time; the confirm endpoint
uses `.get(tool_name)` to route dispatch back to the right `execute`.
"""
from __future__ import annotations

from app.modules.glens.actor.types import ActionSpec


class ActionRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ActionSpec] = {}

    def register(self, spec: ActionSpec, *, replace: bool = False) -> ActionSpec:
        if not replace and spec.name in self._specs:
            raise ValueError(f"ActionSpec {spec.name!r} already registered")
        self._specs[spec.name] = spec
        return spec

    def get(self, name: str) -> ActionSpec | None:
        return self._specs.get(name)

    def names(self) -> list[str]:
        return sorted(self._specs)

    def all(self) -> list[ActionSpec]:
        return list(self._specs.values())


default_action_registry = ActionRegistry()
