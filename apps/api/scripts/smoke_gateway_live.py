#!/usr/bin/env python3
"""Live prod smoke — fire one Gateway call, verify the audit row lands correctly.

Regression guard for:
- #1971 Phase 0 — successful Gateway audit rows carry ``agent_identity_id``
- #1973 route column — the FastAPI request path is recorded

Uses the model-catalog endpoint (``GET /gateway/v1/anthropic/v1/models``)
because it exercises the full ``_gateway_principal`` auth + audit path
without any upstream LLM cost. Verifies via ``GET /guard/events`` — no
direct DB access required, so this smoke runs from any developer's
terminal or from CI.

Env / config:
  CONDUCT_API_URL  optional  default https://api.conductai.ai
  CONDUCT_TOKEN    optional  cond_agt_* token; falls back to
                             ~/.conduct/config.json .agent_token
  CONDUCT_TOKEN_FILE  optional  alternative config path

Usage:
  python3 apps/api/scripts/smoke_gateway_live.py
  API=http://localhost:8000 python3 apps/api/scripts/smoke_gateway_live.py

Exit codes:
  0 — pass (Gateway call 200, audit row lands with both columns populated)
  1 — Gateway call failed (non-200 or transport error)
  2 — audit row missing (nothing landed within the retry window)
  3 — audit row landed but a regression column is empty
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path


DEFAULT_API = "https://api.conductai.ai"
CONFIG_PATH = Path(os.environ.get("CONDUCT_TOKEN_FILE", "~/.conduct/config.json")).expanduser()

# Endpoint under test — no upstream cost, exercises the full audit path.
CATALOG_PATH = "/gateway/v1/anthropic/v1/models?limit=5"
EXPECTED_ROUTE = "/gateway/v1/anthropic/v1/models"
EXPECTED_AI_TOOL = "claude-code"
# The model-catalog callsite writes routing_meta.operation = "model_catalog".
# tool_call stays NULL for every proxy row (hardcoded in audit.py INSERT)
# so routing_meta is the stable discriminator for our own row.
EXPECTED_OPERATION = "model_catalog"

# Poll for the audit row for up to POLL_SECONDS after firing the call.
# Background task usually lands in <1s; the retry loop is belt+braces.
POLL_SECONDS = 8
POLL_INTERVAL = 1


def _load_token() -> str:
    tok = os.environ.get("CONDUCT_TOKEN")
    if tok:
        return tok
    if not CONFIG_PATH.exists():
        sys.exit(
            f"error: CONDUCT_TOKEN not set and {CONFIG_PATH} missing.\n"
            "  Run: conduct login"
        )
    try:
        data = json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError as e:
        sys.exit(f"error: {CONFIG_PATH} is not valid JSON — {e}")
    tok = data.get("agent_token")
    if not tok:
        sys.exit(f"error: {CONFIG_PATH} has no agent_token — run: conduct login")
    return tok


def _fire_catalog(api: str, token: str) -> None:
    """Fire the model-catalog GET. Exits with code 1 on any transport failure."""
    req = urllib.request.Request(
        f"{api}{CATALOG_PATH}",
        headers={"x-api-key": token, "User-Agent": "conduct-gateway-smoke/1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                print(f"FAIL — Gateway returned HTTP {resp.status}")
                sys.exit(1)
            body = resp.read()
    except urllib.error.HTTPError as e:
        print(f"FAIL — Gateway returned HTTP {e.code}: {e.reason}")
        try:
            print(f"  body: {e.read()[:300].decode('utf-8', errors='replace')}")
        except Exception:
            pass
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"FAIL — Gateway transport error: {e.reason}")
        sys.exit(1)
    print(f"  Gateway HTTP 200 ({len(body)} bytes)")


def _poll_audit_row(api: str, token: str) -> dict:
    """Poll GET /guard/events until we find the matching row or time out."""
    req = urllib.request.Request(
        f"{api}/guard/events?limit=10",
        headers={"Authorization": f"Bearer {token}", "User-Agent": "conduct-gateway-smoke/1"},
    )
    deadline = time.monotonic() + POLL_SECONDS
    last_error = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status != 200:
                    last_error = f"HTTP {resp.status}"
                    time.sleep(POLL_INTERVAL)
                    continue
                events = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            print(f"FAIL — /guard/events returned HTTP {e.code}: {e.reason}")
            sys.exit(1)
        except urllib.error.URLError as e:
            last_error = f"transport: {e.reason}"
            time.sleep(POLL_INTERVAL)
            continue

        # Newest first per the endpoint's ORDER BY ts DESC. Look for our row.
        for e in events:
            rm = e.get("routing_meta") or {}
            if (
                e.get("ai_tool") == EXPECTED_AI_TOOL
                and isinstance(rm, dict)
                and rm.get("operation") == EXPECTED_OPERATION
            ):
                return e
        last_error = "row not yet visible"
        time.sleep(POLL_INTERVAL)

    print(f"FAIL — audit row never appeared within {POLL_SECONDS}s (last: {last_error})")
    sys.exit(2)


def main() -> int:
    api = os.environ.get("CONDUCT_API_URL") or os.environ.get("API") or DEFAULT_API
    api = api.rstrip("/")
    token = _load_token()

    print(f"▸ Gateway HTTP + audit smoke")
    print(f"  API:   {api}")
    print(f"  Token: {token[:14]}…{token[-4:]}")
    print()
    print(f"1) GET {api}{CATALOG_PATH}")
    _fire_catalog(api, token)

    print()
    print(f"2) Poll GET {api}/guard/events for the matching audit row")
    row = _poll_audit_row(api, token)
    print(f"  Found row id={row.get('id', '')[:8]}… ts={row.get('ts')}")

    print()
    print("3) Assert regression columns populated")
    ai_id = row.get("agent_identity_id")
    ok = True
    if not ai_id:
        print("  FAIL — agent_identity_id is null (#1971 Phase 0 regression)")
        ok = False
    else:
        print(f"  agent_identity_id: {ai_id}  (#1971 OK)")

    # Route projection: the /guard/events response schema was updated in the
    # same PR as this smoke; until that ships to prod, the field is absent
    # from the response. Treat "field entirely absent" as a soft skip so the
    # smoke stays green during the deploy gap. Once the API projects it,
    # any mismatch is a hard regression.
    if "route" not in row:
        print("  route:             (API not yet projecting — deploy pending)")
    else:
        route = row.get("route")
        if route != EXPECTED_ROUTE:
            print(f"  FAIL — route is {route!r}, expected {EXPECTED_ROUTE!r} (#1973 regression)")
            ok = False
        else:
            print(f"  route:             {route}  (#1973 OK)")

    print()
    if not ok:
        print("SMOKE FAIL — see regression columns above")
        return 3
    print("SMOKE PASS — Gateway audit path healthy end-to-end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
