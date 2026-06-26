#!/usr/bin/env bash
# End-to-end smoke for the Guard Proxy across all 3 providers.
#
# Verifies the full chain: dev's AI tool → Conduct proxy → real vendor API
# → response back → audit row in guard_audit_events. Tests whichever
# provider keys are seeded; skips the rest with a clear note.
#
# Prereqs:
#   CONDUCT_PROXY    proxy base URL (default: http://localhost:8000/proxy)
#   MEMBER_TOKEN     workspace member token (without the guard-mt- prefix)
#   WORKSPACE_ID     workspace uuid
#
# Run:
#   ./scripts/proxy_smoke.sh
#
# Pass criteria per provider:
#   1. Proxy returns 200
#   2. New audit row lands with tool_call like '<provider>/<model>'

set -euo pipefail

PROXY="${CONDUCT_PROXY:-http://localhost:8000/proxy}"
MEMBER_TOKEN="${MEMBER_TOKEN:?MEMBER_TOKEN env var required (without guard-mt- prefix)}"
WORKSPACE_ID="${WORKSPACE_ID:?WORKSPACE_ID env var required}"
DB_URL="${DATABASE_URL:-postgresql://marshal:marshal@localhost:5432/marshal}"

echo "▶ Proxy:        $PROXY"
echo "▶ Workspace:    $WORKSPACE_ID"
echo "▶ Member token: guard-mt-${MEMBER_TOKEN:0:6}…"
echo

PASS=0
FAIL=0
SKIP=0

# ── provider runner ───────────────────────────────────────────────────────

run_one() {
  local provider="$1" path="$2" model="$3" auth_header="$4" extra_headers="$5" body="$6"

  echo "── $provider ──────────────────────────────────────"
  local before
  before=$(psql "$DB_URL" -tA -c "
    SELECT COUNT(*) FROM guard_audit_events
    WHERE workspace_id = '$WORKSPACE_ID'::uuid AND tool_call LIKE '$provider/%'
  ")

  local resp http_code
  resp=$(mktemp)
  http_code=$(eval curl -sS -o "$resp" -w "%{http_code}" \
    -X POST "\"$PROXY$path\"" \
    -H "\"Content-Type: application/json\"" \
    $auth_header \
    $extra_headers \
    -H "\"x-conduct-ai-tool: smoke-test-$provider\"" \
    -d "'$body'")

  echo "HTTP $http_code"
  if [[ "$http_code" != "200" ]]; then
    echo "FAIL — $provider returned non-200"
    cat "$resp" | head -c 300
    echo
    FAIL=$((FAIL + 1))
    rm "$resp"
    return
  fi

  sleep 2
  local after
  after=$(psql "$DB_URL" -tA -c "
    SELECT COUNT(*) FROM guard_audit_events
    WHERE workspace_id = '$WORKSPACE_ID'::uuid AND tool_call LIKE '$provider/%'
  ")
  if (( after > before )); then
    echo "▶ Audit row landed (was $before, now $after)"
    echo "PASS"
    PASS=$((PASS + 1))
  else
    echo "FAIL — 200 but no audit row"
    FAIL=$((FAIL + 1))
  fi
  rm "$resp"
  echo
}

# ── anthropic ─────────────────────────────────────────────────────────────
run_one "anthropic" \
  "/v1/messages" \
  "claude-haiku-4-5-20251001" \
  "-H \"x-api-key: guard-mt-$MEMBER_TOKEN\"" \
  "-H \"anthropic-version: 2023-06-01\"" \
  '{"model":"claude-haiku-4-5-20251001","max_tokens":40,"messages":[{"role":"user","content":"Reply: SMOKE_OK"}]}'

# ── openai ────────────────────────────────────────────────────────────────
run_one "openai" \
  "/openai/v1/chat/completions" \
  "gpt-4o-mini" \
  "-H \"Authorization: Bearer guard-mt-$MEMBER_TOKEN\"" \
  "" \
  '{"model":"gpt-4o-mini","max_tokens":40,"messages":[{"role":"user","content":"Reply: SMOKE_OK"}]}'

# ── perplexity ────────────────────────────────────────────────────────────
run_one "perplexity" \
  "/perplexity/chat/completions" \
  "sonar" \
  "-H \"Authorization: Bearer guard-mt-$MEMBER_TOKEN\"" \
  "" \
  '{"model":"sonar","max_tokens":40,"messages":[{"role":"user","content":"Reply: SMOKE_OK"}]}'

echo "═══════════════════════════════════════════════════"
echo "Summary: $PASS pass · $FAIL fail · $SKIP skip"
exit $(( FAIL > 0 ? 1 : 0 ))
