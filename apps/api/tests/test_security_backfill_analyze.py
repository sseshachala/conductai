"""#1005 step 3 — backfill script's pure-function core.

The DB parts of the backfill are dry-run-tested against prod; the pure
logic (group rows, detect duplicates, format summary) is unit-tested here.
"""
from __future__ import annotations

from scripts.backfill_security_automation_project import (
    analyze_workspace,
    group_by_slug,
)


def test_group_by_slug_partitions_by_playbook():
    rows = [
        ("wf-1", "proj-a", "security_loop"),
        ("wf-2", "proj-a", "security-autopilot-fix"),
        ("wf-3", None, "some_other_slug"),  # ignored
    ]
    loop, fix = group_by_slug(rows)
    assert loop == [("wf-1", "proj-a")]
    assert fix == [("wf-2", "proj-a")]


def test_analyze_workspace_no_duplicates_when_one_of_each():
    rows = [
        ("wf-1", "proj-a", "security_loop"),
        ("wf-2", "proj-a", "security-autopilot-fix"),
    ]
    plan = analyze_workspace("ws-1", rows)
    assert plan.has_duplicates is False
    assert len(plan.loop_workflows) == 1
    assert len(plan.fix_workflows) == 1
    assert "plan: move" in plan.summary()


def test_analyze_workspace_flags_duplicate_security_loop():
    rows = [
        ("wf-1", "proj-a", "security_loop"),
        ("wf-2", "proj-b", "security_loop"),  # duplicate slug
        ("wf-3", "proj-a", "security-autopilot-fix"),
    ]
    plan = analyze_workspace("ws-1", rows)
    assert plan.has_duplicates is True
    assert len(plan.loop_workflows) == 2
    summary = plan.summary()
    assert "SKIP" in summary
    assert "2× security_loop" in summary
    assert "manual review" in summary


def test_analyze_workspace_flags_duplicate_autopilot_fix():
    rows = [
        ("wf-1", "proj-a", "security-autopilot-fix"),
        ("wf-2", "proj-b", "security-autopilot-fix"),
    ]
    plan = analyze_workspace("ws-1", rows)
    assert plan.has_duplicates is True
    assert "2× security_autopilot_fix" in plan.summary()


def test_analyze_workspace_only_loop_installed():
    """Some workspaces have only the auto-triage playbook, not the autopilot fix."""
    rows = [("wf-1", "proj-a", "security_loop")]
    plan = analyze_workspace("ws-1", rows)
    assert plan.has_duplicates is False
    assert plan.loop_workflows == [("wf-1", "proj-a")]
    assert plan.fix_workflows == []
    # Summary still shows what we plan to move
    assert "security_loop=wf-1" in plan.summary()


def test_analyze_workspace_workflow_with_null_project_id():
    """Workflow never installed under a project → project_id is None in the row."""
    rows = [
        ("wf-1", None, "security_loop"),
        ("wf-2", None, "security-autopilot-fix"),
    ]
    plan = analyze_workspace("ws-1", rows)
    assert plan.has_duplicates is False
    assert plan.loop_workflows[0][1] is None
    assert plan.fix_workflows[0][1] is None
