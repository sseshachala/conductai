"""Explicit registered-server review; passive discovery never calls these APIs."""
import json
import re
from uuid import UUID

from . import shared as guard_shared


def run(args):
    action = args.action
    server = str(UUID(args.server)) if args.server else None
    if action != "list" and server is None:
        raise SystemExit("--server is required")
    if action not in {"list", "inspect"} and (args.revision is None or args.revision < 0):
        raise SystemExit("--revision from the latest server listing is required")
    if action == "approve" and not re.fullmatch(r"[a-f0-9]{64}", args.digest or ""):
        raise SystemExit("--digest from the reviewed inspection is required")
    if action == "revoke" and not args.yes:
        raise SystemExit("--yes is required to remove the saved registration credential")
    if action == "response_policy" and getattr(args, "mode", None) not in {"off", "audit", "block", "redact"}:
        raise SystemExit("--mode is required for response_policy")
    cfg = guard_shared._require_guard_config()
    workspace = str(UUID(cfg["workspace_id"]))
    root = guard_shared._api_url(cfg) + "/mcp-servers"
    token = cfg.get("agent_token") or None
    if action == "list":
        rows = guard_shared._req("GET", f"{root}?workspace_id={workspace}", token=token)
        result = [{"id": row["id"], "name": row["name"], "governance": row.get("governance")}
                  for row in rows]
    elif action == "inspect":
        result = guard_shared._req("POST", f"{root}/{server}/inspect?workspace_id={workspace}", token=token)
    else:
        row = guard_shared._req("POST", f"{root}/{server}/review?workspace_id={workspace}", token=token,
                                body={"action": action, "revision": args.revision, "digest": args.digest,
                                      **({"mode": args.mode} if action == "response_policy" else {})})
        result = {"id": row["id"], "governance": row["governance"]}
    print(json.dumps(result, indent=2, ensure_ascii=True))
