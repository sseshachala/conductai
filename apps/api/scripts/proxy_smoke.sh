#!/usr/bin/env bash
# End-to-end smoke for the Guard Proxy across all 3 providers.
#
# Looks up everything from the local DB so you don't have to remember IDs.
# Just give it a workspace name (or none — defaults to the first workspace
# with Guard installed + at least one seeded provider key).
#
# Run:
#   ./scripts/proxy_smoke.sh                       # auto-pick first workspace
#   ./scripts/proxy_smoke.sh "Acme Test Corp"      # use the named workspace
#
# Skips providers without seeded keys instead of failing them.

set -euo pipefail

PROXY="${CONDUCT_PROXY:-http://localhost:8000/proxy}"
DB_URL="${DATABASE_URL:-postgresql://marshal:marshal@localhost:5432/marshal}"
WORKSPACE_NAME="${1:-}"

# ── resolve workspace ────────────────────────────────────────────────────

if [[ -n "$WORKSPACE_NAME" ]]; then
  WS_ROW=$(psql "$DB_URL" -tA -F'|' -c "
    SELECT w.id::text, w.name
    FROM workspaces w
    JOIN guard_config gc ON gc.workspace_id = w.id
    WHERE w.name = '$WORKSPACE_NAME'
    LIMIT 1
  ")
  [[ -z "$WS_ROW" ]] && { echo "No workspace named '$WORKSPACE_NAME' with Guard installed."; exit 1; }
else
  WS_ROW=$(psql "$DB_URL" -tA -F'|' -c "
    SELECT w.id::text, w.name
    FROM workspaces w
    JOIN guard_config gc ON gc.workspace_id = w.id
    JOIN integrations i ON i.workspace_id = w.id AND i.handle = 'env_vars'
    ORDER BY w.created_at DESC LIMIT 1
  ")
  [[ -z "$WS_ROW" ]] && { echo "No workspaces with Guard + a seeded env_vars integration."; exit 1; }
fi
WORKSPACE_ID="${WS_ROW%%|*}"
WS_LABEL="${WS_ROW##*|}"

# ── resolve member token ─────────────────────────────────────────────────

MEMBER_TOKEN=$(psql "$DB_URL" -tA -c "
  SELECT member_token FROM guard_member_config
  WHERE workspace_id = '$WORKSPACE_ID'::uuid AND active = true LIMIT 1
")
[[ -z "$MEMBER_TOKEN" ]] && { echo "No active member token for workspace '$WS_LABEL'. Visit /guard to provision."; exit 1; }

# ── check which provider keys are seeded ─────────────────────────────────
# We can't decrypt from bash, so we ask the API to do it via a one-shot Python helper.

PROVIDERS=$(.venv/bin/python -c "
import psycopg2
from app.core.crypto import decrypt
conn = psycopg2.connect('$DB_URL')
cur = conn.cursor()
cur.execute(\"\"\"
  SELECT handle, encrypted_credentials FROM integrations
  WHERE workspace_id = '$WORKSPACE_ID'
    AND handle IN ('anthropic','openai','perplexity','env_vars')
    AND encrypted_credentials IS NOT NULL
\"\"\")
found = set()
for handle, enc in cur.fetchall():
    try:
        creds = decrypt(enc) or {}
    except Exception:
        continue
    # Per-provider handle with api_key
    if handle in ('anthropic','openai','perplexity') and creds.get('api_key'):
        found.add(handle)
    # Catch-all env_vars
    if handle == 'env_vars':
        if 'ANTHROPIC_API_KEY' in creds: found.add('anthropic')
        if 'OPENAI_API_KEY'    in creds: found.add('openai')
        if 'PERPLEXITY_API_KEY' in creds: found.add('perplexity')
print(' '.join(sorted(found)))
")

# ── header ───────────────────────────────────────────────────────────────

echo "▶ Workspace:    $WS_LABEL ($WORKSPACE_ID)"
echo "▶ Member token: guard-mt-${MEMBER_TOKEN:0:6}…"
echo "▶ Proxy:        $PROXY"
echo "▶ Available:    ${PROVIDERS:-none}"
echo

[[ -z "$PROVIDERS" ]] && { echo "Nothing to test. Seed at least one provider key via Settings → Integrations or scripts/seed_anthropic_key.py"; exit 1; }

PASS=0; FAIL=0; SKIP=0

# ── runner ───────────────────────────────────────────────────────────────

run_one() {
  local provider="$1" path="$2" auth="$3" extra="$4" body="$5"

  if [[ " $PROVIDERS " != *" $provider "* ]]; then
    echo "── $provider ── SKIP (no key seeded)"
    SKIP=$((SKIP + 1)); echo
    return
  fi

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
    $auth $extra \
    -H "\"x-conduct-ai-tool: smoke-test-$provider\"" \
    -d "'$body'")

  echo "HTTP $http_code"
  if [[ "$http_code" != "200" ]]; then
    echo "FAIL — non-200"
    head -c 300 "$resp"; echo
    FAIL=$((FAIL + 1)); rm "$resp"; echo; return
  fi

  sleep 2
  local after
  after=$(psql "$DB_URL" -tA -c "
    SELECT COUNT(*) FROM guard_audit_events
    WHERE workspace_id = '$WORKSPACE_ID'::uuid AND tool_call LIKE '$provider/%'
  ")
  if (( after > before )); then
    echo "Audit row landed (was $before → $after)"
    echo "PASS"
    PASS=$((PASS + 1))
  else
    echo "FAIL — 200 but no audit row"
    FAIL=$((FAIL + 1))
  fi
  rm "$resp"; echo
}

# ── three runs ───────────────────────────────────────────────────────────

run_one "anthropic" "/v1/messages" \
  "-H \"x-api-key: guard-mt-$MEMBER_TOKEN\"" \
  "-H \"anthropic-version: 2023-06-01\"" \
  '{"model":"claude-haiku-4-5-20251001","max_tokens":40,"messages":[{"role":"user","content":"Reply: SMOKE_OK"}]}'

run_one "openai" "/openai/v1/chat/completions" \
  "-H \"Authorization: Bearer guard-mt-$MEMBER_TOKEN\"" \
  "" \
  '{"model":"gpt-4o-mini","max_tokens":40,"messages":[{"role":"user","content":"Reply: SMOKE_OK"}]}'

run_one "perplexity" "/perplexity/chat/completions" \
  "-H \"Authorization: Bearer guard-mt-$MEMBER_TOKEN\"" \
  "" \
  '{"model":"sonar","max_tokens":40,"messages":[{"role":"user","content":"Reply: SMOKE_OK"}]}'

echo "═══════════════════════════════════════════════════"
echo "Summary: $PASS pass · $FAIL fail · $SKIP skip"
exit $(( FAIL > 0 ? 1 : 0 ))
