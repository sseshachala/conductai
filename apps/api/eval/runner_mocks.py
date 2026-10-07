"""Mocked live-execution harness for the eval runner (split from runner.py).

Runs a playbook through the real DAG executor against in-memory run / version /
DB stand-ins with integration calls patched out.
"""
from __future__ import annotations
import logging
from typing import Any
from eval.fixtures import (
    PlaybookFixture,
)

try:
    import structlog
    log = structlog.get_logger("eval.runner")
except ImportError:
    log = logging.getLogger("eval.runner")


def _execute_with_mocks(
    fixture: PlaybookFixture,
    playbook_yaml: str,
    model: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """
    Build a mock run context and call the executor directly.

    Parameters
    ----------
    api_key:
        When provided, the AnthropicClient is patched to use this key for the
        duration of the call.  The patch is scoped to the ``with`` block so
        concurrent callers with different keys never interfere.

    Returns a dict with keys: status, outcome, state.
    """
    import uuid

    # Build a fake run object
    run_id = uuid.uuid4()
    mock_run = _make_mock_run(run_id, fixture)
    mock_version = _make_mock_version(run_id, playbook_yaml, fixture.slug)

    # Patch the DB session so no real DB is needed
    mock_db = _make_mock_db()

    state: dict[str, Any] = dict(fixture.initial_state)
    state["_trigger"] = fixture.trigger_payload
    state["__model"] = model or "claude-haiku-4-5-20251001"
    state["__dry_run"] = False
    state["__max_turns"] = 5   # limit turns to keep live eval cheap

    # Stub external integrations: GitHub, Slack, email, etc.
    # Each stub returns a plausible no-op response so the playbook flows through.
    integration_patches = _build_integration_patches()

    # If an explicit api_key was supplied, inject it into the AnthropicClient
    # constructor for this call only — scoped to the with block, thread-safe.
    if api_key:
        _orig_init = None
        try:
            from app.runtime.llm_client import AnthropicClient
            _orig_init = AnthropicClient.__init__

            def _patched_init(self: Any, **kwargs: Any) -> None:
                kwargs["api_key"] = api_key
                _orig_init(self, **kwargs)  # type: ignore[misc]

            integration_patches["app.runtime.llm_client.AnthropicClient.__init__"] = _patched_init
        except ImportError:
            pass  # llm_client not available — executor will fall back to env/settings

    with _apply_patches(integration_patches):
        from app.runtime.executor import _execute_dag
        try:
            final_state = _execute_dag(
                run=mock_run,
                version=mock_version,
                initial_state=state,
                db=mock_db,
            )
            run_status = "succeeded"
        except Exception as exc:
            final_state = state
            run_status = "failed"
            log.debug("live_dag_failed", slug=fixture.slug, error=str(exc))

    from app.runtime.executor import _detect_outcome
    outcome = _detect_outcome(fixture.slug, final_state, run_status)

    return {"status": run_status, "outcome": outcome, "state": final_state}


def _make_mock_run(run_id: Any, fixture: PlaybookFixture) -> Any:
    from unittest.mock import MagicMock
    from datetime import datetime, timezone

    run = MagicMock()
    run.id = run_id
    run.status = "running"
    run.triggered_by = "eval:manual"
    run.created_at = datetime.now(timezone.utc)
    run.completed_at = None
    run.attempt_count = 1
    run.state = {}
    run.outcome = None
    return run


def _make_mock_version(run_id: Any, playbook_yaml: str, slug: str | None = None) -> Any:
    from unittest.mock import MagicMock

    # Parse the YAML and build a minimal graph
    try:
        from app.dsl import load_workflow_yaml, yaml_to_graph
        wf = load_workflow_yaml(playbook_yaml)
        graph = yaml_to_graph(wf)
    except Exception:
        graph = {"nodes": [], "edges": []}

    version = MagicMock()
    version.id = run_id
    version.graph = graph
    version.yaml_text = playbook_yaml

    # Mock the workflow relationship
    wf_mock = MagicMock()
    wf_mock.name = "eval-test"
    wf_mock.playbook_slug = slug
    wf_mock.workspace_id = "eval-workspace"
    version.workflow = wf_mock

    # Build compiled artifacts: minimal passthrough stubs for each block
    import yaml
    raw = yaml.safe_load(playbook_yaml) or {}
    artifacts: dict[str, dict] = {}
    for block_id, block_def in (raw.get("blocks") or {}).items():
        btype = block_def.get("type", "")
        artifacts[block_id] = {
            "system_prompt": block_def.get("description", ""),
            "model": block_def.get("model", "claude-haiku-4-5-20251001"),
            "mode": block_def.get("mode", btype),
            "raw_slots": {},
        }
    version.compiled_artifacts = artifacts
    return version


def _make_mock_db() -> Any:
    from unittest.mock import MagicMock
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    # query().filter_by() chaining
    db.query.return_value.filter_by.return_value.first.return_value = None
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []
    return db


def _build_integration_patches() -> dict[str, Any]:
    """
    Return a dict of patch targets and their stub return values.
    These stubs intercept external API calls so the eval runs offline.
    """

    # Generic no-op that returns a plausible response for GitHub / Slack
    def _github_stub(*args, **kwargs):
        return {"html_url": "https://github.com/eval/stub", "number": 1, "id": 1}

    def _slack_stub(*args, **kwargs):
        return {"ok": True, "ts": "123456.789"}

    return {
        "app.runtime.integrations.github.GitHubClient.create_pull_request_review": _github_stub,
        "app.runtime.integrations.github.GitHubClient.create_issue": _github_stub,
        "app.runtime.integrations.github.GitHubClient.create_issue_comment": _github_stub,
        "app.runtime.integrations.slack.SlackClient.post_message": _slack_stub,
    }


def _apply_patches(patches: dict[str, Any]):
    """Context manager: apply all patches at once."""
    from contextlib import ExitStack
    from unittest.mock import patch

    stack = ExitStack()
    for target, stub in patches.items():
        try:
            stack.enter_context(patch(target, side_effect=stub))
        except (ModuleNotFoundError, AttributeError):
            pass  # Integration module not present; skip
    return stack


def _sum_tokens(state: dict) -> int:
    total = 0
    for k, v in state.items():
        if k.startswith("__") or not isinstance(v, dict):
            continue
        total += (v.get("input_tokens") or 0) + (v.get("output_tokens") or 0)
    return total
