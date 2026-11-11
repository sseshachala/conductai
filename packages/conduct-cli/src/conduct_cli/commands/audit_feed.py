"""`conduct audit feed` — stream Guard audit events as NDJSON for SIEM collectors.

Pages through the ``get_audit_feed`` MCP tool with the agent token. Each event
is one NDJSON line on stdout (or appended to ``--output``), which Splunk
Universal Forwarder, Azure Monitor Agent, Falcon LogScale Collector, Fluent Bit
or Vector can tail. The cursor is checkpointed to ``--state`` after every page
is written, so a restart resumes where it stopped without losing events.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from conduct_cli import deployment
from conduct_cli.audit_formats import FORMATS, FORMATTERS
from conduct_cli.commands.shared import _load_config

DEFAULT_STATE = Path.home() / ".conduct" / "audit-feed.cursor"
TOOL_NAME = "get_audit_feed"


class FeedError(RuntimeError):
    pass


def _call_tool(arguments: dict) -> dict:
    """One MCP ``tools/call``; refreshes the agent token once on 401."""
    for attempt in (1, 2):
        cfg = _load_config()
        token = cfg.get("agent_token")
        if not token:
            raise FeedError("not logged in; run `conduct login`")
        body = json.dumps({"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "tools/call",
                           "params": {"name": TOOL_NAME, "arguments": arguments}}).encode()
        req = urllib.request.Request(
            deployment.resolve(cfg).mcp, data=body, method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                     "Accept": "application/json, text/event-stream"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                reply = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and attempt == 1:
                from conduct_cli.commands.auth import _refresh_agent_token
                if _refresh_agent_token(expected_config=cfg):
                    continue
            raise FeedError(f"MCP request failed: HTTP {exc.code}") from exc
        if "error" in reply:
            raise FeedError(f"MCP error: {reply['error'].get('message', reply['error'])}")
        result = reply.get("result") or {}
        page = result.get("structuredContent")
        if result.get("isError") or not isinstance(page, dict):
            text = "".join(c.get("text", "") for c in result.get("content", []) if isinstance(c, dict))
            raise FeedError(text or "unexpected MCP response")
        if "error" in page:
            raise FeedError(page["error"])
        return page
    raise FeedError("authentication failed; run `conduct login`")


def _read_cursor(path: Path) -> str | None:
    try:
        return path.read_text().strip() or None
    except OSError:
        return None


def _save_cursor(path: Path, cursor: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w") as fh:
        fh.write(cursor)
    os.replace(tmp, path)


def run_feed(*, since: str | None, limit: int, follow: bool, interval: float,
             state: Path, out, sleep=time.sleep, fmt: str = "json", sink=None) -> int:
    """Write events to ``out`` until caught up (or forever with ``follow``). Returns events written."""
    cursor = _read_cursor(state)
    written = 0
    render = FORMATTERS[fmt]
    while True:
        args: dict = {"limit": limit}
        if cursor:
            args["cursor"] = cursor
        elif since:
            args["since"] = since
        page = _call_tool(args)
        events = page.get("events", [])
        if sink is not None:
            sink.send(events)  # returns only once every batch is acknowledged
            written += len(events)
        else:
            for event in events:
                out.write(render(event) + "\n")
                written += 1
            out.flush()
        cursor = page.get("next_cursor") or cursor
        if cursor:
            _save_cursor(state, cursor)
        if page.get("has_more"):
            continue
        if not follow:
            return written
        sleep(interval)


def cmd_audit_feed(args) -> None:
    from conduct_cli.audit_sinks import SinkError, build_sink
    state = Path(args.state).expanduser() if args.state else DEFAULT_STATE
    sink_name = getattr(args, "sink", None)
    try:
        if sink_name and args.output:
            raise FeedError("--sink and --output are mutually exclusive")
        sink = build_sink(args) if sink_name else None
    except (SinkError, FeedError) as exc:
        print(f"conduct audit feed: {exc}", file=sys.stderr)
        sys.exit(1)
    out = open(args.output, "a", encoding="utf-8") if args.output else sys.stdout
    try:
        written = run_feed(since=args.since, limit=args.limit, follow=args.follow,
                           interval=args.interval, state=state, out=out,
                           fmt=getattr(args, "format", None) or "json", sink=sink)
        if args.output:
            print(f"{written} events appended to {args.output}", file=sys.stderr)
        elif sink is not None:
            print(f"{written} events delivered to {sink_name}", file=sys.stderr)
    except (FeedError, SinkError) as exc:
        print(f"conduct audit feed: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass
    finally:
        if args.output:
            out.close()


def register_feed(audit_sub) -> None:
    f = audit_sub.add_parser("feed", help="Stream audit events as NDJSON for a SIEM collector")
    f.add_argument("--since", help="ISO-8601 start for a new feed (default: last 24 hours); ignored once a cursor is saved")
    f.add_argument("--follow", action="store_true", help="Keep polling for new events")
    f.add_argument("--interval", type=float, default=60.0, help="Seconds between polls with --follow (default: 60)")
    f.add_argument("--limit", type=int, default=500, help="Events per request, 1-1000 (default: 500)")
    f.add_argument("--state", help=f"Cursor checkpoint file (default: {DEFAULT_STATE})")
    f.add_argument("--format", choices=FORMATS, default="json",
                   help="Output format: json (native, default), ocsf (OCSF 1.3 API Activity), ecs (Elastic ECS 8.x), "
                        "cef (ArcSight CEF). Hash-chain fields are kept in every format")
    f.add_argument("--output", help="Append NDJSON to this file instead of stdout")
    f.add_argument("--sink", choices=("splunk-hec", "sentinel"),
                   help="Push events to a SIEM instead of writing a file. The cursor advances only after "
                        "the destination acknowledges each page (at-least-once; dedupe on event id)")
    f.add_argument("--hec-url", help="Splunk HEC base URL, e.g. https://splunk.example.com:8088")
    f.add_argument("--hec-token-file", help="File holding the HEC token (or set $CONDUCT_HEC_TOKEN)")
    f.add_argument("--hec-index", help="Splunk index for the events")
    f.add_argument("--dce-url", help="Sentinel data collection endpoint (https://<dce>.<region>.ingest.monitor.azure.com)")
    f.add_argument("--dcr-id", help="Data collection rule immutable id (dcr-...)")
    f.add_argument("--stream", help="DCR stream name, e.g. Custom-ConductAudit_CL")
    f.add_argument("--tenant-id", help="Entra tenant id (or $AZURE_TENANT_ID)")
    f.add_argument("--client-id", help="Entra app client id (or $AZURE_CLIENT_ID)")
    f.add_argument("--client-secret-file", help="File holding the Entra client secret (or set $CONDUCT_SENTINEL_CLIENT_SECRET)")
