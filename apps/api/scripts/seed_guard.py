"""
Seed script — populates the Guard dashboard with realistic test data.

Usage:
  # Populate (adds to existing data)
  python apps/api/scripts/seed_guard.py --workspace-id <uuid>

  # Wipe Guard data for this workspace, then repopulate
  python apps/api/scripts/seed_guard.py --workspace-id <uuid> --clean

  # Wipe only (no repopulate)
  python apps/api/scripts/seed_guard.py --workspace-id <uuid> --clean --dry-run

Requires DATABASE_URL env var (or .env file at apps/api/.env).
"""
from __future__ import annotations

import argparse
import os
import random
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow `import app.*` from the api root
HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
sys.path.insert(0, str(APPS_API))

# Load .env if present
_env_file = APPS_API / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from app.core.database import SessionLocal
from app.modules.guard.models import (
    GuardAuditEvent,
    GuardMember,
    GuardPolicy,
    GuardSession,
    GuardSpendBudget,
    GuardTeam,
)
from app.models.workspace import Workspace  # noqa — ensure FK target is loaded


# ── realistic data pools ──────────────────────────────────────────────────────

DEVELOPERS = [
    {"email": "alice@acme.dev",   "role": "owner"},
    {"email": "bob@acme.dev",     "role": "developer"},
    {"email": "carol@acme.dev",   "role": "developer"},
    {"email": "dan@acme.dev",     "role": "security"},
    {"email": "eve@acme.dev",     "role": "developer"},
]

AI_TOOLS = ["claude-code", "cursor", "copilot", "claude-code", "claude-code"]  # weighted

TOOL_CALLS = [
    "Read", "Write", "Edit", "Bash", "Grep", "Glob",
    "Read", "Write", "Edit",  # weighted toward common calls
]

DECISIONS = ["allowed", "allowed", "allowed", "allowed", "blocked", "warned"]  # mostly allowed

POLICIES = [
    {
        "rule_id": "no-env-writes",
        "description": "Block writes to .env files",
        "match_tool": "*",
        "match_path_pattern": r"\.env",
        "action": "block",
        "message": "Writing to .env files is not allowed. Use the Conduct credential vault instead.",
        "builtin": True,
    },
    {
        "rule_id": "no-secret-patterns",
        "description": "Block tool calls containing secret patterns",
        "match_tool": "*",
        "match_pattern": r"(password|secret|private_key|sk-ant|ghp_)",
        "action": "block",
        "message": "Tool call contains a secret pattern. Use environment variables.",
        "builtin": True,
    },
    {
        "rule_id": "warn-production-paths",
        "description": "Warn on writes to production config paths",
        "match_tool": "*",
        "match_path_pattern": r"(prod|production|deploy)",
        "action": "warn",
        "message": "Writing to a production path. Confirm this is intentional.",
        "builtin": False,
    },
    {
        "rule_id": "audit-sql-migrations",
        "description": "Audit all SQL migration file edits",
        "match_tool": "*",
        "match_path_pattern": r"migrations?/.*\.sql",
        "action": "audit",
        "message": "SQL migration edit recorded for compliance audit.",
        "builtin": False,
    },
    {
        "rule_id": "no-force-push",
        "description": "Block force push commands",
        "match_tool": "claude-code",
        "match_pattern": r"git push.*--force",
        "action": "block",
        "message": "Force push is not allowed. Use --force-with-lease if absolutely necessary.",
        "builtin": False,
        "enabled": False,  # disabled — shows up in policy list but doesn't evaluate
    },
]

INPUT_SAMPLES = [
    "Read file /src/components/Button.tsx",
    "Edit apps/api/app/routers/runs.py — add pagination",
    "Bash: pytest apps/api/tests/ -x",
    "Write apps/web/src/app/page.tsx",
    "Grep pattern 'get_current_user' in apps/api/",
    "Edit apps/api/app/modules/guard/routers/spend.py",
    "Read .env.example",
    "Bash: git status",
    "Glob **/*.py in apps/api/app/",
    "Write apps/api/alembic/versions/0042_add_guard_spend.py",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ago(hours: int = 0, days: int = 0, minutes: int = 0) -> datetime:
    return _now() - timedelta(hours=hours, days=days, minutes=minutes)


# ── clean ─────────────────────────────────────────────────────────────────────

def clean(db, workspace_id: uuid.UUID) -> None:
    team = db.query(GuardTeam).filter(GuardTeam.workspace_id == workspace_id).first()
    if not team:
        print(f"  No Guard team found for workspace {workspace_id} — nothing to clean.")
        return

    tid = team.id
    deleted = {}

    deleted["audit_events"] = db.query(GuardAuditEvent).filter(GuardAuditEvent.team_id == tid).delete()
    deleted["sessions"]     = db.query(GuardSession).filter(GuardSession.team_id == tid).delete()
    deleted["budgets"]      = db.query(GuardSpendBudget).filter(GuardSpendBudget.team_id == tid).delete()
    deleted["policies"]     = db.query(GuardPolicy).filter(GuardPolicy.team_id == tid).delete()
    deleted["members"]      = db.query(GuardMember).filter(GuardMember.team_id == tid).delete()
    deleted["team"]         = db.query(GuardTeam).filter(GuardTeam.id == tid).delete()

    db.commit()
    for k, v in deleted.items():
        print(f"  deleted {v:>4} {k}")
    print(f"  Guard data for workspace {workspace_id} wiped.")


# ── seed ──────────────────────────────────────────────────────────────────────

def seed(db, workspace_id: uuid.UUID) -> None:
    # 1. Team
    team = GuardTeam(
        id=uuid.uuid4(),
        name="Acme Engineering",
        slug=f"acme-eng-{secrets.token_hex(4)}",
        invite_code=secrets.token_hex(16),
        workspace_id=workspace_id,
        alert_channel="#guard-alerts",
        notify_on_block=True,
        notify_on_budget=True,
    )
    db.add(team)
    db.flush()
    print(f"  team: {team.name} ({team.id})")

    # 2. Members
    members = []
    for dev in DEVELOPERS:
        m = GuardMember(
            id=uuid.uuid4(),
            team_id=team.id,
            user_id=f"user_{secrets.token_hex(8)}",
            email=dev["email"],
            role=dev["role"],
            active=True,
            joined_at=_ago(days=random.randint(7, 30)),
            member_token=secrets.token_hex(32),
        )
        db.add(m)
        members.append(m)
    db.flush()
    print(f"  members: {len(members)}")

    # 3. Policies
    for p_data in POLICIES:
        p = GuardPolicy(
            id=uuid.uuid4(),
            team_id=team.id,
            rule_id=p_data["rule_id"],
            description=p_data.get("description"),
            match_tool=p_data.get("match_tool"),
            match_pattern=p_data.get("match_pattern"),
            match_path_pattern=p_data.get("match_path_pattern"),
            action=p_data["action"],
            message=p_data.get("message"),
            enabled=p_data.get("enabled", True),
            builtin=p_data.get("builtin", False),
        )
        db.add(p)
    db.flush()
    print(f"  policies: {len(POLICIES)}")

    # 4. Team budget
    team_budget = GuardSpendBudget(
        id=uuid.uuid4(),
        team_id=team.id,
        member_id=None,  # team-wide
        monthly_limit_usd=500.0,
        hard_limit_usd=600.0,
        alert_threshold_pct=80,
        default_per_developer_usd=50.0,
    )
    db.add(team_budget)

    # 5. Per-developer budgets (3 of 5 have custom limits)
    for m in members[:3]:
        limit = random.choice([30.0, 50.0, 75.0, 100.0])
        db.add(GuardSpendBudget(
            id=uuid.uuid4(),
            team_id=team.id,
            member_id=m.id,
            monthly_limit_usd=limit,
            hard_limit_usd=limit * 1.2,
            alert_threshold_pct=80,
        ))
    db.flush()
    print(f"  budgets: 1 team + 3 per-developer")

    # 6. Sessions + audit events — spread over last 30 days
    total_events = 0
    total_sessions = 0

    for member in members:
        # Each developer has 3–8 sessions this month
        num_sessions = random.randint(3, 8)
        for s_idx in range(num_sessions):
            session_start = _ago(
                days=random.randint(0, 29),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )
            ai_tool = random.choice(AI_TOOLS)
            num_events = random.randint(5, 30)

            # Accumulate session totals
            s_tokens_before = 0
            s_tokens_after  = 0
            s_cost           = 0.0
            s_saved          = 0.0
            s_violations     = 0

            session = GuardSession(
                id=uuid.uuid4(),
                team_id=team.id,
                member_id=member.id,
                user_email=member.email,
                ai_tool=ai_tool,
                started_at=session_start,
                ended_at=session_start + timedelta(minutes=random.randint(15, 120)),
                event_count=num_events,
                violations_count=0,  # updated below
            )
            db.add(session)
            db.flush()
            total_sessions += 1

            for e_idx in range(num_events):
                decision = random.choice(DECISIONS)
                tokens_before = random.randint(800, 8000)
                tokens_after  = int(tokens_before * random.uniform(0.4, 0.9))
                tokens_saved  = tokens_before - tokens_after
                cost_before   = round(tokens_before * 0.000015, 6)
                cost_after    = round(tokens_after  * 0.000015, 6)

                rule_id   = None
                rule_msg  = None
                if decision in ("blocked", "warned"):
                    matched = random.choice([p for p in POLICIES if p.get("enabled", True) and p["action"] in ("block", "warn")])
                    rule_id  = matched["rule_id"]
                    rule_msg = matched.get("message")
                    s_violations += 1

                event_ts = session_start + timedelta(
                    minutes=random.randint(0, 90),
                    seconds=random.randint(0, 59),
                )

                ev = GuardAuditEvent(
                    id=uuid.uuid4(),
                    team_id=team.id,
                    member_id=member.id,
                    session_id=session.id,
                    user_email=member.email,
                    ai_tool=ai_tool,
                    tool_call=random.choice(TOOL_CALLS),
                    input_summary=random.choice(INPUT_SAMPLES),
                    decision=decision,
                    rule_id=rule_id,
                    rule_message=rule_msg,
                    tokens_before=tokens_before,
                    tokens_after=tokens_after,
                    tokens_saved=tokens_saved,
                    cost_usd_before=cost_before,
                    cost_usd_after=cost_after,
                    ts=event_ts,
                    duration_ms=random.randint(80, 2000),
                )
                db.add(ev)

                s_tokens_before += tokens_before
                s_tokens_after  += tokens_after
                s_cost          += cost_after
                s_saved         += (cost_before - cost_after)
                total_events    += 1

            # Update session totals
            session.total_tokens_before = s_tokens_before
            session.total_tokens_after  = s_tokens_after
            session.total_cost_usd      = round(s_cost, 4)
            session.total_saved_usd     = round(s_saved, 4)
            session.violations_count    = s_violations

    db.commit()
    print(f"  sessions: {total_sessions}")
    print(f"  audit events: {total_events}")
    print()
    print(f"  Guard dashboard: /guard")
    print(f"  Spend dashboard: /guard/spend")
    print(f"  Audit log:       /guard/audit")
    print(f"  Policies:        /guard/policies")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Seed or clean Guard dashboard data")
    parser.add_argument("--workspace-id", required=True, help="Workspace UUID to seed Guard data for")
    parser.add_argument("--clean", action="store_true", help="Wipe existing Guard data for this workspace first")
    parser.add_argument("--dry-run", action="store_true", help="With --clean, only wipe — do not repopulate")
    args = parser.parse_args()

    try:
        ws_id = uuid.UUID(args.workspace_id)
    except ValueError:
        print(f"ERROR: --workspace-id must be a valid UUID, got: {args.workspace_id}")
        sys.exit(1)

    db = SessionLocal()
    try:
        if args.clean:
            print(f"\nCleaning Guard data for workspace {ws_id}...")
            clean(db, ws_id)
            if args.dry_run:
                print("--dry-run set, skipping repopulate.")
                return

        print(f"\nSeeding Guard data for workspace {ws_id}...")
        seed(db, ws_id)
        print("\nDone.")
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
