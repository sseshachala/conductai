#!/usr/bin/env bash
# smoke_api.sh — Tier-2 curl smoke test against a running Delegator API.
#
# Pre-reqs:
#   1. API running on $API_URL (default http://localhost:8000)
#   2. Migrations applied: `alembic upgrade head`
#   3. Test user seeded: `python seed_test_user.py`
#
# Usage:
#   bash tests/smoke_api.sh                # default http://localhost:8000
#   API_URL=https://stage.delegator.io bash tests/smoke_api.sh
#
# Exit code is the number of failed checks. Prints PASS/FAIL per step with a
# one-line reason; no JSON dump unless --verbose is passed.
set -u

API_URL="${API_URL:-http://localhost:8000}"
TEST_WORKSPACE_ID="${TEST_WORKSPACE_ID:-11111111-1111-1111-1111-111111111111}"
SMOKE_EMPTY_WF_ID="${SMOKE_EMPTY_WF_ID:-22222222-2222-2222-2222-222222222222}"
VERBOSE=0
[[ "${1:-}" == "--verbose" ]] && VERBOSE=1

FAILS=0
PASSES=0
N=0

# Colourless ASCII so logs are CI-friendly.
pass() { N=$((N+1)); PASSES=$((PASSES+1)); printf "  [PASS] %-50s %s\n" "$1" "${2:-}"; }
fail() { N=$((N+1)); FAILS=$((FAILS+1));  printf "  [FAIL] %-50s %s\n" "$1" "${2:-}"; }
log()  { (( VERBOSE )) && echo "         $*" || true; }

header() { printf "\n== %s ==\n" "$1"; }

# Common curl wrapper that captures both status and body so we can assert on
# both without re-running the request.
hit() {
  # $1 method, $2 path, $3 content-type, $4 body file or '-' for none
  local method="$1" path="$2" ctype="$3" body="$4"
  local args=(-sS -o /tmp/smoke_body -w "%{http_code}" -X "$method" -H "Content-Type: $ctype" -H "X-Workspace-ID: ${TEST_WORKSPACE_ID}")
  if [[ "$body" != "-" ]]; then
    args+=(--data-binary "@$body")
  fi
  args+=("${API_URL}${path}")
  curl "${args[@]}" 2>/dev/null
}

# ─────────────────────────────────────────────────────────────────────────────
header "1. server reachable"

STATUS=$(curl -sS -o /tmp/smoke_body -w "%{http_code}" "${API_URL}/health" 2>/dev/null || echo "000")
if [[ "$STATUS" == "200" ]] && grep -q '"status":"ok"' /tmp/smoke_body; then
  pass "GET /health" "200 ok"
else
  fail "GET /health" "got $STATUS — is uvicorn running on $API_URL ?"
  echo
  echo "Exiting early: nothing else will work if the server isn't up."
  exit "$FAILS"
fi

# ─────────────────────────────────────────────────────────────────────────────
header "2. DSL endpoints (no DB writes)"

# 2a. Validate a valid YAML
cat >/tmp/smoke_yaml_good <<'YAML'
{"yaml": "name: smoke-validate\non:\n  manual:\n    next: a\nblocks:\n  a:\n    type: output\n    output:\n      via: slack\n      slack:\n        channel: '#x'\n"}
YAML
STATUS=$(hit POST /workflows/yaml/validate "application/json" /tmp/smoke_yaml_good)
if [[ "$STATUS" == "200" ]] && grep -q '"ok":true' /tmp/smoke_body; then
  pass "POST /workflows/yaml/validate (good YAML)" "200, ok=true"
else
  fail "POST /workflows/yaml/validate (good YAML)" "got $STATUS — body: $(cat /tmp/smoke_body | head -c 200)"
fi
log "$(cat /tmp/smoke_body | head -c 300)"

# 2b. Validate a broken YAML
echo '{"yaml": "name: bad\nblocks:\n  x:\n    type: not-a-real-type\n"}' >/tmp/smoke_yaml_bad
STATUS=$(hit POST /workflows/yaml/validate "application/json" /tmp/smoke_yaml_bad)
if [[ "$STATUS" == "200" ]] && grep -q '"ok":false' /tmp/smoke_body; then
  pass "POST /workflows/yaml/validate (bad YAML)" "200, ok=false (error surfaced)"
else
  fail "POST /workflows/yaml/validate (bad YAML)" "got $STATUS — should be ok=false"
fi

# 2c. graph -> YAML
cat >/tmp/smoke_graph <<'JSON'
{
  "name": "Smoke Conversion",
  "graph": {
    "nodes": [
      {"id": "_trigger", "data": {"type": "trigger", "label": "manual", "config": {"event_type": "manual"}}},
      {"id": "out", "data": {"type": "output", "integration": "slack", "config": {"channel": "#x", "integration": "slack"}}}
    ],
    "edges": [{"source": "_trigger", "target": "out"}]
  }
}
JSON
STATUS=$(hit POST /workflows/yaml/from-graph "application/json" /tmp/smoke_graph)
if [[ "$STATUS" == "200" ]] && grep -q '"yaml":' /tmp/smoke_body; then
  pass "POST /workflows/yaml/from-graph" "200, yaml returned"
else
  fail "POST /workflows/yaml/from-graph" "got $STATUS — body: $(cat /tmp/smoke_body | head -c 200)"
fi

# ─────────────────────────────────────────────────────────────────────────────
header "3. workflow CRUD (DB writes — needs seeded test workspace)"

# 3a. List workflows in test workspace (should include seeded ones)
STATUS=$(hit GET /workflows "application/json" -)
if [[ "$STATUS" == "200" ]]; then
  pass "GET /workflows" "200"
else
  fail "GET /workflows" "got $STATUS"
fi

# 3b. GET the seeded "Smoke — empty" workflow YAML
STATUS=$(hit GET "/workflows/${SMOKE_EMPTY_WF_ID}/yaml" "application/json" -)
if [[ "$STATUS" == "200" ]] && grep -q "name: Smoke" /tmp/smoke_body; then
  pass "GET /workflows/{id}/yaml" "200, YAML body returned"
else
  fail "GET /workflows/{id}/yaml" "got $STATUS — did you run seed_test_user.py ?"
fi

# 3c. GET the canonical filename
STATUS=$(hit GET "/workflows/${SMOKE_EMPTY_WF_ID}/yaml/filename" "application/json" -)
if [[ "$STATUS" == "200" ]] && grep -q 'delegator.yml' /tmp/smoke_body; then
  fname=$(grep -o '"filename":"[^"]*"' /tmp/smoke_body)
  pass "GET /workflows/{id}/yaml/filename" "$fname"
else
  fail "GET /workflows/{id}/yaml/filename" "got $STATUS"
fi

# 3d. PUT a new YAML and confirm it sticks
cat >/tmp/smoke_yaml_put <<'YAML'
name: Smoke — updated
version: 1
on:
  manual:
    next: out
blocks:
  out:
    type: output
    output:
      via: slack
      slack:
        channel: "#smoke-updated"
YAML
STATUS=$(hit PUT "/workflows/${SMOKE_EMPTY_WF_ID}/yaml" "application/x-yaml" /tmp/smoke_yaml_put)
if [[ "$STATUS" == "200" ]]; then
  pass "PUT /workflows/{id}/yaml" "200"
else
  fail "PUT /workflows/{id}/yaml" "got $STATUS — body: $(cat /tmp/smoke_body | head -c 200)"
fi

# 3e. GET it back — body must contain the new channel
STATUS=$(hit GET "/workflows/${SMOKE_EMPTY_WF_ID}/yaml" "application/json" -)
if [[ "$STATUS" == "200" ]] && grep -q "smoke-updated" /tmp/smoke_body; then
  pass "GET after PUT — content round-trips" "channel preserved"
else
  fail "GET after PUT — content round-trips" "updated channel not found"
fi

# ─────────────────────────────────────────────────────────────────────────────
header "4. cost estimate (compiled-artifacts read path)"

STATUS=$(hit GET "/workflows/${SMOKE_EMPTY_WF_ID}/estimate" "application/json" -)
if [[ "$STATUS" == "200" ]] && grep -q '"total_cost_usd"' /tmp/smoke_body; then
  pass "GET /workflows/{id}/estimate" "200, cost returned"
else
  # Estimate requires compiled_artifacts; if missing this is a known gap, not a failure
  if grep -q "no compiled version" /tmp/smoke_body 2>/dev/null; then
    pass "GET /workflows/{id}/estimate" "(no compiled artifacts yet — expected)"
  else
    fail "GET /workflows/{id}/estimate" "got $STATUS"
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
echo
echo "──────────────────────────────────────────────────────"
printf "Total: %d   Passed: %d   Failed: %d\n" "$N" "$PASSES" "$FAILS"
echo "──────────────────────────────────────────────────────"
exit "$FAILS"
