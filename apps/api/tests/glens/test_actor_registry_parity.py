"""Actor registry parity harness.

Enforces the 'add both' convention across every mutating tool:

- Every `ActionSpec` in `default_action_registry` has a paired `ToolDef`
  in `default_registry` with the same name + the `actor` tag.
- Every `actor`-tagged `ToolDef` has a matching `ActionSpec`.
- `ToolDef.impl.__name__` == `actor_impl_<spec.name>` (verifies the impl
  routes back to the correct spec via `require_confirmation`).
- `spec.guard_permission` matches `<domain>.<subject>.<action>` shape.
- `spec.description` is non-empty.

Catches at CI time what would otherwise fail live in Lens: a new tool
registered on one side but not the other, or an impl wired to the wrong
spec name.
"""
from __future__ import annotations

import re

import pytest

from app.modules.glens.actor import default_action_registry
from app.modules.glens.actor import registrations  # noqa: F401 — populate registry
from app.tools import registrations as _tool_registrations  # noqa: F401
from app.tools.registry import default_registry


_PERMISSION_RE = re.compile(r"^[a-z][a-z_]*(\.[a-z][a-z_]*){2,}$")


def _actor_specs():
    return default_action_registry.all()


def _actor_tools():
    return default_registry.list(tag="actor")


@pytest.mark.parametrize("spec", _actor_specs(), ids=lambda s: s.name)
def test_actionspec_has_paired_tooldef(spec):
    tool = default_registry.get(spec.name)
    assert tool is not None, (
        f"ActionSpec '{spec.name}' registered but no matching ToolDef — "
        f"add one in apps/api/app/tools/registrations/lens/actor.py"
    )
    assert "actor" in tool.tags, (
        f"ToolDef '{spec.name}' missing 'actor' tag — dispatch won't recognize it"
    )


@pytest.mark.parametrize("tool", _actor_tools(), ids=lambda t: t.name)
def test_actor_tooldef_has_paired_actionspec(tool):
    # Chat-surface confirm/cancel shortcut tools are not spec-backed; they
    # dispatch existing pending actions rather than propose new ones.
    if tool.name in {"confirm_pending_action", "cancel_pending_action"}:
        pytest.skip("confirm/cancel shortcut tools have no ActionSpec by design")
    spec = default_action_registry.get(tool.name)
    assert spec is not None, (
        f"ToolDef '{tool.name}' tagged 'actor' but no matching ActionSpec — "
        f"add one under apps/api/app/modules/glens/actor/registrations/"
    )


@pytest.mark.parametrize("spec", _actor_specs(), ids=lambda s: s.name)
def test_tooldef_impl_routes_to_spec(spec):
    """`ToolDef.impl` for a spec-backed tool must be `_actor_impl(spec.name)`
    — the name is stamped on the impl so we can verify wiring without
    executing it."""
    tool = default_registry.get(spec.name)
    assert tool is not None
    expected = f"actor_impl_{spec.name}"
    actual = getattr(tool.impl, "__name__", "")
    assert actual == expected, (
        f"ToolDef '{spec.name}' impl is '{actual}', expected '{expected}' — "
        f"this fires the wrong spec's execute() on confirm"
    )


@pytest.mark.parametrize("spec", _actor_specs(), ids=lambda s: s.name)
def test_guard_permission_shape(spec):
    perm = spec.guard_permission
    assert perm, f"ActionSpec '{spec.name}' has empty guard_permission"
    assert _PERMISSION_RE.match(perm), (
        f"ActionSpec '{spec.name}' guard_permission '{perm}' does not match "
        f"<domain>.<subject>.<action> shape"
    )


@pytest.mark.parametrize("spec", _actor_specs(), ids=lambda s: s.name)
def test_description_non_empty(spec):
    assert spec.description.strip(), (
        f"ActionSpec '{spec.name}' has no description — surfaces as blank in "
        f"the confirm card"
    )


@pytest.mark.parametrize("spec", _actor_specs(), ids=lambda s: s.name)
def test_propose_and_execute_callable(spec):
    assert callable(spec.propose)
    assert callable(spec.execute)
