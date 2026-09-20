"""#3 — budget refusal for /gateway/v1/completions (#2144).

The invariant: when the pre-flight budget reservation refuses a request,
the executor MUST return the canonical ``budget_reservation_refused``
envelope with a 402/503 status AND MUST NOT dispatch to any target. A
regression that dispatches anyway would let paid traffic through after
the enforcement layer said no.

Reserving a real budget row + wiring redis balances to reproduce refusal
would double the fixture footprint of this suite. Since the invariant
this test guards is the SHAPE and SIDE-EFFECTS at the gateway boundary
(not the ledger's own logic — that has its own dedicated tests under
tests/chaos), we monkeypatch the reservation helper at its call site
to return an EXCEEDED result. The ledger-logic path already has
end-to-end coverage in the chaos suite.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def refuse_budget(monkeypatch: pytest.MonkeyPatch):
    """Force the next ``reserve_budgets_for_request`` call to refuse."""
    from app.modules.guard.gateway_lifecycle import (
        ReserveBudgetsResult, ReserveOutcome,
    )

    def _refuse(*args, **kwargs):
        return ReserveBudgetsResult(
            outcome=ReserveOutcome.EXCEEDED,
            reservations=None,
            refusing_budget=None,
            error="hard cap exceeded (integration test fixture)",
        )

    monkeypatch.setattr(
        "app.modules.guard.gateway_lifecycle.reserve_budgets_for_request",
        _refuse,
    )
    # gateway_handler imports it via aliased name at module load time —
    # patch that reference too so the handler sees the stub.
    monkeypatch.setattr(
        "app.modules.guard.gateway_handler._reserve_budgets_for_request",
        _refuse,
        raising=False,
    )


def test_budget_refusal_returns_canonical_envelope_and_does_not_dispatch(
    seeded_profile, gateway_app, refuse_budget,
) -> None:
    client = TestClient(gateway_app)

    resp = client.post(
        "/gateway/v1/completions",
        headers={"Authorization": f"Bearer {seeded_profile['agent_token']}"},
        json={
            "profile": seeded_profile["profile_identifier"],
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
        },
    )
    # EXCEEDED maps to 402 (payment required). Other refusal outcomes map
    # to 503; both fall under the same envelope contract.
    assert resp.status_code in {402, 503}, resp.text
    payload = resp.json()
    assert payload.get("type") == "budget_reservation_refused", payload

    # The critical invariant: the transport MUST NOT be called when the
    # enforcement layer refused. A dispatch here would be paid-traffic
    # leakage past a hard budget cap.
    stub = seeded_profile["stub_transport"]
    assert len(stub.calls) == 0, (
        f"transport.execute was called {len(stub.calls)} time(s) despite "
        f"a budget refusal — paid traffic leaked past the enforcement layer"
    )
