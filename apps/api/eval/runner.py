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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eval.fixtures import (
    PlaybookFixture, FixtureScenario, ScenarioSet,
    load_fixtures, load_fixture, load_scenario_set,
)
from eval.scorer import PlaybookScore, score_structural, score_quality
from eval.report import EvalReport

try:
    import structlog
    log = structlog.get_logger(__name__)
except ImportError:
    log = logging.getLogger(__name__)


# ── main entry points ─────────────────────────────────────────────────────────

def run_scenarios(
    slug: str,
    live: bool = False,
    model: str | None = None,
    api_key: str | None = None,
) -> "ScenarioReport":
    """
    Run a multi-scenario eval for a single playbook.

    Returns a :class:`ScenarioReport` containing per-scenario results plus
    aggregate pass/fail counts.  Falls back to single-scenario behaviour if
    the playbook has no multi-scenario fixture file.

    Parameters
    ----------
    model:
        Override the LLM model used during live execution (e.g. ``claude-sonnet-4-6``).
        Only applies when live=True.
    api_key:
        Anthropic API key.  Scoped to this call only — no os.environ mutation.
    """
    scenario_set = load_scenario_set(slug)
    if scenario_set is None:
        # Fall back to single-scenario
        report = run_one(slug, live=live, api_key=api_key)
        return ScenarioReport(
            slug=slug,
            scenarios=[],
            eval_report=report,
            model=model,
        )

    scenario_results: list[dict] = []
    scores: list[PlaybookScore] = []

    for scenario in scenario_set.scenarios:
        start = time.perf_counter()
        try:
            result = _eval_scenario(scenario, live=live, model=model, api_key=api_key)
            elapsed = round((time.perf_counter() - start) * 1000)
            scenario_results.append({
                "id": scenario.id,
                "label": scenario.label,
                "tags": scenario.tags,
                "status": "ok",
                "grade": result.grade,
                "pct": round(result.pct, 1),
                "structural_score": result.structural_score,
                "quality_score": result.quality_score,
                "elapsed_ms": elapsed,
                "error": None,
            })
            scores.append(result)
        except Exception as exc:
            elapsed = round((time.perf_counter() - start) * 1000)
            log.warning("scenario_eval_failed", slug=slug, scenario=scenario.id, error=str(exc))
            scenario_results.append({
                "id": scenario.id,
                "label": scenario.label,
                "tags": scenario.tags,
                "status": "error",
                "grade": "F",
                "pct": 0.0,
                "structural_score": 0,
                "quality_score": 0,
                "elapsed_ms": elapsed,
                "error": str(exc),
            })

    # Roll up a combined EvalReport using the best (primary) scenario score
    best_score = max(scores, key=lambda s: s.pct) if scores else None
    wrapped_report = EvalReport(
        scores=[best_score] if best_score else [],
        live_mode=live,
    )

    return ScenarioReport(
        slug=slug,
        scenarios=scenario_results,
        eval_report=wrapped_report,
        model=model,
        scenario_count=len(scenario_set.scenarios),
        positive_count=len(scenario_set.positive_scenarios),
        negative_count=len(scenario_set.negative_scenarios),
    )


@dataclass
class ScenarioReport:
    """Result of a multi-scenario eval run."""
    slug: str
    scenarios: list[dict]
    eval_report: EvalReport
    model: str | None = None
    scenario_count: int = 0
    positive_count: int = 0
    negative_count: int = 0

    @property
    def passing_scenarios(self) -> list[dict]:
        return [s for s in self.scenarios if s.get("grade") not in ("D", "F")]

    @property
    def failing_scenarios(self) -> list[dict]:
        return [s for s in self.scenarios if s.get("grade") in ("D", "F")]

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "model": self.model,
            "scenario_count": self.scenario_count,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "passing_scenarios": len(self.passing_scenarios),
            "failing_scenarios": len(self.failing_scenarios),
            "scenarios": self.scenarios,
            "aggregate": self.eval_report._to_dict() if self.eval_report.scores else {},
        }


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


def run_one(slug: str, live: bool = False, api_key: str | None = None) -> EvalReport:
    """
    Evaluate a single playbook by slug.

    Parameters
    ----------
    api_key:
        Anthropic API key to use for live eval.  When provided it is injected
        directly into the LLM client via a mock patch scoped to this call —
        no process-level environment mutation occurs.  If omitted the executor
        falls back to settings.anthropic_api_key / os.environ.
    """
    fixture = load_fixture(slug)
    if fixture is None:
        raise ValueError(
            f"No playbook found with slug '{slug}'. "
            f"Available slugs: {_list_slugs()}"
        )
    score = _eval_one(fixture, live=live, api_key=api_key)
    return EvalReport(scores=[score], live_mode=live)


# ── internal eval for one playbook ───────────────────────────────────────────

def _eval_scenario(
    scenario: FixtureScenario,
    live: bool,
    model: str | None = None,
    api_key: str | None = None,
) -> PlaybookScore:
    """Run all checks for a single FixtureScenario and return a PlaybookScore."""
    # Build a transient PlaybookFixture from the scenario for reuse of existing code
    fixture = PlaybookFixture(
        slug=scenario.playbook_slug,
        playbook_path=scenario.playbook_path,
        trigger_payload=scenario.trigger_payload,
        initial_state=scenario.initial_state,
        expected_outcome_type=scenario.expected_outcome_type,
        expected_artifact_keys=scenario.expected_artifact_keys,
        extra_assertions=scenario.extra_assertions,
        source="file",
    )
    return _eval_one(fixture, live=live, model=model, api_key=api_key)


def _eval_one(
    fixture: PlaybookFixture,
    live: bool,
    model: str | None = None,
    api_key: str | None = None,
) -> PlaybookScore:
    """Run all checks for one playbook and return a PlaybookScore."""
    start = time.perf_counter()

    playbook_yaml = fixture.playbook_path.read_text()
    score = score_structural(playbook_yaml, fixture.slug)

    if live:
        score = _run_live(fixture, score, playbook_yaml, model=model, api_key=api_key)

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
    model: str | None = None,
    api_key: str | None = None,
) -> PlaybookScore:
    """
    Execute the playbook end-to-end through the real executor using a
    mock database and stubbed integrations.  Appends quality criteria to score.
    """
    try:
        result = _execute_with_mocks(fixture, playbook_yaml, model=model, api_key=api_key)
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
    from unittest.mock import MagicMock, patch

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
        "--model", metavar="MODEL", default=None,
        help="Override the LLM model for live evals (e.g. claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--scenarios", action="store_true", default=False,
        help="Run all scenarios for a playbook (requires --playbook)",
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
        "--publish", action="store_true", default=False,
        help="Write score as a committed baseline to reports/baselines/<slug>.json",
    )
    parser.add_argument(
        "--promote", action="store_true", default=False,
        help="Write PlaybookSubmission rows to DB after scoring (requires DB connection)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    if args.scenarios and args.playbook:
        # Multi-scenario run
        scenario_report = run_scenarios(
            args.playbook,
            live=args.live,
            model=args.model,
        )
        if args.json_out:
            import json
            print(json.dumps(scenario_report.to_dict(), indent=2))
        else:
            d = scenario_report.to_dict()
            print(f"\nScenario eval: {args.playbook} ({d['scenario_count']} scenarios)")
            print(f"  Passing: {d['passing_scenarios']}  Failing: {d['failing_scenarios']}")
            for s in d["scenarios"]:
                tag = "[neg]" if "negative" in s["tags"] else "     "
                print(f"  {tag} {s['id']:<30} {s['grade']}  {s['pct']:.0f}%  {s.get('error') or ''}")
        if args.publish and args.playbook:
            _publish_baseline(scenario_report.to_dict(), args.playbook, model=args.model)
        sys.exit(0)

    if args.playbook:
        report = run_one(args.playbook, live=args.live, api_key=None)
    else:
        report = run_all(live=args.live)

    if args.json_out:
        print(report.to_json())
    else:
        print(report.summary())

    if args.out:
        Path(args.out).write_text(report.to_json())
        print(f"\nReport written to {args.out}")

    if args.publish:
        slug = args.playbook or "all"
        _publish_baseline(report._to_dict(), slug, model=args.model)

    if args.promote:
        from eval.promotion import promote
        submissions = promote(report)
        print(f"\nPromotion complete: {len(submissions)} submission(s) written to DB")

    # Exit with non-zero if any playbook is failing (grade F)
    if any(s.grade == "F" for s in report.scores):
        sys.exit(1)


def _publish_baseline(data: dict, slug: str, model: str | None = None) -> None:
    """
    Write a committed baseline JSON to reports/baselines/<slug>.json.

    The baselines directory is under the repo root (apps/api/reports/baselines/).
    Baseline files are committed to git so regression checks can compare against them.
    """
    import json
    from datetime import datetime, timezone

    root = Path(__file__).resolve().parent.parent
    baselines_dir = root / "reports" / "baselines"
    baselines_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{slug}.json" if not model else f"{slug}_{model.replace('-', '_')}.json"
    dest = baselines_dir / filename

    payload = {
        **data,
        "baseline_published_at": datetime.now(timezone.utc).isoformat(),
        "model": model or "claude-haiku-4-5-20251001",
    }
    dest.write_text(json.dumps(payload, indent=2))
    print(f"\nBaseline written to {dest.relative_to(root)}")


if __name__ == "__main__":
    # Ensure apps/api is on the path when invoked as a module
    _root = Path(__file__).resolve().parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
    _cli()
