#!/usr/bin/env bash
# End-to-end smoke for the Guard Proxy.
#
# Verifies the full chain: dev's AI tool → Conduct proxy → real api.anthropic.com
# → response back → audit row in guard_audit_events.
#
# Prereqs (set as env vars or via 1Password, etc.):
#   CONDUCT_PROXY    proxy base URL (default: http://localhost:8000/proxy)
#   MEMBER_TOKEN     workspace member token (without the guard-mt- prefix; will be added)
#   WORKSPACE_ID     workspace uuid to verify audit row landed against
#   REAL_ANTHROPIC_KEY  used to seed the workspace's integration row if not already there
#                       (this script does NOT send your real key to the proxy)
#
# Run:
#   ./scripts/proxy_smoke.sh
#
# Pass criteria:
#   1. Proxy returns 200 with Claude's reply
#   2. New row in guard_audit_events for our workspace with ai_tool='claude-code-test'

set -euo pipefail

PROXY="${CONDUCT_PROXY:-http://localhost:8000/proxy}"
MEMBER_TOKEN="${MEMBER_TOKEN:?MEMBER_TOKEN env var required (without guard-mt- prefix)}"
WORKSPACE_ID="${WORKSPACE_ID:?WORKSPACE_ID env var required}"
DB_URL="${DATABASE_URL:-postgresql://marshal:marshal@localhost:5432/marshal}"

echo "▶ Proxy:        $PROXY"
echo "▶ Workspace:    $WORKSPACE_ID"
echo "▶ Member token: guard-mt-${MEMBER_TOKEN:0:6}…"
echo

before_count=$(psql "$DB_URL" -tA -c "
  SELECT COUNT(*) FROM guard_audit_events
  WHERE workspace_id = '$WORKSPACE_ID'::uuid
    AND tool_call LIKE 'anthropic/%'
")
echo "Audit rows for this workspace (before): $before_count"

echo
echo "▶ Calling proxy → expect Claude reply"
resp=$(mktemp)
http_code=$(curl -sS -o "$resp" -w "%{http_code}" \
  -X POST "$PROXY/v1/messages" \
  -H "Content-Type: application/json" \
  -H "x-api-key: guard-mt-$MEMBER_TOKEN" \
  -H "anthropic-version: 2023-06-01" \
  -H "x-conduct-ai-tool: claude-code-test" \
  -d '{
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 50,
    "messages": [{"role": "user", "content": "Reply with exactly: SMOKE_OK"}]
  }')

echo "HTTP $http_code"
if [[ "$http_code" != "200" ]]; then
  echo "FAIL — proxy returned non-200"
  cat "$resp"
  exit 1
fi

# Show the model's reply text
python3 - <<PY < "$resp"
import sys, json
r = json.load(sys.stdin)
content = (r.get("content") or [{}])[0].get("text", "")
print(f"▶ Claude reply: {content!r}")
print(f"▶ Stop reason:  {r.get('stop_reason')!r}")
u = r.get("usage", {})
print(f"▶ Tokens:       in={u.get('input_tokens')} out={u.get('output_tokens')}")
PY

# Wait a beat for the background audit task
sleep 2

after_count=$(psql "$DB_URL" -tA -c "
  SELECT COUNT(*) FROM guard_audit_events
  WHERE workspace_id = '$WORKSPACE_ID'::uuid
    AND tool_call LIKE 'anthropic/%'
")
echo
echo "Audit rows for this workspace (after):  $after_count"

if (( after_count > before_count )); then
  echo "▶ Last audit row:"
  psql "$DB_URL" -c "
    SELECT ts, ai_tool, tool_call, decision, tokens_before, tokens_after, duration_ms
    FROM guard_audit_events
    WHERE workspace_id = '$WORKSPACE_ID'::uuid
      AND tool_call LIKE 'anthropic/%'
    ORDER BY ts DESC LIMIT 1
  "
  echo "PASS — end-to-end working"
  rm "$resp"
  exit 0
fi

echo "FAIL — proxy returned 200 but no audit row landed (background task issue?)"
exit 1
