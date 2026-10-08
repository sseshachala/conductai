"""Shared harness for the ``handle_gateway_request`` characterization suite (#2399).

The suite pins today's observable behaviour of the gateway hot path so the
#2399 refactor (split the ~1535-line function into phase functions) can prove
"no behaviour change". Every test drives the REAL ``handle_gateway_request``
end to end; only these boundaries are replaced:

- auth DB lookup        ``gateway_helpers._resolve_gateway_auth`` (or the
                        ``app.core.auth`` token resolvers it calls)
- policy engine         ``app.guard.policy.evaluate_composed``
- v2 profile lookup     ``gateway_handler._build_v2_plan_owned`` (real
                        ``_V2Plan`` + real ``GatewayProfileV2``)
- vendor HTTP           ``httpx.AsyncClient.send`` behind a REAL
                        ``AttemptCoordinator`` + ``NativeHTTPTransport``
                        (same pattern as ``test_gateway_transport_matrix``)
- durable audit SQL     ``gateway_lifecycle.insert_accepted`` / ``.finalize``
- budget ledger         ``app.core.budget_ledger`` + ``spend_lookup`` (the
                        real ``reserve_budgets_for_request`` /
                        ``settle_reservations`` run on top)
- receipts writer       ``shadow_writer.write_receipts_for_attempts``

Patch targets resolve at call time, so the same tests pass before and after
#2396 (which moved helpers but re-exported every name).
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from fastapi import BackgroundTasks
from starlette.requests import Request

from app.core.config import settings
from app.guard.policy_types import PolicyAction, PolicyDecision
from app.modules.guard import gateway_handler, gateway_helpers, gateway_lifecycle
from app.modules.guard.gateway_config import GatewayProfileV2
from app.modules.guard.gateway_profile_rate_limit import ProfileRateDecision
from app.runtime.attempt_coordinator import AttemptCoordinator
from app.runtime.native_http_transport import NativeHTTPTransport

WS = "11111111-1111-4111-8111-111111111111"
IDENTITY = "22222222-2222-4222-8222-222222222222"
PROFILE_ID = "33333333-3333-4333-8333-333333333333"
REVISION = UUID("44444444-4444-4444-8444-444444444444")
MEMBER = "member-fixture"
TOKEN = "cond_agt_fixture_token"
COND_MODEL = "cond-abcdefgh-coding"
PATH = "/gateway/v1/openai/v1/chat/completions"
ENV = "55555555-5555-4555-8555-555555555555"

CHAT = {"id": "chatcmpl_fixture", "object": "chat.completion", "created": 1, "model": "gpt-4o",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}}
SSE_CHUNKS = [
    b'data: {"id":"c1","object":"chat.completion.chunk","created":1,"model":"gpt-4o",'
    b'"choices":[{"index":0,"delta":{"role":"assistant","content":"OK"},"finish_reason":null}]}\n\n',
    b'data: {"id":"c1","object":"chat.completion.chunk","created":1,"model":"gpt-4o",'
    b'"choices":[{"index":0,"delta":{},"finish_reason":"stop"}],'
    b'"usage":{"prompt_tokens":5,"completion_tokens":2,"total_tokens":7}}\n\n',
    b"data: [DONE]\n\n",
]


def ok_json(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=CHAT)


def ok_sse(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, request=request, headers={"content-type": "text/event-stream"},
                          stream=_ChunkStream(SSE_CHUNKS))


def status(code: int, message: str = "fixture upstream error") -> Callable:
    return lambda request: httpx.Response(code, json={"error": {"message": message, "type": "fixture"}})


def raises(exc_factory: Callable[[httpx.Request], BaseException]) -> Callable:
    def _r(request):
        raise exc_factory(request)
    return _r


class _ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        self.closed = True


class FakeTicket:
    """Admission ticket double — records release/defer ordering."""

    def __init__(self):
        self.released = False
        self.deferred = False
        self.release_calls = 0

    async def release(self):
        self.release_calls += 1
        self.released = True

    def defer(self):
        self.deferred = True


@dataclass
class FakeReservation:
    reservation_id: str
    estimated_micros: int = 10_000


class FakeLedger:
    """Budget-ledger double. ``decision`` is a ``BudgetDecision`` name."""

    def __init__(self, decision: str = "ACCEPTED", reservations: int = 1):
        self.decision = decision
        self.reservations = [FakeReservation(f"res-{i}") for i in range(reservations)]
        self.reserve_calls: list[dict] = []
        self.commit_calls: list[dict] = []
        self.release_calls: list[dict] = []

    def reserve_all(self, **kwargs):
        from app.core.budget_ledger import BudgetDecision
        self.reserve_calls.append(kwargs)
        decision = BudgetDecision[self.decision]
        if decision is BudgetDecision.ACCEPTED:
            return decision, list(self.reservations), None
        refusing = SimpleNamespace(ai_tool="cursor", hard_limit_usd=0.01)
        return decision, None, refusing if self.decision == "EXCEEDED" else None

    def commit_all(self, **kwargs):
        self.commit_calls.append(kwargs)

    def release_all(self, **kwargs):
        self.release_calls.append(kwargs)


def policy(action: str = "ALLOW", *, source: str = "rule", rule_id: str | None = None,
           reason: str | None = None, gate: str = "prompt") -> Callable:
    """Composed-engine double: ``action`` applies to ``gate`` only, ALLOW elsewhere."""
    def _eval(ctx):
        if getattr(ctx, "gate", "prompt") == gate:
            return PolicyDecision(action=PolicyAction[action], source=source,
                                  rule_id=rule_id, reason=reason)
        return PolicyDecision(action=PolicyAction.ALLOW, source="rule")
    return _eval


def profile(*models: str, timeout_seconds: int = 60) -> GatewayProfileV2:
    targets = [{"id": f"t{i}", "transport": "native_http", "provider": "openai", "model": m,
                "credential_ref": f"vault://{ENV}/openai"} for i, m in enumerate(models or ("gpt-4o",))]
    return GatewayProfileV2(name="fixture-profile", model_alias="coding", accepts=["openai_chat_completions"],
                            timeout_seconds=timeout_seconds, max_attempts=len(targets), targets=targets)


@dataclass
class Harness:
    monkeypatch: pytest.MonkeyPatch
    upstream: list = field(default_factory=lambda: [ok_json])
    sent: list = field(default_factory=list)
    policy_ctx: list = field(default_factory=list)
    inserted: list = field(default_factory=list)
    finalized: list = field(default_factory=list)
    receipts: list = field(default_factory=list)
    ledger: FakeLedger = field(default_factory=FakeLedger)
    ticket: FakeTicket = field(default_factory=FakeTicket)
    plan: Any = None
    auth: MagicMock = None
    real_auth: Callable = None
    native: NativeHTTPTransport = field(default_factory=NativeHTTPTransport)

    # ── configuration ────────────────────────────────────────────────
    def set_policy(self, fn: Callable) -> None:
        def _eval(ctx):
            self.policy_ctx.append(ctx)
            return fn(ctx)
        self.monkeypatch.setattr("app.guard.policy.evaluate_composed", _eval)

    def set_profile(self, prof: GatewayProfileV2) -> None:
        def _build(**kwargs):
            self.plan = gateway_handler._V2Plan(
                SimpleNamespace(profile=prof, revision_id=REVISION, profile_id=PROFILE_ID),
                "openai_chat_completions", lambda ref: "fixture-vendor-key")
            return self.plan
        self.monkeypatch.setattr(gateway_handler, "_build_v2_plan_owned", _build)

    def durable(self, on: bool) -> None:
        self.monkeypatch.setattr(type(settings), "durable_audit_enabled_for", lambda self_, ws: on)

    def ledger_enabled(self, on: bool) -> None:
        self.monkeypatch.setattr("app.core.budget_ledger.enabled", lambda *a, **k: on)
        self.monkeypatch.setattr("app.core.budget_ledger.enabled_for", lambda *a, **k: on)

    # ── execution ────────────────────────────────────────────────────
    async def call(self, body: dict | None = None, *, headers: dict | None = None,
                   provider: str = "openai", path: str = PATH,
                   upstream_path: str = "/v1/chat/completions"):
        body = {"model": COND_MODEL, "messages": [{"role": "user", "content": "hello"}]} if body is None else body
        raw = json.dumps(body).encode()

        async def receive():
            return {"type": "http.request", "body": raw, "more_body": False}

        hdrs = {"authorization": f"Bearer {TOKEN}", **(headers or {})}
        request = Request({
            "type": "http", "method": "POST", "path": path, "scheme": "https",
            "server": ("fixture", 443), "query_string": b"",
            "headers": [(k.lower().encode(), v.encode()) for k, v in hdrs.items() if v is not None],
        }, receive)
        background = BackgroundTasks()
        response = await gateway_handler.handle_gateway_request(
            request, background, provider=provider, upstream_path=upstream_path,
            auth_header_in="authorization", auth_header_out="authorization", bearer=True)
        return response, background


def audit_tasks(background: BackgroundTasks) -> list[SimpleNamespace]:
    """Queued background audit writes as (func name, positional args, kwargs)."""
    return [SimpleNamespace(name=getattr(t.func, "__name__", repr(t.func)), args=t.args, kwargs=t.kwargs)
            for t in background.tasks]


async def drain(response) -> bytes:
    return b"".join([chunk async for chunk in response.body_iterator])


@pytest_asyncio.fixture
async def gw(monkeypatch):
    """Fully wired harness: allowed v2 request, durable audit ON, ledger ON (1 reservation)."""
    h = Harness(monkeypatch=monkeypatch)
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    monkeypatch.setattr(type(settings), "gateway_profile_v2_enabled_for", lambda self_, ws: True)
    monkeypatch.setattr(settings, "guard_durable_audit_stream_renew_seconds", 0)
    h.durable(True)
    h.ledger_enabled(True)
    monkeypatch.setattr("app.core.auth_cache.get_auth_cache", lambda: None)
    h.real_auth = gateway_helpers._resolve_gateway_auth
    h.auth = MagicMock(return_value=SimpleNamespace(
        workspace_id=WS, clerk_user_id=MEMBER, is_internal=False,
        agent_identity_id=IDENTITY, agent_risk_tier="standard"))
    monkeypatch.setattr(gateway_helpers, "_resolve_gateway_auth", h.auth)
    monkeypatch.setattr("app.modules.auth.federation.gateway.prepare_gateway", lambda *a: None)
    monkeypatch.setattr("app.core.admission._acquire", AsyncMock(return_value=h.ticket))
    monkeypatch.setattr(gateway_helpers, "_apply_tier_resolution_owned", lambda ws, p, body: (body.get("model"), None))
    monkeypatch.setattr(gateway_helpers, "_lookup_user_email", lambda *a: "member@example.test")
    monkeypatch.setattr(gateway_helpers, "_lookup_workspace_trial", lambda *a: (None, None))
    monkeypatch.setattr("app.core.database.SessionLocal", MagicMock)
    monkeypatch.setattr("app.modules.guard.routers._proxy_helpers.SessionLocal", MagicMock)
    monkeypatch.setattr("app.core.workspace_context.set_workspace_rls", lambda *a, **k: None)
    monkeypatch.setattr("app.modules.guard.gateway_profile_rate_limit.check_profile_rate_limit",
                        MagicMock(return_value=ProfileRateDecision()))
    h.set_policy(policy("ALLOW"))
    h.set_profile(profile("gpt-4o"))

    def _insert(*args, **kwargs):
        h.inserted.append(SimpleNamespace(args=args, kwargs=kwargs))
        return f"row-{len(h.inserted)}"

    def _finalize(row_id, workspace_id, **kwargs):
        h.finalized.append({"row_id": row_id, "workspace_id": workspace_id, **kwargs})

    monkeypatch.setattr(gateway_lifecycle, "insert_accepted", _insert)
    monkeypatch.setattr(gateway_lifecycle, "finalize", _finalize)
    monkeypatch.setattr("app.core.budget_ledger.get_budget_ledger", lambda: h.ledger)
    monkeypatch.setattr("app.modules.guard.spend_lookup.lookup_applicable_budgets",
                        lambda *a, **k: [SimpleNamespace(hard_cap_enabled=True, hard_limit_usd=5.0, ai_tool=None)])

    def _receipts(**kwargs):
        h.receipts.append(kwargs)
        return [uuid.uuid4() for _ in (kwargs.get("attempts_meta") or [None])]

    monkeypatch.setattr("app.runtime.accounting.shadow_writer.write_receipts_for_attempts", _receipts)

    async def _send(client, request, **kwargs):
        h.sent.append(request)
        responder = h.upstream[min(len(h.sent), len(h.upstream)) - 1]
        response = responder(request)
        if hasattr(response, "__await__"):
            response = await response
        response.request = request
        if not kwargs.get("stream"):
            await response.aread()
        return response

    monkeypatch.setattr(httpx.AsyncClient, "send", _send)
    coordinator = AttemptCoordinator(native_http_transport=h.native)
    monkeypatch.setattr("app.runtime.gateway_transports.get_coordinator", AsyncMock(return_value=coordinator))
    try:
        yield h
    finally:
        if h.native._client is not None:
            await h.native._client.aclose()
