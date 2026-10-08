"""Shared harness for ``_execute_brain`` tests (#2170, #2400, #2401).

Single home for brain-block test fixtures. ``_wf_row`` / ``_profile_row``
/ ``_dispatch_db`` moved here from test_brain_block_gateway_profile_routing
so the characterization tests can reuse them without copying.

``brain_harness`` patches only stable seams ``_execute_brain`` looks up:

- ``app.runtime.blocks.brain_block.<name>``: model router, LLM replay
  cache, MCP tool loader.
- ``GatewayProfileClient.create`` — the only model-call path (#2170). The
  real class is constructed, so ``routes_through_gateway`` and the real
  ``make_assistant_turn`` / ``make_tool_results_turn`` shapes run; only
  the network call is scripted.
- ``app.runtime.runtime._emit`` / ``_write_trace``.
- ``app.runtime.dag_runner._checkpoint_state`` (turn checkpoint).
- Guard: ``mcp_helpers.compute_policy`` (raw rules), so the real
  ``_get_rules`` → ``_project_rule`` projection runs; and
  ``notify_guard_block``.
- Memory: ``memory_block._execute_memory*`` are spied only to prove
  ``_execute_brain`` never calls them (memory is its own block type).

Pricing is not patched: ``freeze_pricing_snapshot`` / ``get_model_rates``
are pure, so tests compare against ``expected_pricing()``.
"""
from __future__ import annotations

import copy
import uuid
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator
from unittest.mock import MagicMock, patch

from app.runtime.llm_client import (
    LLMResponse,
    LLMTextBlock,
    LLMToolUseBlock,
    LLMUsage,
)

WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
WORKFLOW_ID = "22222222-2222-4222-8222-222222222222"
RUN_ID = "33333333-3333-4333-8333-333333333333"
BLOCK_ID = "brain-1"
MODEL = "claude-test"
PROVIDER = "anthropic"
ROUTING_REASON = "explicit"
PROFILE_COND_CODE = "ABC12345"
PROFILE_ALIAS = "default"
FILES_CHANGED = ["src/app.py"]
DIFF_STAT = "1 file changed, 2 insertions(+)"

BB = "app.runtime.blocks.brain_block"


# ── DB fixtures (shared with test_brain_block_gateway_profile_routing) ──


def _wf_row(gateway_profile_id):
    row = MagicMock()
    row.gateway_profile_id = gateway_profile_id
    return row


def _profile_row(*, id=None, cond_code="ABC12345", model_alias="default", active=True):
    row = MagicMock()
    row.id = id or uuid.uuid4()
    row.cond_code = cond_code
    row.model_alias = model_alias
    row.active_revision_id = uuid.uuid4() if active else None
    row.name = f"profile-{cond_code}"
    return row


def _dispatch_db(*, wf_row, prof_row, revision_snapshot: dict | None = None):
    """Return a MagicMock db whose ``query`` dispatches by ORM model."""
    from app.models.workflow import Workflow as _WF
    from app.models.gateway_profile import (
        GatewayProfile as _GP,
        GatewayProfileRevision as _GPR,
    )

    wf_q = MagicMock()
    wf_q.filter.return_value.first.return_value = wf_row
    prof_q = MagicMock()
    prof_q.filter.return_value.first.return_value = prof_row

    # #2170 PR 3 — brain_block queries the revision snapshot to decide
    # per-profile streaming safety. Provide a minimal snapshot so those
    # code paths don't get MagicMock objects.
    rev_row = MagicMock()
    rev_row.snapshot = revision_snapshot or {"targets": []}
    rev_q = MagicMock()
    rev_q.filter.return_value.first.return_value = rev_row

    db = MagicMock()

    def _q(model):
        if model is _WF:
            return wf_q
        if model is _GP:
            return prof_q
        if model is _GPR:
            return rev_q
        return MagicMock()

    db.query.side_effect = _q
    return db


def mcp_server_row(name: str, url: str = "https://mcp.example.test"):
    row = MagicMock()
    row.id = uuid.uuid4()
    row.name = name
    row.url = url
    row.encrypted_auth = None
    row.transport = "auto"
    return row


def make_db(*, assigned: bool = True, mcp_servers: list | None = None):
    """``_dispatch_db`` plus ``Run`` (records updates) and ``McpServer``."""
    from app.models.mcp_server import McpServer
    from app.models.run import Run

    prof = _profile_row(cond_code=PROFILE_COND_CODE, model_alias=PROFILE_ALIAS)
    db = _dispatch_db(
        wf_row=_wf_row(prof.id if assigned else None),
        prof_row=prof if assigned else None,
    )
    run_q = MagicMock(name="run_query")
    mcp_q = MagicMock(name="mcp_query")
    mcp_q.filter.return_value.all.return_value = list(mcp_servers or [])
    base = db.query.side_effect
    by_model = {Run: run_q, McpServer: mcp_q}
    db.query.side_effect = lambda model: by_model.get(model) or base(model)
    return db, run_q


def expected_pricing() -> tuple[dict, str]:
    """Real (rates, version) the function reports for MODEL."""
    from app.runtime.pricing import freeze_pricing_snapshot, get_model_rates

    return get_model_rates(PROVIDER, MODEL, freeze_pricing_snapshot())


# ── LLM response builders ────────────────────────────────────────────


def text_response(text: str, *, cost: float = 0.001, inp: int = 10,
                  out: int = 5, stop: str = "end_turn") -> LLMResponse:
    return LLMResponse(
        content=[LLMTextBlock(text=text)],
        stop_reason=stop,
        usage=LLMUsage(input_tokens=inp, output_tokens=out),
        cost_usd=cost,
        _raw_content={"role": "assistant", "content": text},
    )


def tool_response(*calls: tuple[str, str, dict], text: str = "",
                  cost: float = 0.001, inp: int = 10, out: int = 5,
                  correlation_ids: dict | None = None) -> LLMResponse:
    """``calls`` = (tool_use_id, tool_name, input) triples."""
    content: list = [LLMTextBlock(text=text)] if text else []
    content.extend(LLMToolUseBlock(id=i, name=n, input=x) for i, n, x in calls)
    return LLMResponse(
        content=content,
        stop_reason="tool_use",
        usage=LLMUsage(input_tokens=inp, output_tokens=out),
        cost_usd=cost,
        _raw_content={
            "role": "assistant", "content": text,
            "tool_calls": [{"id": i, "type": "function",
                            "function": {"name": n, "arguments": "{}"}}
                           for i, n, _ in calls],
        },
        correlation_ids=correlation_ids or {},
    )


# ── Recorder + fakes ─────────────────────────────────────────────────


class FakeSession:
    """Stand-in sandbox session (passed as ``injected_session``)."""

    def __init__(self, outputs: dict[str, str] | None = None):
        self.outputs = outputs or {}
        self.dispatched: list[tuple[str, dict]] = []
        self.close_calls = 0
        self.capture_calls = 0
        self.captured_after_close = False

    def dispatch(self, tool_name: str, tool_input: dict) -> str:
        self.dispatched.append((tool_name, copy.deepcopy(tool_input)))
        return self.outputs.get(tool_name, f"ok:{tool_name}")

    def capture_artifacts(self):
        self.capture_calls += 1
        if self.close_calls:
            self.captured_after_close = True
        return list(FILES_CHANGED), DIFF_STAT

    def close(self):
        self.close_calls += 1


@dataclass
class Harness:
    script: list
    db: Any = None
    run_q: Any = None
    session: FakeSession = field(default_factory=FakeSession)
    llm_calls: list[dict] = field(default_factory=list)
    client_kwargs: list[dict] = field(default_factory=list)
    emits: list[tuple[str, dict]] = field(default_factory=list)
    traces: list[tuple] = field(default_factory=list)
    checkpoints: list[dict] = field(default_factory=list)
    rule_lookups: list = field(default_factory=list)
    notifies: list[dict] = field(default_factory=list)
    memory_calls: list = field(default_factory=list)
    mcp_tool_loads: list = field(default_factory=list)
    sessions_created: list = field(default_factory=list)
    mcp_calls: list = field(default_factory=list)

    def kinds(self) -> list[str]:
        return [k for k, _ in self.emits]

    def emitted(self, kind: str) -> list[dict]:
        return [p for k, p in self.emits if k == kind]

    def run_updates(self) -> list[dict]:
        """Every ``Run`` row update (``_record_turns``) in call order."""
        upd = self.run_q.filter.return_value.update
        return [c.args[0] for c in upd.call_args_list]

    def audit_rows(self) -> list:
        return [c.args[0] for c in self.db.add.call_args_list
                if type(c.args[0]).__name__ == "GuardAuditEvent"]


@contextmanager
def brain_harness(script: list, *, raw_rules: list[dict] | None = None,
                  assigned: bool = True, mcp_servers: list | None = None,
                  session_outputs: dict[str, str] | None = None) -> Iterator[Harness]:
    """Patch every seam ``_execute_brain`` touches; yield the recorder.

    ``script`` items are returned by successive ``create()`` calls; an
    exception item is raised instead. ``raw_rules`` are un-projected
    policy rules as ``compute_policy`` returns them.
    """
    from app.runtime.adapters.gateway_profile import GatewayProfileClient

    db, run_q = make_db(assigned=assigned, mcp_servers=mcp_servers)
    h = Harness(script=list(script), db=db, run_q=run_q,
                session=FakeSession(session_outputs))
    orig_init = GatewayProfileClient.__init__

    def _init(self, **kw):
        h.client_kwargs.append(kw)
        orig_init(self, **kw)

    def _create(self, **kw):
        h.llm_calls.append({**kw, "messages": copy.deepcopy(kw.get("messages"))})
        if not h.script:
            raise AssertionError("LLM script exhausted — unexpected extra turn")
        item = h.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def _emit(db_, run_id, block_id, kind, payload):
        h.emits.append((kind, copy.deepcopy(payload)))

    def _trace(db_, run_id, block_id, turn, role, **kw):
        h.traces.append((turn, role, kw))

    def _ckpt(run_id, state, **kw):
        h.checkpoints.append({"run_id": run_id, "state_keys": sorted(state), **kw})

    def _policy(db_, ws_uuid, persona):
        h.rule_lookups.append((str(ws_uuid), persona))
        return copy.deepcopy(raw_rules or [])

    def _notify(db_, workspace_id, **kw):
        h.notifies.append({"workspace_id": workspace_id, **kw})

    def _mem(*a, **kw):
        h.memory_calls.append((a, kw))
        return {}

    def _mcp_tools(*a, **kw):
        h.mcp_tool_loads.append((a, kw))
        return []

    def _mcp_call(url, token, tool_name, tool_input, transport="auto"):
        h.mcp_calls.append((url, tool_name, copy.deepcopy(tool_input)))
        return {"ok": True, "tool": tool_name}

    def _create_session(*a, **kw):
        h.sessions_created.append((a, kw))
        return h.session

    patches = [
        patch(f"{BB}._router_resolve",
              lambda *a, **k: (PROVIDER, MODEL, ROUTING_REASON)),
        patch(f"{BB}._cache_get", lambda *a, **k: None),
        patch(f"{BB}._cache_set", lambda *a, **k: None),
        patch(f"{BB}._load_workspace_mcp_tools", _mcp_tools),
        patch.object(GatewayProfileClient, "__init__", _init),
        patch.object(GatewayProfileClient, "create", _create),
        patch("app.runtime.runtime._emit", _emit),
        patch("app.runtime.runtime._write_trace", _trace),
        patch("app.runtime.dag_runner._checkpoint_state", _ckpt),
        patch("app.runtime.sandbox._modal_available", lambda: False),
        patch("app.runtime.sandbox_session.create_session", _create_session),
        patch("app.runtime.integrations.mcp_client.call_tool", _mcp_call),
        patch("app.modules.guard.routers.mcp_helpers.compute_policy", _policy),
        patch("app.modules.guard.routers.events.notify_guard_block", _notify),
        patch("app.runtime.blocks.memory_block._execute_memory", _mem),
        patch("app.runtime.blocks.memory_block._execute_memory_inner", _mem),
    ]
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        yield h


# ── Block / state builders + runner ──────────────────────────────────


def brain_block(*, agentic: bool, **data: Any) -> dict:
    base = {
        "type": "brain",
        "isAgentic": agentic,
        "description": "You are a characterization-test brain block.",
        "prompt": "Summarise {{ticket.title}}",
        "config": {},
    }
    base.update(data)
    return {"id": BLOCK_ID, "data": base}


def base_state(**extra: Any) -> dict:
    state = {"ticket": {"title": "Fix flaky test"}, "__inputs": {}}
    state.update(extra)
    return state


def run_brain(h: Harness, block: dict, state: dict, **overrides: Any) -> dict:
    from app.runtime.blocks.brain_block import _execute_brain

    kwargs: dict = dict(
        credentials=None, db=h.db, run_id=RUN_ID, block_id=BLOCK_ID,
        playbook_slug="char-playbook", injected_session=h.session,
        workspace_id=WORKSPACE_ID, workflow_id=WORKFLOW_ID,
        user_email="dev@example.com", block_label="Brain",
        workflow_name="Char Workflow", environment_id=None,
        attempt_id="attempt-1",
    )
    kwargs.update(overrides)
    return _execute_brain(block, state, {}, **kwargs)
