#!/usr/bin/env python3
"""
conduct-daemon — local policy enforcement proxy.

Keeps a local SQLite copy of the workspace's active policy.
Hooks talk to http://127.0.0.1:7878 instead of the remote API.
Policy updates arrive via WebSocket push; audit events are batch-flushed every 30s.

Usage:
  conduct-daemon start
  conduct-daemon stop
  conduct-daemon status
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
import urllib.request
from pathlib import Path

# ── Deps: websockets (pure-python, no heavy extras needed) ────────────────────
try:
    import websockets
except ImportError:
    print("conduct-daemon requires websockets: pip install websockets", file=sys.stderr)
    sys.exit(1)

from aiohttp import web

from conduct_daemon import enforcer, policy_store

LOG = logging.getLogger("conduct-daemon")
PORT         = int(os.environ.get("CONDUCT_DAEMON_PORT", "7878"))
FLUSH_SEC    = 30
CONFIG_PATH  = Path.home() / ".conductguard" / "config.json"
PID_PATH     = Path.home() / ".conductguard" / "daemon.pid"


# ── Config ────────────────────────────────────────────────────────────────────

def _cfg() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    except Exception:
        return {}


def _api_url() -> str:
    return _cfg().get("api_url", "https://api.conductai.ai").rstrip("/")


def _headers() -> dict:
    key = _cfg().get("api_key", "")
    return {"Authorization": f"Bearer {key}"} if key else {}


# ── Policy fetch ──────────────────────────────────────────────────────────────

def _fetch_policy(workspace_id: str, persona: str = "standard") -> dict | None:
    url = f"{_api_url()}/guard/policies/sync?workspace_id={workspace_id}&persona={persona}"
    try:
        req = urllib.request.Request(url, headers=_headers())
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read())
        policy_store.put_policy(payload)
        return payload
    except Exception as e:
        LOG.warning("policy fetch failed: %s", e)
        return None


# ── HTTP handlers ─────────────────────────────────────────────────────────────

async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "port": PORT})


async def handle_policy(request: web.Request) -> web.Response:
    workspace_id = request.query.get("workspace_id", "")
    persona      = request.query.get("persona", "standard")
    if not workspace_id:
        return web.json_response({"error": "workspace_id required"}, status=400)

    cached = policy_store.get_policy(workspace_id, persona)
    if cached:
        return web.json_response(cached)

    # Cache miss — fetch synchronously (first call or after invalidation)
    payload = await asyncio.get_event_loop().run_in_executor(
        None, _fetch_policy, workspace_id, persona
    )
    if payload:
        return web.json_response(payload)
    return web.json_response({"workspace_id": workspace_id, "persona": persona, "rules": [], "version": ""})


async def handle_check(request: web.Request) -> web.Response:
    """
    POST /check
    Body: {"workspace_id": "...", "persona": "standard", "tool_name": "bash", "tool_input": {...}, "tokens_before": 0}
    Returns: {"action": "allow|block|warn|audit", "rule_id": null, "message": null}
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    workspace_id = body.get("workspace_id", "")
    persona      = body.get("persona", "standard")
    tool_name    = body.get("tool_name", "")
    tool_input   = body.get("tool_input", {})
    tokens_before = body.get("tokens_before", 0)

    cached = policy_store.get_policy(workspace_id, persona)
    rules  = (cached or {}).get("rules", [])

    _, action, rule_id, message = enforcer.check_policy(tool_name, tool_input, rules, tokens_before)
    return web.json_response({"action": action, "rule_id": rule_id, "message": message})


async def handle_event(request: web.Request) -> web.Response:
    """POST /event — queue a single audit event for batch flush."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)
    workspace_id = body.get("workspace_id", "")
    if workspace_id:
        policy_store.queue_event(workspace_id, body)
    return web.json_response({"queued": True})


# ── WebSocket client — receives invalidation pushes ───────────────────────────

async def _ws_listener() -> None:
    cfg = _cfg()
    workspace_id = cfg.get("workspace_id")
    api_key      = cfg.get("api_key", "")
    if not workspace_id:
        LOG.info("no workspace_id in config — WS listener skipped")
        return

    ws_url = _api_url().replace("https://", "wss://").replace("http://", "ws://")
    ws_url = f"{ws_url}/guard/ws/policy?workspace_id={workspace_id}"
    if api_key:
        ws_url += f"&token={api_key}"

    backoff = 2
    while True:
        try:
            async with websockets.connect(ws_url) as ws:
                LOG.info("WS connected to %s", ws_url)
                backoff = 2
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    if msg.get("type") == "policy_invalidated":
                        ws_id = msg.get("workspace_id", workspace_id)
                        LOG.info("policy invalidated for %s — re-fetching", ws_id)
                        policy_store.invalidate(ws_id)
                        await asyncio.get_event_loop().run_in_executor(
                            None, _fetch_policy, ws_id, "standard"
                        )
        except Exception as e:
            LOG.warning("WS disconnected (%s) — retrying in %ds", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


# ── Audit flush loop ──────────────────────────────────────────────────────────

async def _audit_flusher() -> None:
    api_url = _api_url()
    while True:
        await asyncio.sleep(FLUSH_SEC)
        events = policy_store.drain_events()
        if not events:
            continue
        try:
            body = json.dumps({"events": events}).encode()
            req  = urllib.request.Request(
                f"{api_url}/guard/events/batch",
                data=body,
                headers={**_headers(), "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10):
                pass
            LOG.debug("flushed %d audit events", len(events))
        except Exception as e:
            LOG.warning("audit flush failed (%s) — events re-queued", e)
            # Re-queue on failure so nothing is lost
            cfg = _cfg()
            ws_id = cfg.get("workspace_id", "")
            for ev in events:
                policy_store.queue_event(ws_id, ev)


# ── Entry point ───────────────────────────────────────────────────────────────

async def _main() -> None:
    policy_store.init_db()

    # Pre-warm policy cache
    cfg = _cfg()
    ws_id = cfg.get("workspace_id")
    if ws_id:
        await asyncio.get_event_loop().run_in_executor(None, _fetch_policy, ws_id, "standard")

    app = web.Application()
    app.router.add_get("/health",  handle_health)
    app.router.add_get("/policy",  handle_policy)
    app.router.add_post("/check",  handle_check)
    app.router.add_post("/event",  handle_event)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", PORT)
    await site.start()

    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()))
    LOG.info("conduct-daemon listening on http://127.0.0.1:%d", PORT)

    await asyncio.gather(
        _ws_listener(),
        _audit_flusher(),
    )


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"

    if cmd == "status":
        if PID_PATH.exists():
            pid = PID_PATH.read_text().strip()
            print(f"conduct-daemon running (pid {pid}) on port {PORT}")
        else:
            print("conduct-daemon not running")
        return

    if cmd == "stop":
        if PID_PATH.exists():
            pid = int(PID_PATH.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            PID_PATH.unlink(missing_ok=True)
            print(f"stopped pid {pid}")
        else:
            print("conduct-daemon not running")
        return

    # start
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        PID_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
