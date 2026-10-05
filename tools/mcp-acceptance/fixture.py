"""Expire/revoke one credential on a disposable local stack, then verify/restore it.

The snapshot contains only UUID references and timestamps, never tokens/hashes.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/api"))


def require(condition):
    if not condition:
        raise ValueError("Invalid fixture or lifecycle evidence")


def main(argv=None):
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session
    from app.modules.agent_identity.models import AgentCredentialSession, AgentIdentity
    from app.modules.guard.models import GuardAuditEvent

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["expire", "revoke", "verify-refresh", "verify-revoked", "restore"])
    parser.add_argument("--workspace", type=UUID, required=True)
    parser.add_argument("--identity", type=UUID, required=True)
    parser.add_argument("--credential", type=UUID, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--database-env", default="MCP_ACCEPTANCE_DATABASE_URL")
    parser.add_argument("--allow-disposable-fixture", action="store_true")
    args = parser.parse_args(argv)
    require(args.allow_disposable_fixture)
    url = make_url(os.environ[args.database_env])
    require(url.host in {"localhost", "127.0.0.1", "::1"})
    engine = create_engine(url, connect_args={"connect_timeout": 10}, hide_parameters=True)
    try:
        with Session(engine) as db:
            row = db.query(AgentCredentialSession).join(AgentIdentity).filter(
                AgentCredentialSession.id == str(args.credential),
                AgentIdentity.id == str(args.identity), AgentIdentity.workspace_id == args.workspace,
            ).with_for_update().one()
            ts = datetime.now(timezone.utc)
            if args.action in {"expire", "revoke"}:
                require(row.revoked_at is None)
                snapshot = {"workspace": str(args.workspace), "identity": str(args.identity),
                            "credential": str(args.credential), "started_at": ts.isoformat(),
                            "action": args.action, "expires_at": row.expires_at.isoformat(),
                            "test_expires_at": (ts - timedelta(seconds=1)).isoformat(), "revoked_at": None}
                fd = os.open(args.snapshot, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "w") as file:
                    json.dump(snapshot, file)
                if args.action == "expire":
                    row.expires_at = datetime.fromisoformat(snapshot["test_expires_at"])
                else:
                    row.revoked_at = ts
                db.commit()
                return 0
            snapshot = json.loads(args.snapshot.read_text())
            require(snapshot["workspace"] == str(args.workspace) and snapshot["identity"] == str(args.identity)
                    and snapshot["credential"] == str(args.credential))
            if args.action == "restore":
                # Restore only our mutation; leave a client's subsequent rotation intact.
                if snapshot["action"] == "expire" and row.expires_at == datetime.fromisoformat(snapshot["test_expires_at"]):
                    row.expires_at = datetime.fromisoformat(snapshot["expires_at"])
                if snapshot["action"] == "revoke" and row.revoked_at == datetime.fromisoformat(snapshot["started_at"]):
                    row.revoked_at = None
                db.commit()
                return 0
            marker = os.environ["MCP_ACCEPTANCE_MARKER"]
            require(marker.startswith("mcp-acceptance-") and len(marker) <= 64)
            events = db.query(GuardAuditEvent).filter(
                GuardAuditEvent.workspace_id == args.workspace,
                GuardAuditEvent.agent_identity_id == str(args.identity),
                GuardAuditEvent.ts >= datetime.fromisoformat(snapshot["started_at"]),
                GuardAuditEvent.input_summary.contains(marker), GuardAuditEvent.source == "mcp",
            ).all()
            if args.action == "verify-revoked":
                require(snapshot["action"] == "revoke" and row.revoked_at is not None)
                require(not events)
            else:
                require(snapshot["action"] == "expire" and row.revoked_at is None)
                require(row.expires_at > ts and row.expires_at > datetime.fromisoformat(snapshot["expires_at"]))
                require(bool(events))
                for event in events:
                    credential_id = (event.routing_meta or {}).get("credential_session_id")
                    require(credential_id == str(args.credential))
            return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit("Fixture check failed; database details and credentials omitted") from None
