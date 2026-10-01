"""Explicit inventory associations; this command never contacts discovered servers."""
import json
import re
from uuid import UUID

from . import shared as guard_shared


def run(args):
    if args.offset < 0:
        raise SystemExit("--offset must be non-negative")
    body = None
    if args.action != "list":
        if not args.installation or not re.fullmatch(r"[a-f0-9]{64}", args.reference or ""):
            raise SystemExit("--installation UUID and --reference from mcp-links list are required")
        try:
            installation = str(UUID(args.installation))
            server = str(UUID(args.server)) if args.action == "link" and args.server else None
        except ValueError:
            raise SystemExit("Installation and registration IDs must be UUIDs") from None
        if args.action == "link" and not server:
            raise SystemExit("--server registration UUID is required")
        if args.revision is None or args.revision < 0:
            raise SystemExit("--revision from mcp-links list is required")
        body = {"server_id": server, "revision": args.revision}
    cfg = guard_shared._require_guard_config()
    workspace = str(UUID(cfg["workspace_id"]))
    root = guard_shared._api_url(cfg) + "/guard/discover"
    token = cfg.get("agent_token") or None
    if args.action == "list":
        result = guard_shared._req("GET", f"{root}/mcp-reconciliation?workspace_id={workspace}&offset={args.offset}", token=token)
    else:
        result = guard_shared._req("PUT", f"{root}/agents/{installation}/mcp-links/{args.reference}?workspace_id={workspace}",
                                  token=token, body=body)
    print(json.dumps(result, indent=2, ensure_ascii=True))
