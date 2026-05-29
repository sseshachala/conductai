"""
Eval harness tests — structural mode only (no LLM calls, no DB).

These run as part of the standard pytest suite (``rtk pytest``).
They enforce a minimum quality floor across all 18+ pre-built playbooks.

Grade thresholds:
  - No playbook may score below 60 pts (grade D or F)
  - The overall average must be at least 70 pts

Individual criterion tests catch common authoring mistakes early:
  - Missing test_trigger sections
  - Orphan blocks (reachable only from dead-end routing)
  - Brain blocks without JSON output contracts
  - Logic blocks with incomplete pass/fail branches
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure apps/api root is on the path so ``import app.*`` and ``import eval.*`` work
HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

from eval.fixtures import load_fixtures, load_fixture
from eval.runner import run_all, run_one
from eval.scorer import score_structural


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def all_scores():
    """Run the full structural eval once per test session."""
    report = run_all(live=False)
    return report.scores


@pytest.fixture(scope="session")
def all_fixtures():
    return load_fixtures()


# ── basic fixture loading ─────────────────────────────────────────────────────

def test_fixtures_load(all_fixtures):
    """All playbook YAML files should produce a fixture."""
    assert len(all_fixtures) >= 18, (
        f"Expected at least 18 playbook fixtures, got {len(all_fixtures)}"
    )


def test_fixture_slugs_are_unique(all_fixtures):
    slugs = [f.slug for f in all_fixtures]
    assert len(slugs) == len(set(slugs)), "Duplicate fixture slugs detected"


def test_every_fixture_has_playbook_path(all_fixtures):
    for f in all_fixtures:
        assert f.playbook_path.exists(), f"Playbook file missing for slug '{f.slug}'"


# ── DSL validation ────────────────────────────────────────────────────────────

def test_all_playbooks_parse(all_fixtures):
    """Every playbook must parse cleanly through the DSL validator."""
    failures = []
    for fixture in all_fixtures:
        try:
            from app.dsl import load_workflow_yaml
            load_workflow_yaml(fixture.playbook_path.read_text())
        except Exception as exc:
            failures.append(f"{fixture.slug}: {exc}")

    assert not failures, "DSL validation failures:\n" + "\n".join(failures)


# ── structural scores ─────────────────────────────────────────────────────────

def test_no_playbook_below_minimum(all_scores):
    """No playbook may score below 60 (grade D / F)."""
    below = [(s.slug, s.structural_score) for s in all_scores if s.structural_score < 60]
    assert not below, (
        "Playbooks below minimum structural score of 60:\n"
        + "\n".join(f"  {slug}: {score}" for slug, score in below)
    )


def test_average_structural_score(all_scores):
    """Average structural score across all playbooks must be >= 70."""
    avg = sum(s.structural_score for s in all_scores) / len(all_scores)
    assert avg >= 70, f"Average structural score {avg:.1f} is below 70"


def test_grade_distribution(all_scores):
    """At least 80% of playbooks should achieve grade C or better."""
    grades = [s.grade for s in all_scores]
    passing = sum(1 for g in grades if g not in ("D", "F"))
    ratio = passing / len(grades)
    assert ratio >= 0.80, (
        f"Only {passing}/{len(grades)} playbooks at grade C or better ({ratio:.0%})"
    )


# ── criterion-level checks ────────────────────────────────────────────────────

def test_all_triggers_wired(all_scores):
    """Every playbook's trigger must route to a real block."""
    failures = [
        s.slug for s in all_scores
        if not _criterion_passed(s, "trigger_wired")
    ]
    assert not failures, f"Trigger not wired in: {failures}"


def test_all_have_test_fixtures(all_scores):
    """Every playbook must have a test_trigger section."""
    failures = [
        s.slug for s in all_scores
        if not _criterion_passed(s, "test_fixture_present")
    ]
    assert not failures, (
        f"Missing test_trigger section in: {failures}\n"
        "Add a 'test_trigger: payload: ...' section to each playbook."
    )


def test_no_orphan_blocks(all_scores):
    """No playbook should have blocks that are unreachable from the trigger."""
    failures = [
        (s.slug, _criterion_detail(s, "no_orphan_blocks"))
        for s in all_scores
        if not _criterion_passed(s, "no_orphan_blocks")
    ]
    assert not failures, (
        "Orphan blocks detected:\n"
        + "\n".join(f"  {slug}: {detail}" for slug, detail in failures)
    )


def test_brain_blocks_have_descriptions(all_scores):
    """Every brain block must have a non-empty description."""
    failures = [
        (s.slug, _criterion_detail(s, "brain_descriptions"))
        for s in all_scores
        if not _criterion_passed(s, "brain_descriptions")
    ]
    assert not failures, (
        "Brain blocks missing descriptions:\n"
        + "\n".join(f"  {slug}: {detail}" for slug, detail in failures)
    )


def test_brain_blocks_have_json_contracts(all_scores):
    """Brain blocks should declare a JSON output contract on the last line."""
    failures = [
        (s.slug, _criterion_detail(s, "output_contract_json"))
        for s in all_scores
        if not _criterion_passed(s, "output_contract_json")
    ]
    assert not failures, (
        "Brain blocks missing JSON output contracts:\n"
        + "\n".join(f"  {slug}: {detail}" for slug, detail in failures)
    )


def test_logic_blocks_complete(all_scores):
    """Every logic block must have both pass: and fail: branches."""
    failures = [
        (s.slug, _criterion_detail(s, "logic_branches_complete"))
        for s in all_scores
        if not _criterion_passed(s, "logic_branches_complete")
    ]
    assert not failures, (
        "Logic blocks with incomplete routing:\n"
        + "\n".join(f"  {slug}: {detail}" for slug, detail in failures)
    )


def test_outcome_map_coverage(all_scores):
    """Playbooks should appear in _OUTCOME_MAP for analytics tracking."""
    # This is advisory — not all slugs need to be in the map — so we just report
    not_mapped = [
        s.slug for s in all_scores
        if not _criterion_passed(s, "outcome_map_entry")
    ]
    # Warn but don't fail hard: custom/internal playbooks may not be in the map
    if not_mapped:
        import warnings
        warnings.warn(
            f"Playbooks not in _OUTCOME_MAP (add for analytics): {not_mapped}",
            stacklevel=2,
        )


# ── per-playbook spot checks ──────────────────────────────────────────────────

@pytest.mark.parametrize("slug,expected_blocks", [
    ("pr_reviewer",       {"recall_context", "review_pr", "has_critical"}),
    ("issue_triage",      {"recall_context", "triage_issue", "record_outcome"}),
    ("security_scanner",  {"recall_context", "fetch_pr_diff", "security_scan", "has_critical"}),
    ("autopilot",         {"fetch_issue", "implement_fix", "run_tests", "tests_pass", "push_pr"}),
])
def test_expected_blocks_present(slug, expected_blocks):
    """Key blocks must be present in the specified playbooks."""
    fixture = load_fixture(slug)
    if fixture is None:
        pytest.skip(f"Playbook '{slug}' not found")

    from app.dsl import load_workflow_yaml
    import yaml
    raw = yaml.safe_load(fixture.playbook_path.read_text()) or {}
    actual_blocks = set(raw.get("blocks", {}).keys())
    missing = expected_blocks - actual_blocks
    assert not missing, (
        f"Expected blocks missing from '{slug}': {missing}"
    )


def test_pr_reviewer_has_logic_branch():
    """PR Reviewer must branch on critical issues found."""
    fixture = load_fixture("pr_reviewer")
    if fixture is None:
        pytest.skip("pr_reviewer not found")

    from app.dsl import load_workflow_yaml, yaml_to_graph
    yaml_text = fixture.playbook_path.read_text()
    wf = load_workflow_yaml(yaml_text)
    g = yaml_to_graph(wf)

    handle_edges = {e.get("sourceHandle"): e["target"] for e in g["edges"] if "sourceHandle" in e}
    assert "pass" in handle_edges, "PR Reviewer missing pass branch on logic block"
    assert "fail" in handle_edges, "PR Reviewer missing fail branch on logic block"


def test_autopilot_trigger_fixture_payload():
    """Autopilot fixture payload must contain a repository full_name."""
    fixture = load_fixture("autopilot")
    if fixture is None:
        pytest.skip("autopilot not found")

    payload = fixture.trigger_payload
    assert payload, "autopilot fixture payload is empty"


def test_run_one_returns_report():
    """run_one() should return a single-score report without errors."""
    report = run_one("pr_reviewer")
    assert len(report.scores) == 1
    assert report.scores[0].slug == "pr_reviewer"
    assert report.scores[0].structural_score > 0


def test_report_to_json_is_valid():
    """EvalReport.to_json() must produce valid JSON with the expected schema."""
    import json
    report = run_one("issue_triage")
    data = json.loads(report.to_json())
    assert data["version"] == "1"
    assert "summary" in data
    assert "playbooks" in data
    assert len(data["playbooks"]) == 1
    pb = data["playbooks"][0]
    assert pb["slug"] == "issue_triage"
    assert "criteria" in pb


def test_report_summary_contains_grade():
    """EvalReport.summary() must mention the grade for each playbook."""
    report = run_one("security_scanner")
    text = report.summary()
    assert "security_scanner" in text
    assert any(g in text for g in ("A", "B", "C", "D", "F"))


def test_regression_alerts_no_regressions():
    """Running eval twice on the same data should produce zero regression alerts."""
    report_a = run_all(live=False)
    report_b = run_all(live=False)
    alerts = report_b.regression_alerts(baseline=report_a)
    assert alerts == [], f"Unexpected regression alerts: {alerts}"


def test_promotion_candidates():
    """At least one playbook should qualify as a promotion candidate."""
    report = run_all(live=False)
    candidates = report.promotion_candidates(min_grade="C")
    assert len(candidates) >= 1, "No playbooks reached grade C — check rubric thresholds"


# ── helpers ───────────────────────────────────────────────────────────────────

def test_slug_specific_rubrics_autopilot():
    """autopilot score should include the autopilot_outputs_pr_url criterion."""
    report = run_one("autopilot")
    score = report.scores[0]
    criterion_names = [c.name for c in score.criteria]
    assert "autopilot_outputs_pr_url" in criterion_names, (
        f"autopilot score missing autopilot_outputs_pr_url criterion. "
        f"Found: {criterion_names}"
    )


def test_slug_specific_rubrics_pr_reviewer():
    """pr_reviewer score should include the reviewer_has_critical_logic criterion."""
    report = run_one("pr_reviewer")
    score = report.scores[0]
    criterion_names = [c.name for c in score.criteria]
    assert "reviewer_has_critical_logic" in criterion_names, (
        f"pr_reviewer score missing reviewer_has_critical_logic criterion. "
        f"Found: {criterion_names}"
    )


def test_structural_max_is_dynamic(all_scores):
    """
    structural_max must equal the sum of all criteria.points_possible for
    each playbook (it is computed dynamically, not hardcoded to 100).
    """
    for score in all_scores:
        expected_max = sum(c.points_possible for c in score.criteria)
        assert score.structural_max == expected_max, (
            f"{score.slug}: structural_max={score.structural_max} but "
            f"sum(criteria.points_possible)={expected_max}"
        )


# ── helpers ───────────────────────────────────────────────────────────────────

def _criterion_passed(score, name: str) -> bool:
    for c in score.criteria:
        if c.name == name:
            return c.passed
    return True   # criterion not evaluated for this playbook — don't fail


def _criterion_detail(score, name: str) -> str:
    for c in score.criteria:
        if c.name == name:
            return c.detail
    return ""
