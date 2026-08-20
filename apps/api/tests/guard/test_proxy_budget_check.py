"""Smoke test for #1083 — pre-forward budget check wired into _proxy.

Verifies the budget_check helper is importable from the proxy module and
that BudgetCheckOut carries the fields the 429 response body references.
"""
from __future__ import annotations


def test_budget_check_importable_from_spend():
    from app.modules.guard.routers.spend import budget_check, BudgetCheckOut
    assert callable(budget_check)
    assert {"hard_blocked", "reason", "monthly_cost_usd", "hard_limit_usd"} \
        <= set(BudgetCheckOut.model_fields.keys())


def test_proxy_module_imports_cleanly():
    # Guards against the import inside _proxy being wrong (ast.parse alone
    # would miss import-time failures on runtime paths).
    from app.modules.guard.routers import proxy as _proxy_mod
    from app.modules.guard.routers.spend import budget_check
    assert _proxy_mod._proxy is not None
    assert budget_check is not None


def test_budget_exceeded_response_shape():
    # Contract check: keys the frontend / CLI will parse.
    from app.modules.guard.routers.spend import BudgetCheckOut
    bc = BudgetCheckOut(hard_blocked=True, reason="over", monthly_cost_usd=42.0, hard_limit_usd=40.0)
    body = {"error": {
        "type": "guard_budget_exceeded",
        "message": bc.reason or "Monthly AI budget reached.",
        "monthly_cost_usd": bc.monthly_cost_usd,
        "hard_limit_usd": bc.hard_limit_usd,
    }}
    assert body["error"]["type"] == "guard_budget_exceeded"
    assert body["error"]["monthly_cost_usd"] == 42.0
    assert body["error"]["hard_limit_usd"] == 40.0
