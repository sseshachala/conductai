"""Verify the session-scoped agent_identity_id threads through gateway sigs.

Isolated (no DB) — inspects function signatures + PolicyContext population.
Exercises the wiring introduced by the #1252 PR.
"""
from __future__ import annotations

import inspect


def test_guarded_completion_accepts_agent_identity_id():
    from app.guard.gateway import guarded_completion
    sig = inspect.signature(guarded_completion)
    assert "agent_identity_id" in sig.parameters
    assert sig.parameters["agent_identity_id"].default is None


def test_guarded_llm_call_accepts_agent_identity_id():
    from app.guard.gateway import guarded_llm_call
    sig = inspect.signature(guarded_llm_call)
    assert "agent_identity_id" in sig.parameters
    assert sig.parameters["agent_identity_id"].default is None


def test_guarded_llm_stream_accepts_agent_identity_id():
    from app.guard.gateway import guarded_llm_stream
    sig = inspect.signature(guarded_llm_stream)
    assert "agent_identity_id" in sig.parameters
    assert sig.parameters["agent_identity_id"].default is None


def test_executor_accepts_and_stores_agent_identity_id():
    from app.modules.glens.executor import Executor
    sig = inspect.signature(Executor.__init__)
    assert "agent_identity_id" in sig.parameters

    # Behavioral: stored on instance, defaults None
    class _StubDb: pass
    ex = Executor(_StubDb(), "workspace-1")
    assert ex.agent_identity_id is None
    ex2 = Executor(_StubDb(), "workspace-1", agent_identity_id="ai-42")
    assert ex2.agent_identity_id == "ai-42"


def test_glens_chat_session_has_agent_identity_id_column():
    from app.modules.glens.models import GlensChatSession
    assert hasattr(GlensChatSession, "agent_identity_id")
