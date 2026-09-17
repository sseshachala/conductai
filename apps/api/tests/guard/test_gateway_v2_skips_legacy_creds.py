"""X3 — v2 must not require legacy v1 credentials to serve a request.

Before the fix, ``handle_gateway_request`` ran the v1 vault-lookup
block (``_upstream_url`` / ``_vault_key`` / trial-key resolution)
unconditionally, then fail-closed with 503 if none of those v1
credentials existed. That meant a workspace configured **only** with
a v2 Gateway Profile (targets carry their own ``credential_ref``
pointing at Vault) still had to provision a v1
``ANTHROPIC_API_KEY``/``OPENAI_API_KEY`` or the request would 503
before the v2 executor ever ran.

Contract this file locks:

- The v1 credential-lookup block sits inside ``if _v2_plan is None:``.
- The v1-only variables (``upstream``, ``_upstream_key``,
  ``_vault_key_val``, ``transport``, ``real_key``) are initialised to
  ``None`` above the branch so downstream code can safely reason
  about "did v1 pick a key" without a ``NameError``.
- ``_execute_v2`` uses ``_v2_plan.credential_resolver``, not any of
  the v1-lookup variables — a source-level assertion here catches a
  future edit that would cross-wire them.
"""
from __future__ import annotations

from pathlib import Path


_HANDLER = (
    Path(__file__).resolve().parents[2]
    / "app" / "modules" / "guard" / "gateway_handler.py"
).read_text(encoding="utf-8")


def test_legacy_credential_block_is_gated_on_no_v2_plan():
    """The whole v1 credential-lookup block (from ``upstream =
    _upstream_url(...)`` down to the 503 fail-closed) MUST live inside
    ``if _v2_plan is None:``. Regressing this reintroduces the
    v2-only-workspace 503."""
    # Locate the gate. Fails loudly if someone deletes the branch.
    assert "if _v2_plan is None:" in _HANDLER, (
        "v1 credential-lookup gate is gone. v2-only workspaces will "
        "start hitting the 'No API key configured' 503 again."
    )

    # The v1-only variables must be initialised to None BEFORE the
    # branch, so the v2 code path doesn't NameError trying to reason
    # about them.
    for var in ("upstream", "_upstream_key", "_vault_key_val", "transport", "real_key"):
        assert f"{var} = None" in _HANDLER, (
            f"v1-only variable {var} must be initialised to None "
            f"above the ``if _v2_plan is None:`` gate. Missing this "
            f"lets a future edit hit NameError inside the v2 branch."
        )


def test_v1_only_vars_appear_only_inside_v2_none_gate():
    """The v1 vault helpers (``_upstream_url``, ``_vault_key``,
    ``resolve_trial_key``, etc.) are called exactly once each, and
    the call site sits inside the ``_v2_plan is None`` branch. If
    someone calls one of these outside the gate (e.g. moves the trial
    lookup to run unconditionally), v2-only workspaces will 503
    against a missing v1 key again."""
    # Every helper call must be preceded by the gate — use a coarse
    # "the gate appears earlier in the file than any of these" check.
    gate_pos = _HANDLER.index("if _v2_plan is None:")
    # PR 2 Commit 3 combined _upstream_url + _upstream_api_key + _vault_key
    # into ``_resolve_upstream_credentials(...)`` for threadpool offload —
    # gate check now targets that helper (v1 primitives are called inside it).
    for helper in ("_resolve_upstream_credentials", "resolve_trial_key("):
        first_call = _HANDLER.find(helper)
        assert first_call > gate_pos, (
            f"{helper} appears before the ``if _v2_plan is None:`` "
            f"gate at char {gate_pos}. That means a v2 request would "
            f"execute this v1-only lookup and potentially trip the "
            f"missing-v1-key 503 branch. Move the helper call inside "
            f"the gate."
        )


def test_execute_v2_does_not_reference_v1_credentials():
    """``_execute_v2`` should only use ``plan.credential_resolver`` for
    credentials, not any of the v1-lookup locals. This is what makes
    the ``_v2_plan is None`` gate above safe — the v2 code path never
    reads a v1-populated variable, so leaving them None is correct."""
    # Extract the body of _execute_v2.
    start = _HANDLER.index("async def _execute_v2(")
    end = _HANDLER.index("\n\ndef ", start)  # next top-level def
    body = _HANDLER[start:end]

    # None of the v1-only credential accessors should appear in
    # _execute_v2's body. If they do, the ``_v2_plan is None`` gate
    # doesn't actually protect a v2-only workspace.
    for banned in ("_upstream_key", "_vault_key_val", "real_key"):
        assert banned not in body, (
            f"_execute_v2 references v1-only credential variable "
            f"{banned!r}. That defeats the ``_v2_plan is None`` gate "
            f"in the handler — v2 must go through plan.credential_resolver."
        )
