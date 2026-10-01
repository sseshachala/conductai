"""Explicit peer review for synthetic fixture edits; never upload edit content."""

import json
from pathlib import Path
from uuid import UUID

from conduct_cli.hooks.fixture_approval import fingerprint
from . import shared


def run(args):
    digest = None
    if args.action in {"fingerprint", "approve"}:
        if not args.action_file:
            raise SystemExit("--action-file is required")
        try:
            path = Path(args.action_file)
            if path.stat().st_size > 256 * 1024:
                raise ValueError("Too large")
            value = json.loads(path.read_text())
            digest = fingerprint(value["tool_name"], value["tool_input"], value["cwd"])
        except (OSError, ValueError, KeyError, TypeError):
            raise SystemExit(
                "Invalid fixture action file; expected tool_name, tool_input and absolute cwd"
            ) from None
    if args.action == "fingerprint":
        print(digest)
        return
    if args.action == "approve" and (
        not args.reviewed_synthetic
        or not args.subject
        or not (args.reason or "").strip()
    ):
        raise SystemExit(
            "Review the full edit, then supply --reviewed-synthetic, --subject and --reason"
        )
    cfg = shared._require_guard_config()
    root = shared._api_url(cfg) + "/guard/fixture-approvals"
    query = "?workspace_id=" + str(UUID(cfg["workspace_id"]))
    token = cfg.get("agent_token")
    if args.action == "list":
        value = shared._req("GET", root + query, token=token)
    elif args.action == "approve":
        value = shared._req(
            "POST",
            root + query,
            token=token,
            body={
                "action_digest": digest,
                "subject_id": args.subject,
                "reason": args.reason,
                "synthetic_reviewed": True,
                "ttl_seconds": args.ttl_seconds,
            },
        )
    else:
        if not args.approval:
            raise SystemExit("--approval is required")
        value = shared._req(
            "POST",
            root + "/" + str(UUID(args.approval)) + "/revoke" + query,
            token=token,
        )
    print(json.dumps(value, indent=2))
