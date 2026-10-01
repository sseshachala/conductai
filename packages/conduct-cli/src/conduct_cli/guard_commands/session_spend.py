"""Read session evidence from the selected deployment, without changing setup."""
import json
from uuid import UUID

from . import shared


def run(args):
    try:
        event_id = str(UUID(args.event))
    except ValueError:
        raise SystemExit("--event must be a session usage event UUID") from None
    cfg = shared._require_guard_config()
    workspace = str(UUID(cfg["workspace_id"]))
    result = shared._req(
        "GET", f"{shared._api_url(cfg)}/guard/events/session-usage/{event_id}/reconciliation?workspace_id={workspace}",
        token=cfg.get("agent_token") or None,
    )
    print(json.dumps(result, indent=2, ensure_ascii=True))
