#!/usr/bin/env python3
"""Seed canonical screenshot data for the website facelift.

Produces the deterministic Acme Robotics workspace referenced in
`docs/website-facelift-2026.md` §10. Every re-run reproduces the same
IDs, timestamps, and rendered strings so screenshots stay stable across
UI changes.

What it seeds (keyed by the IMG-* IDs in the facelift plan):
- IMG-01 Policy Decision Card — 3 audit events (allow / approve / block)
- IMG-02 Approval Flow        — 1 pending GuardApprovalRequest
- IMG-03 Cross-agent Activity — 4 audit events across 4 agent surfaces
- IMG-04 Audit Receipt        — the BLOCK event from IMG-01, richer detail
- IMG-05 Policy Definition    — 3 workspace_custom_rules (viewable in UI)
- IMG-07 Playbook Run         — 1 Workflow + WorkflowVersion + Run + events
- IMG-10 Discovery Scan       — 1 DiscoveryScan + 4 DiscoveredAgents

Prerequisites:
  export DATABASE_URL=postgresql://...    # required
  # Local dev only — workspace must exist first:
  python apps/api/scripts/seed_e2e_workspace.py
  # Prod / staging — pass an existing workspace UUID via --workspace-id

Usage:
  # Local dev (default workspace, default localhost URLs)
  python apps/api/scripts/seed_screenshots.py
  python apps/api/scripts/seed_screenshots.py --wipe

  # Prod / staging — target a specific workspace and print prod URLs
  python apps/api/scripts/seed_screenshots.py \\
      --workspace-id 8f2a1c50-... \\
      --created-by user_2h5abc... \\
      --base-url https://app.conductai.ai \\
      --wipe

Idempotent — uses fixed UUIDs under the 77777777-... namespace so --wipe
targets only screenshot rows without touching real data.
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
sys.path.insert(0, str(APPS_API))

from app.core.auth import DEV_USER_ID as _DEFAULT_USER, DEV_WORKSPACE_ID as _DEFAULT_WORKSPACE  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models.run import Run, RunEvent  # noqa: E402
from app.models.workflow import Workflow, WorkflowVersion  # noqa: E402
from app.models.workspace import Workspace  # noqa: E402
from app.modules.guard.models import (  # noqa: E402
    DiscoveredAgent,
    DiscoveryScan,
    GuardApprovalRequest,
    GuardAuditEvent,
    WorkspaceCustomRule,
)

# ── target workspace ──────────────────────────────────────────────────────────
# Set by main() from --workspace-id, defaults to WORKSPACE_ID.
# Every _seed_* function references this global so the script works against
# both local dev (default) and prod (with a real workspace UUID).

WORKSPACE_ID: uuid.UUID | str = _DEFAULT_WORKSPACE
CREATED_BY: str = _DEFAULT_USER


# ── deterministic ids ─────────────────────────────────────────────────────────

_NS = "77777777-7777-7777-7777"

def _u(suffix: str) -> uuid.UUID:
    return uuid.UUID(f"{_NS}-{suffix:>012}")

WORKFLOW_ID    = _u("100000000001")
WF_VERSION_ID  = _u("100000000002")
RUN_ID         = _u("100000000003")
DISCOVERY_ID   = _u("200000000001")
APPROVAL_ID    = _u("300000000001")
EVENT_IDS = {
    "img01_allow":    _u("400000000001"),
    "img01_approve":  _u("400000000002"),
    "img01_block":    _u("400000000003"),  # doubles as IMG-04 receipt
    "img03_claude":   _u("400000000004"),
    "img03_cursor":   _u("400000000005"),
    "img03_codex":    _u("400000000006"),
    "img03_copilot":  _u("400000000007"),
}

# Reference "day" — Wed 2026-03-11 14:32 UTC. Everything reads as one coherent day.
REF = datetime(2026, 3, 11, 14, 32, 11, tzinfo=timezone.utc)


# ── canonical strings (match facelift §2 canonical identifiers) ───────────────
AGENTS = {
    "claude":  "claude-code / deploy-agent",
    "cursor":  "cursor-agent-17",
    "codex":   "codex / release-agent",
    "copilot": "copilot-reviewer",
}
USER_EMAIL = "developer@acme.example"

RULES = [
    {
        "rule_id": "production-change-v4",
        "match_pattern": r"deploy.*production",
        "action": "approval",
        "severity": "high",
        "message": "Production deployment outside approved change window",
    },
    {
        "rule_id": "refund-cap",
        "match_pattern": r"issue_refund",
        "action": "block",
        "severity": "high",
        "message": "Agent refund limit $500",
    },
    {
        "rule_id": "no-production-network-change",
        "match_pattern": r"update_terraform.*prod",
        "action": "block",
        "severity": "critical",
        "message": "Production network modifications require approved change record.",
    },
]


# ── wipe ──────────────────────────────────────────────────────────────────────

def wipe(db) -> None:
    counts = {}
    counts["audit_events"] = (
        db.query(GuardAuditEvent)
        .filter(GuardAuditEvent.id.in_(list(EVENT_IDS.values())))
        .delete(synchronize_session=False)
    )
    counts["approvals"] = (
        db.query(GuardApprovalRequest)
        .filter(GuardApprovalRequest.id == APPROVAL_ID)
        .delete(synchronize_session=False)
    )
    counts["run_events"] = (
        db.query(RunEvent).filter(RunEvent.run_id == RUN_ID).delete(synchronize_session=False)
    )
    counts["runs"] = db.query(Run).filter(Run.id == RUN_ID).delete(synchronize_session=False)
    counts["wf_versions"] = (
        db.query(WorkflowVersion).filter(WorkflowVersion.id == WF_VERSION_ID).delete(synchronize_session=False)
    )
    counts["workflows"] = (
        db.query(Workflow).filter(Workflow.id == WORKFLOW_ID).delete(synchronize_session=False)
    )
    counts["discovered"] = (
        db.query(DiscoveredAgent).filter(DiscoveredAgent.scan_id == DISCOVERY_ID).delete(synchronize_session=False)
    )
    counts["discovery"] = (
        db.query(DiscoveryScan).filter(DiscoveryScan.id == DISCOVERY_ID).delete(synchronize_session=False)
    )
    for rule in RULES:
        counts[f"rule:{rule['rule_id']}"] = (
            db.query(WorkspaceCustomRule)
            .filter_by(workspace_id=WORKSPACE_ID, rule_id=rule["rule_id"])
            .delete(synchronize_session=False)
        )
    db.commit()
    for k, v in counts.items():
        if v:
            print(f"  wiped {v:>3} {k}")


# ── seed ──────────────────────────────────────────────────────────────────────

def _seed_rules(db) -> None:
    for rule in RULES:
        key = (WORKSPACE_ID, rule["rule_id"])
        if db.get(WorkspaceCustomRule, key):
            continue
        db.add(WorkspaceCustomRule(
            workspace_id=WORKSPACE_ID,
            rule_id=rule["rule_id"],
            persona="agent",
            body=rule,
            enabled=True,
            created_by=CREATED_BY,
            created_at=REF - timedelta(days=30),
            updated_at=REF - timedelta(days=7),
        ))
    print(f"  rules: {len(RULES)}")


def _audit_event(
    *, id, ai_tool, tool_call, decision, rule_id, message, minutes_ago, input_summary,
    duration_ms=180, blast=None,
) -> GuardAuditEvent:
    ts = REF - timedelta(minutes=minutes_ago)
    return GuardAuditEvent(
        id=id,
        workspace_id=WORKSPACE_ID,
        clerk_user_id=CREATED_BY,
        user_email=USER_EMAIL,
        ai_tool=ai_tool,
        tool_call=tool_call,
        source="hook",
        input_summary=input_summary,
        decision=decision,
        rule_id=rule_id,
        rule_message=message,
        blast_radius=blast,
        ts=ts,
        duration_ms=duration_ms,
        execution_status="success" if decision in ("allow", "warn", "approve") else None,
    )


def _seed_audit_events(db) -> None:
    events = [
        _audit_event(
            id=EVENT_IDS["img01_allow"], ai_tool=AGENTS["claude"], tool_call="run_tests",
            decision="allow", rule_id=None, message=None,
            input_summary="Bash: pytest apps/api/tests/ -x",
            minutes_ago=45,
        ),
        _audit_event(
            id=EVENT_IDS["img01_approve"], ai_tool=AGENTS["claude"], tool_call="deploy_production",
            decision="approval", rule_id="production-change-v4",
            message="Production deployment outside approved change window",
            input_summary="deploy(environment='prod', service='payments-api')",
            minutes_ago=8, blast={"environment": "production", "service": "payments-api"},
        ),
        _audit_event(
            id=EVENT_IDS["img01_block"], ai_tool=AGENTS["cursor"], tool_call="update_terraform",
            decision="block", rule_id="no-production-network-change",
            message="Production network modifications require approved change record.",
            input_summary="update_terraform(resource='prod-vpc')",
            minutes_ago=0, blast={"resource": "prod-vpc"},
        ),
        _audit_event(
            id=EVENT_IDS["img03_claude"], ai_tool=AGENTS["claude"], tool_call="Edit",
            decision="allow", rule_id=None, message=None,
            input_summary="Edit apps/api/app/routers/runs.py — add pagination",
            minutes_ago=127,
        ),
        _audit_event(
            id=EVENT_IDS["img03_cursor"], ai_tool=AGENTS["cursor"], tool_call="Write",
            decision="allow", rule_id=None, message=None,
            input_summary="Write apps/web/src/app/page.tsx",
            minutes_ago=98,
        ),
        _audit_event(
            id=EVENT_IDS["img03_codex"], ai_tool=AGENTS["codex"], tool_call="issue_refund",
            decision="block", rule_id="refund-cap",
            message="Agent refund limit $500",
            input_summary="issue_refund(customer='C-8911', amount=840)",
            minutes_ago=62, blast={"customer": "C-8911", "amount_usd": 840},
        ),
        _audit_event(
            id=EVENT_IDS["img03_copilot"], ai_tool=AGENTS["copilot"], tool_call="approve_pr",
            decision="warn", rule_id=None, message="PR touches production config path",
            input_summary="Approve PR #4821 (touches deploy/production.yml)",
            minutes_ago=34,
        ),
    ]
    db.add_all(events)
    print(f"  audit events: {len(events)}")


def _seed_pending_approval(db) -> None:
    if db.get(GuardApprovalRequest, APPROVAL_ID):
        return
    db.add(GuardApprovalRequest(
        id=APPROVAL_ID,
        workspace_id=WORKSPACE_ID,
        rule_id="production-change-v4",
        rule_pack="conduct-base",
        rule_message="Production deployment outside approved change window",
        tool_name="deploy_production",
        tool_input={"environment": "production", "service": "payments-api"},
        requester_email=USER_EMAIL,
        requester_user_id=CREATED_BY,
        requester_agent_ident=AGENTS["claude"],
        surface="hook",
        session_id="hook_sess_screenshot_01",
        approval_type="any_authorized",
        status="pending",
        created_at=REF - timedelta(minutes=4),
        timeout_at=REF + timedelta(hours=4),
    ))
    print("  pending approval: 1 (IMG-02)")


def _seed_playbook_run(db) -> None:
    now = REF - timedelta(minutes=22)
    wf = db.get(Workflow, WORKFLOW_ID)
    if wf is None:
        wf = Workflow(
            id=WORKFLOW_ID,
            workspace_id=WORKSPACE_ID,
            name="pr-reviewer",
            default_mode="dag",
            playbook_slug="pr-reviewer",
            guard_enabled=True,
            agent_identity_required=True,
            created_at=REF - timedelta(days=14),
            updated_at=now,
        )
        db.add(wf)
        db.flush()  # so subsequent db.get(WorkflowVersion,...) FK is valid
    if not db.get(WorkflowVersion, WF_VERSION_ID):
        db.add(WorkflowVersion(
            id=WF_VERSION_ID,
            workflow_id=WORKFLOW_ID,
            yaml_source="name: pr-reviewer\nblocks:\n  - id: fetch\n  - id: review\n  - id: approve\n",
            graph={
                "nodes": [
                    {"id": "fetch",   "type": "tool"},
                    {"id": "review",  "type": "brain"},
                    {"id": "approve", "type": "approval"},
                    {"id": "comment", "type": "tool"},
                ],
                "edges": [
                    {"from": "fetch",   "to": "review"},
                    {"from": "review",  "to": "approve"},
                    {"from": "approve", "to": "comment"},
                ],
            },
            created_at=REF - timedelta(days=14),
            published_at=REF - timedelta(days=14),
        ))
        db.flush()
        wf.current_version_id = WF_VERSION_ID

    if not db.get(Run, RUN_ID):
        db.add(Run(
            id=RUN_ID,
            workflow_version_id=WF_VERSION_ID,
            workspace_id=WORKSPACE_ID,
            triggered_by="github_webhook",
            status="succeeded",
            started_at=now,
            completed_at=now + timedelta(minutes=6),
            actual_turns=8,
            state={"pr": 4821, "repo": "acme/payments-api"},
            outcome={"type": "pr_comment", "artifact_url": "https://github.com/acme/payments-api/pull/4821"},
            created_at=now,
        ))
        events = [
            ("fetch",   "block_started",       {}),
            ("fetch",   "block_completed",     {"files_changed": 12}),
            ("review",  "block_started",       {}),
            ("review",  "brain_turn",          {"turn": 1, "tokens_in": 4123, "tokens_out": 812}),
            ("review",  "brain_turn",          {"turn": 2, "tokens_in": 5011, "tokens_out": 1104}),
            ("review",  "block_completed",     {"findings": 3}),
            ("approve", "approval_requested",  {"requester": "pr-reviewer"}),
            ("approve", "approval_received",   {"decision": "approved", "actor": USER_EMAIL}),
            ("comment", "block_completed",     {"comment_id": 981234}),
        ]
        for i, (block_id, kind, payload) in enumerate(events):
            db.add(RunEvent(
                run_id=RUN_ID,
                block_id=block_id,
                kind=kind,
                payload=payload,
                created_at=now + timedelta(seconds=i * 40),
            ))
    print("  playbook run: 1 (IMG-07)")


def _seed_discovery(db) -> None:
    if db.get(DiscoveryScan, DISCOVERY_ID):
        return
    started = REF - timedelta(hours=3)
    db.add(DiscoveryScan(
        id=DISCOVERY_ID,
        workspace_id=WORKSPACE_ID,
        triggered_by="cli",
        status="complete",
        agents_found=4,
        guard_coverage=2,
        scan_config={"paths": ["~/", "/opt"]},
        started_at=started,
        completed_at=started + timedelta(minutes=2),
    ))
    db.flush()  # so DiscoveredAgent FK is valid
    agents = [
        ("claude-code-workstation-01", "claude-code", "process", "/usr/local/bin/claude",       True,  True,  10),
        ("cursor-mac-01",              "cursor",      "process", "/Applications/Cursor.app",    True,  False, 20),
        ("langchain-jobs-agent",       "langchain",   "config",  "~/projects/jobs/agent.py",    False, False, 70),
        ("crewai-support-bot",         "crewai",      "config",  "~/projects/support/crew.yml", False, False, 55),
    ]
    for name, framework, source, location, under_guard, proxy, risk in agents:
        db.add(DiscoveredAgent(
            workspace_id=WORKSPACE_ID,
            scan_id=DISCOVERY_ID,
            name=name,
            framework=framework,
            source=source,
            location=location,
            evidence={"cmd": location},
            risk_score=risk,
            under_guard=under_guard,
            proxy_routed=proxy,
            first_seen_at=started,
            last_seen_at=started + timedelta(minutes=2),
        ))
    print(f"  discovery: 1 scan + {len(agents)} agents (IMG-10)")


def seed(db, base_url: str = "http://localhost:3000") -> None:
    if not db.get(Workspace, WORKSPACE_ID):
        print(f"ERROR: workspace {WORKSPACE_ID} does not exist.")
        print("Pass an existing workspace via --workspace-id, or run seed_e2e_workspace.py for local dev.")
        sys.exit(2)

    _seed_rules(db)
    _seed_audit_events(db)
    _seed_pending_approval(db)
    _seed_playbook_run(db)
    _seed_discovery(db)
    db.commit()
    print()
    print(f"  Workspace: {WORKSPACE_ID}")
    print(f"  Screenshot URLs ({base_url}):")
    print(f"    Guard audit          → {base_url}/audit")
    print(f"    Audit receipt IMG-04 → {base_url}/audit/{EVENT_IDS['img01_block']}")
    print(f"    Pending approvals    → {base_url}/theguard/approvals")
    print(f"    Playbook run IMG-07  → {base_url}/runs/{RUN_ID}")
    print(f"    Discovery IMG-10     → {base_url}/theguard/discovery/{DISCOVERY_ID}")
    print(f"    Policy definitions   → {base_url}/theguard/policies")


def main() -> None:
    global WORKSPACE_ID, CREATED_BY
    parser = argparse.ArgumentParser(description="Seed canonical website-facelift screenshot data")
    parser.add_argument(
        "--workspace-id",
        default=str(_DEFAULT_WORKSPACE),
        help=f"Target workspace UUID (default: {_DEFAULT_WORKSPACE} — local dev workspace)",
    )
    parser.add_argument(
        "--created-by",
        default=_DEFAULT_USER,
        help="Clerk user ID recorded as created_by on seeded rules (default: local dev user)",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:3000",
        help="Base URL to print alongside screenshot URLs (default: http://localhost:3000)",
    )
    parser.add_argument("--wipe", action="store_true", help="Wipe screenshot rows first (idempotent re-seed)")
    args = parser.parse_args()

    try:
        WORKSPACE_ID = uuid.UUID(args.workspace_id)
    except ValueError:
        print(f"ERROR: --workspace-id must be a valid UUID, got: {args.workspace_id}")
        sys.exit(1)
    CREATED_BY = args.created_by

    db = SessionLocal()
    try:
        if args.wipe:
            print(f"Wiping existing screenshot rows for workspace {WORKSPACE_ID}...")
            wipe(db)
        print(f"Seeding screenshot data into workspace {WORKSPACE_ID}...")
        seed(db, base_url=args.base_url.rstrip("/"))
        print("Done.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
