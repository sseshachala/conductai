"""#1 — profile resolution + revision pinning for /gateway/v1/completions (#2144).

The invariant: a request carrying ``profile: cond-<code>-<alias>`` MUST
be dispatched to the target declared in the profile's PINNED revision.
This proves two things at once:

- ``_extract_cond_code`` picked the profile, ``resolve_v2`` pinned the
  active revision, and the coordinator selected the correct target
- the target-specific model rewrite happened INSIDE the executor — the
  outbound payload carries the target's model, not the caller's alias
  (silent fallthrough to v1 legacy routing would leave the client's
  alias untouched, so a match here rules that class of bug out)

Concentric with the audit row test (#4) — that one asserts what got
recorded, this one asserts what got dispatched.
"""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_dispatched_payload_carries_target_model_not_client_alias(
    seeded_profile, gateway_app,
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
        f"expected one dispatch to the stubbed native_http target, "
        f"got {len(stub.calls)}"
    )

    call = stub.calls[0]
    # Target id from the fixture's published v2 config (see conftest).
    assert call["target_id"] == "primary", call

    # The v2 executor rewrites the outbound ``model`` to the target's own
    # model id (``openai/gpt-4o`` in the fixture). If the payload still
    # carried the caller's cond-... alias, the request would have silently
    # bypassed v2 and gone through v1 with the raw alias — exactly the
    # bug this contract exists to prevent.
    assert call["dispatched_body"]["model"] == "openai/gpt-4o", (
        f"outbound body.model was {call['dispatched_body'].get('model')!r} — "
        f"expected the target's model 'openai/gpt-4o'. If it equals the "
        f"caller's cond-... alias, the executor rewrote nothing and the "
        f"request likely fell through to legacy routing."
    )

    assert call["operation"] == "openai_chat_completions", call
    assert call["stream"] is False
