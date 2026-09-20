"""Smoke test — /gateway/v1/completions end-to-end fixture probe (#2144).

Proves the fixture stack in ``conftest.py`` actually stands up:

  - published GatewayProfileV2 is discoverable via ``resolve_v2``
  - agent token authenticates through ``handle_gateway_request``
  - v2 executor dispatches to the stubbed transport
  - a 200 response comes back
  - the stub captured exactly one outbound forward

Assertions here are DELIBERATELY loose — this file exists to validate the
fixture, not to prove parity. Strict-invariant tests (audit finalization,
policy block parity, budget refusal, revision_id pinning) land in
follow-up files once this smoke test is green.
"""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_smoke_published_v2_profile_serves_a_completions_request(
    seeded_profile, gateway_app
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
    assert resp.status_code == 200, resp.text

    stub = seeded_profile["stub_transport"]
    assert len(stub.calls) == 1, (
        f"expected exactly one outbound forward, got {len(stub.calls)}"
    )
