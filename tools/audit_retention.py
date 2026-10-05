"""Operator checks; all storage/provider I/O happens outside DB transactions."""

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.workspace_context import set_workspace_rls
from app.modules.guard.audit_archive import S3ArchiveStore, read_verified_archive
from app.modules.guard.audit_retention import archive_workspace_once, checkpoint_anchor, verify_event_rows
from app.modules.guard.models import GuardAuditArchiveSegment


def main():
    parser = argparse.ArgumentParser(description="Audit archive preview, apply, and integrity checks")
    parser.add_argument("command", choices=("preview", "apply", "verify"))
    parser.add_argument("--workspace-id", required=True, type=UUID)
    args = parser.parse_args()
    try:
        import app.main  # Register all ORM relationship targets for the standalone operator.
        if args.command == "verify":
            with SessionLocal() as db:
                set_workspace_rls(db, args.workspace_id)
                checkpoint_anchor(db, args.workspace_id)
                segments = [(dict(row.manifest), row.signature) for row in db.query(GuardAuditArchiveSegment)
                    .filter(GuardAuditArchiveSegment.workspace_id == args.workspace_id)
                    .order_by(GuardAuditArchiveSegment.ordinal).all()]
            store = S3ArchiveStore(settings)
            previous = ""
            for manifest, signature in segments:
                rows = read_verified_archive(manifest, signature, settings, store, workspace_id=str(args.workspace_id))
                previous = verify_event_rows(rows, previous)
            result = {"verified_segments": len(segments)}
        else:
            result = archive_workspace_once(args.workspace_id, dry_run=args.command == "preview")
        print(json.dumps(result, sort_keys=True))
        return 1 if result.get("blocked_reason") else 0
    except Exception as exc:
        print(f"Archive check failed ({type(exc).__name__}); no credentials or payloads printed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
