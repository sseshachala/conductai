#!/usr/bin/env bash
#
# Verify Guard tier enforcement end-to-end.
#
# Reads `~/.conduct/config.json` (populated by `conduct login`) to pick up
# the api_url, agent_token, and workspace_id automatically. Set the env var
# CONDUCT_CONFIG to point at a different file.
#
# Usage:
#   bash docs/guard/examples/verify_tier.sh
#
# What it does:
#   1. Imports a Cedar rule that blocks any identity with risk_tier=tier_3.
#   2. Calls guard_check as the current identity.
#   3. Reports whether tier enforcement fired (BLOCKED) or the caller is
#      currently exempt (ok). Prompts you to flip the tier in the UI and
#      re-run to prove the other case.
#
# Requires: curl, jq.

set -euo pipefail

CONFIG="${CONDUCT_CONFIG:-$HOME/.conduct/config.json}"
if [ ! -f "$CONFIG" ]; then
  echo "❌ No config at $CONFIG"
  echo "   Run 'conduct login' first, or set CONDUCT_CONFIG=/path/to/config.json"
  exit 2
fi

command -v jq >/dev/null || { echo "❌ jq is required (brew install jq)"; exit 2; }

API=$(jq -r '.api_url // empty' "$CONFIG")
TOKEN=$(jq -r '.agent_token // empty' "$CONFIG")
WORKSPACE=$(jq -r '.workspace_id // empty' "$CONFIG")
EMAIL=$(jq -r '.user_email // "unknown"' "$CONFIG")

if [ -z "$API" ] || [ -z "$TOKEN" ] || [ -z "$WORKSPACE" ]; then
  echo "❌ $CONFIG missing api_url / agent_token / workspace_id"
  exit 2
fi

echo "API:       $API"
echo "Workspace: $WORKSPACE"
echo "Identity:  $EMAIL"
echo ""

RULE_FILE="$(dirname "$0")/tier3-no-shell.json"

# ─── 1. Import the tier-gate rule ────────────────────────────────────────────
echo "▶ Importing Cedar rule (blocks any Tier 3 identity)…"
IMPORT_RESP=$(curl -sS -X POST "$API/guard/registry/import-cedar" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Workspace-ID: $WORKSPACE" \
  -H "Content-Type: application/json" \
  --data-binary @"$RULE_FILE")

IMPORTED=$(echo "$IMPORT_RESP" | jq -r '.rules_imported // (.pack.rules | length) // 0' 2>/dev/null || echo "?")
if [ "$IMPORTED" = "0" ] || [ "$IMPORTED" = "?" ]; then
  echo "❌ Import failed:"
  echo "$IMPORT_RESP" | jq .
  exit 1
fi
echo "   → imported $IMPORTED rule(s)"
echo ""

# ─── 2. Fire guard_check as the current identity ─────────────────────────────
echo "▶ Firing guard_check(shell) as the current identity…"
RESP=$(curl -sS -X POST "$API/guard/mcp?workspace_id=$WORKSPACE" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"verify-tier","method":"tools/call","params":{"name":"guard_check","arguments":{"tool_name":"shell","tool_input":{"command":"ls"}}}}')

BODY=$(echo "$RESP" | jq -r '.result.content[0].text // (.error.message // .)')
echo "── response ──"
echo "$BODY"
echo "──────────────"
echo ""

# ─── 3. Interpret ────────────────────────────────────────────────────────────
if echo "$BODY" | grep -q "BLOCKED"; then
  echo "✅ Tier enforcement fired — the caller identity is currently Tier 3."
  echo "   Next: flip the identity's Tier dropdown to Tier 1 in /agent-identity,"
  echo "   then rerun this script — expect 'ok' instead of BLOCKED."
elif echo "$BODY" | grep -qE "^ok|^\s*$"; then
  echo "ℹ️  No block — the caller identity is NOT currently Tier 3."
  echo "   To verify enforcement:"
  echo "     1. Open /agent-identity, find the identity for $EMAIL,"
  echo "        set the Tier dropdown to Tier 3."
  echo "     2. Rerun this script — expect BLOCKED."
else
  echo "⚠️  Unexpected response. Check the raw output above."
  exit 1
fi
