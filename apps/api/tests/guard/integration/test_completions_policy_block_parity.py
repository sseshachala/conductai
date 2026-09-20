"""#2 — policy-block parity between /gateway/v1/completions and
the SDK-shaped /gateway/v1/openai/v1/chat/completions route (#2144).

The invariant: for the same profile + same body + same policy decision,
BOTH routes must return the same block envelope (same status, same
error type, same reason). If they diverge, the ``canonical_profile``
guarantee — that /completions is a thin adapter over the same v2
executor — is broken.

We monkeypatch ``evaluate_composed`` to force a BLOCK decision rather
than seeding a real rule row. Policy-rule seeding has extensive
coverage in the unit suite; the invariant this file exists to lock
is the parity of the DOWNSTREAM behavior at the gateway boundary
— identical for both entry points.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.guard.policy_types import PolicyAction, PolicyDecision


@pytest.fixture()
def force_policy_block(monkeypatch: pytest.MonkeyPatch):
    """Every ``evaluate_composed`` call returns a hard BLOCK decision."""
    def _block(ctx, sources=None):
        return PolicyDecision(
            action=PolicyAction.BLOCK,
            source="integration-test",
            reason="integration-test block rule",
            rule_id="it-block-rule",
        )

    # gateway_handler imports evaluate_composed lazily inside its policy
    # closure builder, so patching the source module is the right seam.
    monkeypatch.setattr("app.guard.policy.evaluate_composed", _block)


def _fire_completions(client: TestClient, seeded: dict) -> tuple[int, dict]:
    resp = client.post(
        "/gateway/v1/completions",
        headers={"Authorization": f"Bearer {seeded['agent_token']}"},
        json={
            "profile": seeded["profile_identifier"],
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
        },
    )
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, {"raw": resp.text}


def _fire_openai_sdk_shape(client: TestClient, seeded: dict) -> tuple[int, dict]:
    resp = client.post(
        "/gateway/v1/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {seeded['agent_token']}"},
        json={
            "model": seeded["profile_identifier"],
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
        },
    )
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, {"raw": resp.text}


def test_block_envelope_is_identical_across_canonical_and_sdk_routes(
    seeded_profile, gateway_app, force_policy_block,
) -> None:
    client = TestClient(gateway_app)

    status_canonical, body_canonical = _fire_completions(client, seeded_profile)
    status_sdk, body_sdk = _fire_openai_sdk_shape(client, seeded_profile)

    # Both routes MUST agree on the block signal at the HTTP layer.
    assert status_canonical == status_sdk, (
        f"canonical returned {status_canonical}, SDK route returned {status_sdk} "
        f"— they must agree since /completions is a shim over the same executor"
    )
    # Guard blocks land as 403 through the fail-closed shape (v2 executor
    # normalized). 451 is reserved for approval-required-not-yet-approved
    # from the coordinator's policy layer. Locking whatever the current
    # blocking status is prevents a silent regression from allowing the
    # request through as 200.
    assert status_canonical != 200, (
        f"block did not reject the request — status {status_canonical}, "
        f"body {body_canonical}"
    )
    assert status_canonical in {403, 451}, (
        f"unexpected block status {status_canonical} — expected 403 (guard "
        f"fail-closed shape) or 451 (approval required). Body: {body_canonical}"
    )

    # The transport stub MUST NOT be called from either route — a policy
    # block that dispatches anyway is the exact governance regression
    # this test guards.
    assert len(seeded_profile["stub_transport"].calls) == 0, (
        "transport was called despite a policy BLOCK decision"
    )

    # Envelope parity — same policy source, same rule id in both bodies.
    # Body format is the guard router's fail-closed shape:
    # {"error": {"type": ..., "message": ..., "rule_id": ...}}
    def _pick(body: dict) -> dict:
        err = body.get("error") if isinstance(body, dict) else {}
        return {
            "type": (err or {}).get("type") if isinstance(err, dict) else None,
            "rule_id": (err or {}).get("rule_id") if isinstance(err, dict) else None,
        }

    canon = _pick(body_canonical)
    sdk = _pick(body_sdk)
    assert canon["type"] == sdk["type"], (canon, sdk)
    assert canon["rule_id"] == sdk["rule_id"], (canon, sdk)
