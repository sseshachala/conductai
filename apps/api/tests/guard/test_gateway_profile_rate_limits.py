"""Profile quota admission, settlement, validation, and stream cleanup."""
import base64
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from starlette.responses import StreamingResponse

from app.modules.guard import gateway_profile_rate_limit as limiter
from app.routers.gateway_profiles_v2 import ProfileRateLimitsBody


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_profile_limit_http_routes_reject_cross_workspace_urls(method):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.core.auth import get_workspace_id
    from app.core.database import get_db
    from app.routers.gateway_profiles_v2 import router

    app, db, ws = FastAPI(), MagicMock(), str(uuid4())
    app.include_router(router)
    app.dependency_overrides[get_workspace_id] = lambda: ws
    app.dependency_overrides[get_db] = lambda: db
    for route in app.routes:
        for dependency in getattr(getattr(route, "dependant", None), "dependencies", []):
            if getattr(dependency.call, "__qualname__", "").startswith("require_permission"):
                app.dependency_overrides[dependency.call] = lambda: "admin"
    with TestClient(app) as client:
        response = client.request(method, f"/workspaces/{uuid4()}/gateway-profiles-v2/{uuid4()}/rate-limits",
                                  **({"json": {"rpm": 2}} if method == "PUT" else {}))
    assert response.status_code == 404
    db.query.assert_not_called()


def test_profile_limit_routes_require_budget_edit_permission():
    import inspect
    from app.routers.gateway_profiles_v2 import router
    routes = [r for r in router.routes if r.path.endswith("/rate-limits")]
    assert len(routes) == 2
    for route in routes:
        permissions = [getattr(d.call, "__conduct_permission__", None) or inspect.getclosurevars(d.call).nonlocals.get("permission")
                       for d in route.dependant.dependencies if inspect.isfunction(d.call)]
        assert "guard.spend.budgets.edit" in permissions


class RedisStub:
    def __init__(self):
        self.values = {}
        self.lock = threading.Lock()

    def register_script(self, source):
        def script(*, keys, args):
            with self.lock:
                if source == limiter._ADMIT:
                    for i, key in enumerate(keys):
                        current = self.values.get(key, 0)
                        if current + args[2 * i + 2] > args[2 * i + 1]:
                            return [0, i + 1, current]
                    for i, key in enumerate(keys):
                        self.values[key] = self.values.get(key, 0) + args[2 * i + 2]
                    return [1]
                assert source == limiter._SETTLE
                for key in keys:
                    if key in self.values:
                        self.values[key] = max(0, self.values[key] + args[0])
                return 1
        return script


@pytest.fixture
def redis(monkeypatch):
    client = RedisStub()
    monkeypatch.setattr(limiter, "_redis_client", lambda: client)
    monkeypatch.setattr(limiter.time, "time", lambda: 1234)
    return client


def check(rows, *, workspace=None, profile=None, revision=None, agent=None, tokens=10):
    db = MagicMock()
    profile_query, agent_query = MagicMock(), MagicMock()
    profile_query.filter.return_value.all.return_value = [r for r in rows if r.agent_identity_id is None]
    agent_query.filter.return_value.all.return_value = [r for r in rows if r.agent_identity_id == agent and agent]
    db.query.side_effect = [profile_query, agent_query]
    return limiter.check_profile_rate_limit(
        db, workspace_id=str(workspace or uuid4()), profile_id=profile or uuid4(),
        revision_id=revision or uuid4(), agent_identity_id=agent, reserved_tokens=tokens,
    )


def cap(rpm=None, tpm=None, agent=None):
    return SimpleNamespace(rpm=rpm, tpm=tpm, agent_identity_id=agent)


def plan(payload=None, operation="openai_chat_completions", attempts=None):
    return SimpleNamespace(operation=operation, upstream_body=bytearray(json.dumps(payload).encode() if payload else b""),
                           last_meta={"attempts": attempts or [{"succeeded": True, "operation": operation}]})


def test_shared_quota_cannot_be_bypassed_by_switching_clients_agents_or_revisions(redis):
    ws, profile = uuid4(), uuid4()
    for agent in (None, str(uuid4())):
        assert not check([cap(rpm=2)], workspace=ws, profile=profile, agent=agent).limited
    blocked = check([cap(rpm=2)], workspace=ws, profile=profile, revision=uuid4(), agent=str(uuid4()))
    assert blocked.limited and blocked.metric == "rpm" and blocked.scope == "profile"
    assert blocked.retry_after == 26 and list(redis.values.values()) == [2]
    assert not check([cap(rpm=2)], workspace=ws, profile=uuid4()).limited


def test_atomic_burst_never_overshoots_or_charges_rejected_calls(redis):
    ws, profile = uuid4(), uuid4()
    with ThreadPoolExecutor(max_workers=16) as pool:
        decisions = list(pool.map(lambda _: check([cap(rpm=5, tpm=100)], workspace=ws, profile=profile), range(40)))
    assert sum(not d.limited for d in decisions) == 5
    assert sorted(redis.values.values()) == [5, 50]


def test_agent_caps_are_additional_not_overrides(redis):
    ws, profile, agent = uuid4(), uuid4(), str(uuid4())
    rows = [cap(rpm=2, tpm=100), cap(rpm=100, tpm=1000, agent=agent)]
    assert not check(rows, workspace=ws, profile=profile, agent=agent).limited
    assert not check(rows, workspace=ws, profile=profile, agent=agent).limited
    assert check(rows, workspace=ws, profile=profile, agent=agent).scope == "profile"
    smaller = check([cap(rpm=100), cap(tpm=5, agent=agent)], workspace=ws, profile=uuid4(), agent=agent)
    assert smaller.limited and smaller.scope == "agent"


def test_agent_rpm_is_shared_across_profiles_clients_and_revisions(redis):
    ws, first, second, identity = uuid4(), uuid4(), uuid4(), str(uuid4())
    rows = [cap(rpm=100), cap(rpm=2, agent=identity)]
    assert not check(rows, workspace=ws, profile=first, agent=identity).limited
    assert not check(rows, workspace=ws, profile=second, agent=identity).limited
    blocked = check(rows, workspace=ws, profile=uuid4(), revision=uuid4(), agent=identity)
    assert blocked.limited and blocked.scope == "agent" and blocked.metric == "rpm"
    assert len(redis.values) == 3  # The refused profile was never charged.
    assert sorted(redis.values.values()) == [1, 1, 2]
    assert not check([cap(rpm=2, agent="other")], workspace=ws, profile=first, agent="other").limited
    assert not check(rows, workspace=uuid4(), profile=first, agent=identity).limited
    assert all("{" + str(ws) + "}" in key for key in redis.values if ":agent:other:" not in key and str(ws) in key)


def test_agent_tpm_settles_usage_across_profiles_and_rejected_calls_charge_neither(redis):
    ws, identity = uuid4(), str(uuid4())
    rows = [cap(tpm=1000), cap(tpm=100, agent=identity)]
    accepted = check(rows, workspace=ws, profile=uuid4(), agent=identity, tokens=90)
    limiter.settle_profile_rate_limit(accepted.admission, plan({"usage": {"prompt_tokens": 10, "completion_tokens": 5}}))
    assert sorted(redis.values.values()) == [15, 15]
    assert not check(rows, workspace=ws, profile=uuid4(), agent=identity, tokens=80).limited
    before = dict(redis.values)
    blocked = check(rows, workspace=ws, profile=uuid4(), agent=identity, tokens=6)
    assert blocked.limited and blocked.scope == "agent" and blocked.metric == "tpm"
    assert redis.values == before


def test_profile_and_agent_keys_share_a_redis_cluster_slot(redis):
    identity = str(uuid4())
    admitted = check([cap(rpm=10, tpm=100), cap(rpm=10, tpm=100, agent=identity)], agent=identity)
    keys = list(redis.values)
    assert len(keys) == 4 and len({key.split("{")[1].split("}")[0] for key in keys}) == 1
    assert admitted.admission is not None


def test_tpm_reserves_input_plus_output_and_rejects_without_charging(redis):
    ws, profile = uuid4(), uuid4()
    assert not check([cap(tpm=100)], workspace=ws, profile=profile, tokens=70).limited
    rejected = check([cap(tpm=100)], workspace=ws, profile=profile, tokens=40)
    assert rejected.limited and rejected.metric == "tpm"
    assert list(redis.values.values()) == [70]


@pytest.mark.parametrize("operation", ["anthropic_messages", "openai_chat_completions", "openai_responses", "anthropic_count_tokens"])
def test_token_count_requests_do_not_reserve_generation_allowance(operation):
    from app.runtime.accounting.estimator import estimate_tokens
    body = {"messages": [{"role": "user", "content": "Say hello"}], "max_tokens": 10}
    estimate = estimate_tokens(body)
    expected = estimate.input_tokens + (0 if operation == "anthropic_count_tokens" else estimate.output_tokens_allowance)
    assert limiter.reserved_profile_tokens(body, operation) == expected


@pytest.mark.parametrize("operation,payload,expected", [
    ("openai_chat_completions", {"usage": {"prompt_tokens": 10, "completion_tokens": 3}}, 13),
    ("openai_responses", {"usage": {"input_tokens": 10, "output_tokens": 4}}, 14),
    ("anthropic_messages", {"usage": {"input_tokens": 10, "output_tokens": 5,
        "cache_read_input_tokens": 7, "cache_creation_input_tokens": 8}}, 30),
    ("anthropic_count_tokens", {"input_tokens": 12}, 12),
])
def test_all_operations_settle_actual_input_output_and_cache_tokens(redis, operation, payload, expected):
    identity = str(uuid4())
    admitted = check([cap(tpm=1000), cap(tpm=1000, agent=identity)], agent=identity, tokens=100).admission
    limiter.settle_profile_rate_limit(admitted, plan(payload, operation))
    assert sorted(redis.values.values()) == [expected, expected]
    limiter.settle_profile_rate_limit(admitted, plan(payload, operation))
    assert sorted(redis.values.values()) == [expected, expected]


def test_failed_attempt_usage_is_not_dropped_before_fallback(redis):
    failed = {"succeeded": False, "operation": "openai_chat_completions", "response_bytes_b64":
        base64.b64encode(json.dumps({"usage": {"prompt_tokens": 10, "completion_tokens": 1}}).encode()).decode()}
    admitted = check([cap(tpm=1000)], tokens=100).admission
    limiter.settle_profile_rate_limit(admitted, plan({"usage": {"prompt_tokens": 20, "completion_tokens": 2}},
        attempts=[failed, {"succeeded": True}]))
    assert list(redis.values.values()) == [33]


def test_missing_usage_keeps_reservation_and_partial_known_usage_is_a_floor(redis):
    admitted = check([cap(tpm=1000)], tokens=100).admission
    limiter.settle_profile_rate_limit(admitted, plan({"choices": []}))
    assert list(redis.values.values()) == [100]
    assert limiter.actual_profile_tokens(plan({"usage": {"prompt_tokens": 150}}), 100) == 150


def test_predispatch_failure_refunds_tpm_but_keeps_rpm(redis):
    admitted = check([cap(rpm=10, tpm=1000)], tokens=100).admission
    limiter.settle_profile_rate_limit(admitted, SimpleNamespace(last_meta={}))
    assert sorted(redis.values.values()) == [0, 1]


def test_cancellation_before_attempt_metadata_keeps_reservation():
    assert limiter.actual_profile_tokens(SimpleNamespace(last_meta={}, dispatched=True), 100) == 100


def test_policy_refusals_before_vendor_dispatch_do_not_charge_tokens():
    assert limiter.actual_profile_tokens(plan(attempts=[{"succeeded": False, "error_class": "PolicyBlock"}]), 100) == 0


def test_translated_fallback_uses_provider_usage_shape():
    assert limiter.actual_profile_tokens(plan({"usage": {"prompt_tokens": 10, "completion_tokens": 3}},
        operation="anthropic_messages"), 100) == 13


def test_no_limits_do_not_require_redis(monkeypatch):
    client = MagicMock(side_effect=RuntimeError("offline"))
    monkeypatch.setattr(limiter, "_redis_client", client)
    assert not check([]).limited
    client.assert_not_called()


def test_configured_limits_fail_closed_on_redis_outage(monkeypatch):
    monkeypatch.setattr(limiter, "_redis_client", MagicMock(side_effect=RuntimeError("offline")))
    decision = check([cap(rpm=2)])
    assert decision.limited and decision.status == 503 and decision.metric == "availability"


def test_lookup_failure_does_not_silently_disable_limits():
    db = MagicMock()
    db.query.side_effect = RuntimeError("unavailable")
    decision = limiter.check_profile_rate_limit(db, workspace_id=str(uuid4()), profile_id=uuid4(),
        revision_id=uuid4(), agent_identity_id=None, reserved_tokens=1)
    assert decision.limited and decision.status == 503


@pytest.mark.parametrize("value", [0, -1, 1.5, "2", True, 2147483648])
def test_api_cap_validation_is_strict(value):
    with pytest.raises(ValidationError):
        ProfileRateLimitsBody(rpm=value)


@pytest.mark.asyncio
async def test_stream_settles_only_after_drain_and_closes_upstream(redis):
    upstream_plan = plan({"usage": {"prompt_tokens": 2, "completion_tokens": 3}})
    admitted = check([cap(tpm=1000)], tokens=100).admission
    closed = []

    async def upstream():
        try:
            yield b"data: first\n\n"
            yield b"data: second\n\n"
        finally:
            closed.append(True)

    response = limiter.wrap_profile_rate_stream(StreamingResponse(upstream()), admitted, upstream_plan)
    iterator = response.body_iterator
    assert await anext(iterator) == b"data: first\n\n"
    assert not admitted.finished
    assert [chunk async for chunk in iterator] == [b"data: second\n\n"]
    assert admitted.finished and closed and list(redis.values.values()) == [5]


@pytest.mark.asyncio
async def test_disconnect_preserves_unknown_usage_and_closes_upstream(redis):
    admitted = check([cap(tpm=1000)], tokens=100).admission
    closed = []

    async def upstream():
        try:
            yield b"data: chunk\n\n"
        finally:
            closed.append(True)

    response = limiter.wrap_profile_rate_stream(StreamingResponse(upstream()), admitted, plan())
    await anext(response.body_iterator)
    await response.body_iterator.aclose()
    assert admitted.finished and closed and list(redis.values.values()) == [100]
