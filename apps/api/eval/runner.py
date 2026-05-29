"""
Eval runner — orchestrates the full eval loop.

Usage
-----
  # From Python
  from eval.runner import run_all, run_one
  report = run_all()                 # structural only, all playbooks
  report = run_all(live=True)        # also execute with real LLM
  report = run_one("pr_reviewer")    # single playbook

  # From the CLI
  python -m eval.runner
  python -m eval.runner --live
  python -m eval.runner --playbook pr_reviewer
  python -m eval.runner --playbook pr_reviewer --live

Live execution
--------------
When live=True the runner instantiates a minimal mock database session and
executes the playbook through the real executor.  External integrations
(GitHub, Slack, email) are intercepted and stubbed so no real API calls are
made.  The LLM is real — set ANTHROPIC_API_KEY in the environment.

The mock session does not persist; it lives only for the duration of the eval.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from eval.fixtures import PlaybookFixture, load_fixtures, load_fixture
from eval.scorer import PlaybookScore, score_structural, score_quality
from eval.report import EvalReport

log = logging.getLogger(__name__)


# ── main entry points ─────────────────────────────────────────────────────────

def run_all(live: bool = False, playbooks_dir: Path | None = None) -> EvalReport:
    """
    Evaluate all playbooks and return a consolidated report.

    Parameters
    ----------
    live:
        When True, execute each playbook via the real executor with a mocked
        database and stubbed integrations.  Requires ANTHROPIC_API_KEY.
    playbooks_dir:
        Override the default playbooks directory (useful for tests).
    """
    fixtures = load_fixtures(playbooks_dir) if playbooks_dir else load_fixtures()
    scores: list[PlaybookScore] = []

    for fixture in fixtures:
        score = _eval_one(fixture, live=live)
        scores.append(score)

    return EvalReport(scores=scores, live_mode=live)


def run_one(slug: str, live: bool = False) -> EvalReport:
    """Evaluate a single playbook by slug."""
    fixture = load_fixture(slug)
    if fixture is None:
        raise ValueError(
            f"No playbook found with slug '{slug}'. "
            f"Available slugs: {_list_slugs()}"
        )
    score = _eval_one(fixture, live=live)
    return EvalReport(scores=[score], live_mode=live)


# ── internal eval for one playbook ───────────────────────────────────────────

def _eval_one(fixture: PlaybookFixture, live: bool) -> PlaybookScore:
    """Run all checks for one playbook and return a PlaybookScore."""
    start = time.perf_counter()

    playbook_yaml = fixture.playbook_path.read_text()
    score = score_structural(playbook_yaml, fixture.slug)

    if live:
        score = _run_live(fixture, score, playbook_yaml)

    elapsed = time.perf_counter() - start
    log.info(
        "eval",
        slug=fixture.slug,
        structural=score.structural_score,
        quality=score.quality_score if live else "n/a",
        grade=score.grade,
        elapsed_ms=round(elapsed * 1000),
    )
    return score


# ── structural-only helpers ───────────────────────────────────────────────────

def _list_slugs() -> list[str]:
    return [f.slug for f in load_fixtures()]


# ── live execution helpers ────────────────────────────────────────────────────

def _run_live(
    fixture: PlaybookFixture,
    score: PlaybookScore,
    playbook_yaml: str,
) -> PlaybookScore:
    """
    Execute the playbook end-to-end through the real executor using a
    mock database and stubbed integrations.  Appends quality criteria to score.
    """
    try:
        result = _execute_with_mocks(fixture, playbook_yaml)
        run_status   = result["status"]
        outcome      = result["outcome"]
        state        = result["state"]
        total_tokens = _sum_tokens(state)
        return score_quality(score, run_status, outcome, state, total_tokens)

    except Exception as exc:
        tb = traceback.format_exc()
        log.warning("live_eval_failed", slug=fixture.slug, error=str(exc))
        # Add a single failed quality criterion with the error
        from eval.scorer import CriterionResult
        score.criteria.append(CriterionResult(
            name="live_execution", passed=False,
            points_earned=0, points_possible=40,
            detail=f"Execution raised: {exc}\n{tb[:500]}",
        ))
        score.quality_max = 40
        return score


def _execute_with_mocks(fixture: PlaybookFixture, playbook_yaml: str) -> dict[str, Any]:
    """
    Build a mock run context and call the executor directly.

    Returns a dict with keys: status, outcome, state.
    """
    import uuid
    from unittest.mock import MagicMock, patch

    # Build a fake run object
    run_id = uuid.uuid4()
    mock_run = _make_mock_run(run_id, fixture)
    mock_version = _make_mock_version(run_id, playbook_yaml)

    # Patch the DB session so no real DB is needed
    mock_db = _make_mock_db()

    state: dict[str, Any] = dict(fixture.initial_state)
    state["_trigger"] = fixture.trigger_payload
    state["__model"] = "claude-haiku-4-5-20251001"
    state["__dry_run"] = False
    state["__max_turns"] = 5   # limit turns to keep live eval cheap

    # Stub external integrations: GitHub, Slack, email, etc.
    # Each stub returns a plausible no-op response so the playbook flows through.
    integration_patches = _build_integration_patches()

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


def _make_mock_version(run_id: Any, playbook_yaml: str) -> Any:
    from unittest.mock import MagicMock
    import json

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
    wf_mock.playbook_slug = None
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
    from unittest.mock import AsyncMock, MagicMock

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


# ── CLI entry point ───────────────────────────────────────────────────────────

def _cli():
    parser = argparse.ArgumentParser(
        description="Conduct Eval Harness — playbook quality scorer",
    )
    parser.add_argument(
        "--playbook", metavar="SLUG",
        help="Evaluate a single playbook by slug (e.g. pr_reviewer)",
    )
    parser.add_argument(
        "--live", action="store_true", default=False,
        help="Execute playbooks with real LLM calls (requires ANTHROPIC_API_KEY)",
    )
    parser.add_argument(
        "--json", dest="json_out", action="store_true", default=False,
        help="Print full JSON report instead of human-readable summary",
    )
    parser.add_argument(
        "--out", metavar="FILE",
        help="Write report to file (JSON)",
    )
    parser.add_argument(
        "--promote", action="store_true", default=False,
        help="Write PlaybookSubmission rows to DB after scoring (requires DB connection)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    if args.playbook:
        report = run_one(args.playbook, live=args.live)
    else:
        report = run_all(live=args.live)

    if args.json_out:
        print(report.to_json())
    else:
        print(report.summary())

    if args.out:
        Path(args.out).write_text(report.to_json())
        print(f"\nReport written to {args.out}")

    if args.promote:
        from eval.promotion import promote
        submissions = promote(report)
        print(f"\nPromotion complete: {len(submissions)} submission(s) written to DB")

    # Exit with non-zero if any playbook is failing (grade F)
    if any(s.grade == "F" for s in report.scores):
        sys.exit(1)


if __name__ == "__main__":
    # Ensure apps/api is on the path when invoked as a module
    _root = Path(__file__).resolve().parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
    _cli()
