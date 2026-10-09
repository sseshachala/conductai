"""#2403 item 1 — a repeated X-Request-Id must not dispatch or bill twice.

#2057 invariant 4: retries are idempotent or refused. The client key is
hashed with workspace + principal into the server request id; the
durable acceptance row's unique ``request_id`` index refuses the repeat
with 409 before any reservation or upstream dispatch.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.guard import gateway_lifecycle
from tests.guard._gateway_handler_char_helpers import gw  # noqa: F401 — fixture


@pytest.fixture
def unique_rows(gw, monkeypatch):
    """Model ``ux_guard_audit_events_request_id``: a repeated request id
    raises IntegrityError on insert, like Postgres does."""
    seen: set[str] = set()

    def _insert(*args, **kwargs):
        rid = kwargs["request_id"]
        if rid in seen:
            raise IntegrityError("INSERT", {}, Exception("ux_guard_audit_events_request_id"))
        seen.add(rid)
        gw.inserted.append(SimpleNamespace(args=args, kwargs=kwargs))
        return f"row-{len(gw.inserted)}"

    monkeypatch.setattr(gateway_lifecycle, "insert_accepted", _insert)
    return gw


@pytest.mark.asyncio
async def test_repeated_request_id_is_refused_without_second_dispatch_or_bill(unique_rows):
    gw = unique_rows
    headers = {"x-request-id": "client-retry-1"}
    first, _ = await gw.call(headers=headers)
    second, background = await gw.call(headers=headers)

    assert first.status_code == 200
    assert second.status_code == 409
    assert json.loads(second.body)["error"]["type"] == "conduct_gateway_duplicate_request"
    # The client learns which server request already owns this key.
    assert second.headers["x-conduct-request-id"] == first.headers["x-conduct-request-id"]
    # Exactly one dispatch, one reservation, one receipt, one commit.
    assert len(gw.sent) == 1
    assert len(gw.ledger.reserve_calls) == 1
    assert len(gw.receipts) == 1
    assert len(gw.ledger.commit_calls) == 1
    assert len(gw.finalized) == 1
    assert background.tasks == []
    assert gw.ticket.released  # admission slot not leaked by the refusal


@pytest.mark.asyncio
async def test_repeated_request_id_is_refused_with_durable_audit_off(unique_rows):
    """The key opts the request into durable acceptance: without a
    durable record there is nothing to dedupe against."""
    gw = unique_rows
    gw.durable(False)
    headers = {"x-request-id": "client-retry-2"}
    first, _ = await gw.call(headers=headers)
    second, _ = await gw.call(headers=headers)

    assert (first.status_code, second.status_code) == (200, 409)
    assert len(gw.sent) == 1 and len(gw.ledger.reserve_calls) == 1


@pytest.mark.asyncio
async def test_distinct_request_ids_both_dispatch(unique_rows):
    gw = unique_rows
    a, _ = await gw.call(headers={"x-request-id": "k-a"})
    b, _ = await gw.call(headers={"x-request-id": "k-b"})
    assert (a.status_code, b.status_code) == (200, 200)
    assert len(gw.sent) == 2
    assert a.headers["x-conduct-request-id"] != b.headers["x-conduct-request-id"]


@pytest.mark.asyncio
async def test_no_request_id_keeps_random_server_ids(unique_rows):
    gw = unique_rows
    a, _ = await gw.call()
    b, _ = await gw.call()
    assert (a.status_code, b.status_code) == (200, 200)
    assert len(gw.sent) == 2


def test_request_id_is_scoped_to_workspace_and_principal():
    from app.modules.guard.gateway_attempt_outcome import idempotent_request_id
    base = dict(workspace_id="ws-1", clerk_user_id="u-1", agent_identity_id="a-1", client_key="k")
    rid = idempotent_request_id(**base)
    assert rid == idempotent_request_id(**base)
    assert rid != idempotent_request_id(**{**base, "workspace_id": "ws-2"})
    assert rid != idempotent_request_id(**{**base, "clerk_user_id": "u-2"})
    assert rid != idempotent_request_id(**{**base, "agent_identity_id": "a-2"})
    assert idempotent_request_id(**{**base, "client_key": None}) is None
