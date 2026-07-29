"""Backfill: assign every existing security_loop / security_autopilot_fix
workflow to a Security Automation project + set the workspace pointer.

Step 3 of conductai#1005. After this runs, every workspace with security
workflows will:
  - have exactly one project with ``project_type = 'security_automation'``
  - have both security workflows moved under that project (``Workflow.project_id``)
  - have ``Workspace.security_automation_project_id`` set to that project

The migration 0087 partial unique index
``projects_workspace_security_automation_uniq`` guarantees at most one such
project per workspace, and ``workflows_project_playbook_uniq`` guarantees at
most one workflow-per-slug-per-project. Duplicates in the source data are
detected, skipped, and reported for manual review — never auto-deleted.

After this ships, the legacy ``.first()`` fallback in
``_find_security_workflow`` can be removed (step 4).

Run:
  cd apps/api
  python scripts/backfill_security_automation_project.py            # dry-run
  python scripts/backfill_security_automation_project.py --apply    # write
  python scripts/backfill_security_automation_project.py --workspace-id UUID
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from app.core.database import SessionLocal
from app.routers.security import (
    _SECURITY_AUTOPILOT_FIX_SLUG,
    _SECURITY_LOOP_SLUG,
    _ensure_security_automation_project,
)


_SECURITY_SLUGS = (_SECURITY_LOOP_SLUG, _SECURITY_AUTOPILOT_FIX_SLUG)


@dataclass
class WorkspacePlan:
    """What we would do (or did) for one workspace."""
    workspace_id: str
    loop_workflows: list  # (workflow_id, project_id)
    fix_workflows: list
    has_duplicates: bool

    def summary(self) -> str:
        if self.has_duplicates:
            dupes = []
            if len(self.loop_workflows) > 1:
                ids = ", ".join(str(w[0]) for w in self.loop_workflows)
                dupes.append(f"{len(self.loop_workflows)}× security_loop ({ids})")
            if len(self.fix_workflows) > 1:
                ids = ", ".join(str(w[0]) for w in self.fix_workflows)
                dupes.append(f"{len(self.fix_workflows)}× security_autopilot_fix ({ids})")
            return f"[{self.workspace_id}] SKIP — duplicates: {'; '.join(dupes)} — manual review"

        parts = []
        if self.loop_workflows:
            parts.append(f"security_loop={self.loop_workflows[0][0]}")
        if self.fix_workflows:
            parts.append(f"security_autopilot_fix={self.fix_workflows[0][0]}")
        return f"[{self.workspace_id}] plan: move {', '.join(parts)} → new/existing security_automation project"


def group_by_slug(rows: Iterable) -> tuple[list, list]:
    """Given rows of (workflow_id, project_id, playbook_slug), return
    (loop_workflows, fix_workflows) as (workflow_id, project_id) tuples."""
    loop, fix = [], []
    for wf_id, proj_id, slug in rows:
        if slug == _SECURITY_LOOP_SLUG:
            loop.append((wf_id, proj_id))
        elif slug == _SECURITY_AUTOPILOT_FIX_SLUG:
            fix.append((wf_id, proj_id))
    return loop, fix


def analyze_workspace(workspace_id: str, workflow_rows: Iterable) -> WorkspacePlan:
    """Pure function: classify a workspace's security workflows."""
    loop, fix = group_by_slug(workflow_rows)
    return WorkspacePlan(
        workspace_id=str(workspace_id),
        loop_workflows=loop,
        fix_workflows=fix,
        has_duplicates=(len(loop) > 1 or len(fix) > 1),
    )


def _fetch_workspaces_with_security_workflows(db, only_workspace_id: str | None):
    """Return {workspace_id: [(wf_id, project_id, slug), ...]}."""
    from sqlalchemy import bindparam, text

    sql = (
        "SELECT workspace_id, id, project_id, playbook_slug "
        "FROM workflows "
        "WHERE playbook_slug IN :slugs"
    )
    params: dict = {"slugs": list(_SECURITY_SLUGS)}
    if only_workspace_id:
        sql += " AND workspace_id = :ws"
        params["ws"] = only_workspace_id

    stmt = text(sql).bindparams(bindparam("slugs", expanding=True))
    grouped: dict = defaultdict(list)
    for ws_id, wf_id, proj_id, slug in db.execute(stmt, params):
        grouped[str(ws_id)].append((str(wf_id), str(proj_id) if proj_id else None, slug))
    return grouped


def _apply_plan(db, plan: WorkspacePlan) -> str:
    """Auto-provision project + move the two canonical workflows into it."""
    from sqlalchemy import text

    project_id = _ensure_security_automation_project(db, plan.workspace_id)
    moved = []
    for wf_list, slug in ((plan.loop_workflows, "security_loop"),
                          (plan.fix_workflows, "security_autopilot_fix")):
        if not wf_list:
            continue
        wf_id, current_project_id = wf_list[0]
        if current_project_id == project_id:
            continue  # already in place
        db.execute(
            text("UPDATE workflows SET project_id = :pid WHERE id = :wid"),
            {"pid": project_id, "wid": wf_id},
        )
        moved.append(f"{slug}={wf_id}")

    if not moved:
        return f"[{plan.workspace_id}] already migrated — project={project_id}"
    return f"[{plan.workspace_id}] MOVED {', '.join(moved)} → project={project_id}"


def run(apply_changes: bool, only_workspace_id: str | None) -> int:
    """Return process exit code: 0 clean, 1 if any duplicates encountered."""
    db = SessionLocal()
    exit_code = 0
    try:
        grouped = _fetch_workspaces_with_security_workflows(db, only_workspace_id)
        if not grouped:
            print("No workspaces with security workflows found.")
            return 0

        plans = [analyze_workspace(ws_id, rows) for ws_id, rows in grouped.items()]
        moved = skipped = clean = 0

        for plan in plans:
            if plan.has_duplicates:
                print(plan.summary())
                skipped += 1
                exit_code = 1
                continue
            if apply_changes:
                print(_apply_plan(db, plan))
            else:
                print(plan.summary())
            moved += 1
        clean = moved  # for the summary line

        if apply_changes:
            db.commit()
            print(f"\n{clean} workspace(s) processed, {skipped} skipped due to duplicates.")
        else:
            print(
                f"\nDry run: {clean} workspace(s) would be processed, "
                f"{skipped} would be skipped. Re-run with --apply to write."
            )
    finally:
        db.close()
    return exit_code


def _main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="Write changes. Default is dry-run.")
    p.add_argument("--workspace-id", help="Only process this workspace (UUID). Default: all.")
    args = p.parse_args()
    sys.exit(run(apply_changes=args.apply, only_workspace_id=args.workspace_id))


if __name__ == "__main__":
    _main()
