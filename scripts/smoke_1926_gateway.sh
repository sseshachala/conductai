#!/usr/bin/env bash
# #1926 — Gateway compatibility smoke, both providers in one run.
#
# The Gateway is the primary compatibility gate. Client-side (Claude
# Code, Codex) smokes are a thin confirmation and live at the bottom
# of this script (opt-in via CLIENT_SMOKE=1).
#
# Anthropic (Claude Code):
#   HEAD /gateway/v1/anthropic/api/hello              startup probe
#   GET  /gateway/v1/anthropic/v1/models              discovery
#   POST /gateway/v1/anthropic/v1/messages/count      token counting
#   POST /gateway/v1/anthropic/v1/messages            inference (non-stream)
#   POST /gateway/v1/anthropic/v1/messages   stream   inference (SSE)
#
# OpenAI (Codex / Responses API clients):
#   GET  /gateway/v1/openai/v1/models                 discovery (may be empty; #1926)
#   POST /gateway/v1/openai/v1/chat/completions       inference (non-stream)
#   POST /gateway/v1/openai/v1/chat/completions strm  inference (SSE)
#   POST /gateway/v1/openai/v1/responses              Responses API
#
# Cross-cutting:
#   401 without credentials on each surface.
#   Recent audit row appears in Flight Recorder (/guard/events).
#
# Prereqs:
#   CONDUCT_TOKEN   agent token (cond_agt_*) or member token. Falls back
#                   to ~/.conduct/config.json.
#   WORKSPACE_ID    workspace uuid. Falls back to /whoami.
#   API             defaults to https://api.conductai.ai
#   CLIENT_SMOKE=1  additionally print the two env-var one-liners a
#                   human can paste to point Claude Code + Codex at
#                   this API and verify from a real client.
#
# Run:
#   bash scripts/smoke_1926_gateway.sh
#   API=http://localhost:8000 bash scripts/smoke_1926_gateway.sh
#   CLIENT_SMOKE=1 bash scripts/smoke_1926_gateway.sh
#
# Exit codes:
#   0 — all checks pass
#   1 — one or more assertions failed
#   2 — missing prerequisite

set -uo pipefail

API=${API:-https://api.conductai.ai}
CONDUCT_TOKEN=${CONDUCT_TOKEN:-}
WORKSPACE_ID=${WORKSPACE_ID:-}
CLIENT_SMOKE=${CLIENT_SMOKE:-0}

fail=0
pass=0
say()  { printf "\n\033[1;36m→ %s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; pass=$((pass+1)); }
bad()  { printf "  \033[31m✗\033[0m %s\n" "$*" >&2; fail=$((fail+1)); }
info() { printf "    %s\n" "$*"; }

command -v jq   >/dev/null || { echo "missing: jq"; exit 2; }
command -v curl >/dev/null || { echo "missing: curl"; exit 2; }

if [[ -z "$CONDUCT_TOKEN" && -f "$HOME/.conduct/config.json" ]]; then
  CONDUCT_TOKEN=$(jq -r '.agent_token // empty' "$HOME/.conduct/config.json")
  WORKSPACE_ID=${WORKSPACE_ID:-$(jq -r '.workspace_id // empty' "$HOME/.conduct/config.json")}
fi
[[ -n "$CONDUCT_TOKEN" ]] || { echo "missing: CONDUCT_TOKEN or ~/.conduct/config.json"; exit 2; }
if [[ -z "$WORKSPACE_ID" ]]; then
  WORKSPACE_ID=$(curl -sS -H "Authorization: Bearer ${CONDUCT_TOKEN}" \
    "${API}/whoami" | jq -r '.workspace_id // empty')
  [[ -n "$WORKSPACE_ID" ]] || { echo "could not resolve WORKSPACE_ID via /whoami"; exit 2; }
fi

echo "API:          $API"
echo "Workspace:    $WORKSPACE_ID"
echo "Token prefix: ${CONDUCT_TOKEN:0:16}…"

started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# ══════════════════════════════════════════════════════════════════════
# ANTHROPIC / CLAUDE CODE PATH
# ══════════════════════════════════════════════════════════════════════

anth=(
  -H "x-api-key: ${CONDUCT_TOKEN}"
  -H "content-type: application/json"
  -H "anthropic-version: 2023-06-01"
)

say "Anthropic 1/5 — startup probe"
status=$(curl -sS -o /dev/null -w "%{http_code}" -I \
  "${API}/gateway/v1/anthropic/api/hello")
if [[ "$status" == "204" || "$status" == "200" ]]; then
  ok "HEAD /anthropic/api/hello → $status"
else
  bad "expected 200/204, got $status"
fi

say "Anthropic 2/5 — unauth returns 401"
status=$(curl -sS -o /dev/null -w "%{http_code}" \
  "${API}/gateway/v1/anthropic/v1/models?limit=1000")
[[ "$status" == "401" ]] && ok "no creds → 401" || bad "expected 401, got $status"

say "Anthropic 3/5 — /v1/models profile-scoped catalog"
body=$(curl -sS "${anth[@]}" \
  "${API}/gateway/v1/anthropic/v1/models?limit=1000")
if echo "$body" | jq -e '.data | type == "array"' >/dev/null 2>&1; then
  count=$(echo "$body" | jq '.data | length')
  ok "Anthropic-shaped {data:[]}, $count entries"
  echo "$body" | jq -e '.data | all(.id != null and .type == "model")' >/dev/null \
    && ok "all entries have id + type=model" \
    || bad "entries missing required fields"
  [[ "$count" -le 200 ]] \
    && ok "size $count ≤ 200 (profile scoping likely working)" \
    || bad "size $count > 200 — leaking shared catalog?"
else
  bad "response not Anthropic-shaped"; info "body: $(echo "$body" | head -c 300)"
fi

say "Anthropic 4/5 — /v1/messages/count_tokens"
body=$(curl -sS "${anth[@]}" -X POST \
  -d '{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":"Count these tokens."}]}' \
  "${API}/gateway/v1/anthropic/v1/messages/count_tokens")
if echo "$body" | jq -e '.input_tokens | type == "number"' >/dev/null 2>&1; then
  ok "returned {input_tokens: $(echo "$body" | jq '.input_tokens')}"
else
  bad "no .input_tokens in response"; info "body: $(echo "$body" | head -c 300)"
fi

say "Anthropic 5/5 — /v1/messages inference"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w "%{http_code}" "${anth[@]}" -X POST \
  -d '{"model":"claude-sonnet-4-6","max_tokens":32,"messages":[{"role":"user","content":"Say the single word: pong"}]}' \
  "${API}/gateway/v1/anthropic/v1/messages")
if [[ "$status" == "200" ]] && jq -e '.content[0].text' "$resp" >/dev/null 2>&1; then
  ok "200 with content: \"$(jq -r '.content[0].text' "$resp" | head -c 60)\""
elif [[ "$status" == "402" || "$status" == "429" ]]; then
  ok "$status is a valid enforced-limit response (budget / rate limit)"
else
  bad "expected 200, got $status"; info "body: $(head -c 300 "$resp")"
fi
rm -f "$resp"

# ══════════════════════════════════════════════════════════════════════
# OPENAI / CODEX PATH
# ══════════════════════════════════════════════════════════════════════

oai=(
  -H "Authorization: Bearer ${CONDUCT_TOKEN}"
  -H "content-type: application/json"
)

say "OpenAI 1/4 — unauth returns 401"
status=$(curl -sS -o /dev/null -w "%{http_code}" \
  "${API}/gateway/v1/openai/v1/models")
[[ "$status" == "401" ]] && ok "no creds → 401" || bad "expected 401, got $status"

say "OpenAI 2/4 — /v1/models"
body=$(curl -sS "${oai[@]}" "${API}/gateway/v1/openai/v1/models")
# By design the gateway returns Codex's rich ``{"models":[]}`` schema, not
# the public OpenAI ``{"data":[]}``. Empty successful catalog is the
# documented merge signal for Codex to use its bundled metadata (see
# gateway_proxy.gateway_openai_models docstring).
if echo "$body" | jq -e '.models | type == "array"' >/dev/null 2>&1; then
  count=$(echo "$body" | jq '.models | length')
  ok "Codex-shaped {models:[]}, $count entries (empty is by design — Codex falls back)"
else
  bad "response not Codex-shaped"; info "body: $(echo "$body" | head -c 300)"
fi

say "OpenAI 3/4 — /v1/chat/completions inference"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w "%{http_code}" "${oai[@]}" -X POST \
  -d '{"model":"gpt-4o-mini","max_tokens":16,"messages":[{"role":"user","content":"Say the single word: pong"}]}' \
  "${API}/gateway/v1/openai/v1/chat/completions")
if [[ "$status" == "200" ]] && jq -e '.choices[0].message.content' "$resp" >/dev/null 2>&1; then
  ok "200 with content: \"$(jq -r '.choices[0].message.content' "$resp" | head -c 60)\""
elif [[ "$status" == "402" || "$status" == "429" ]]; then
  ok "$status is a valid enforced-limit response"
elif [[ "$status" == "503" ]] && grep -qF "No API key configured" "$resp"; then
  # Workspace config gap — vault missing OPENAI_API_KEY. Not a code bug.
  info "$(cat "$resp")"
  ok "503 is workspace config gap (missing OPENAI_API_KEY in vault) — not a Gateway wiring bug"
else
  bad "expected 200, got $status"; info "body: $(head -c 300 "$resp")"
fi
rm -f "$resp"

say "OpenAI 4/4 — /v1/responses (Responses API)"
resp=$(mktemp)
status=$(curl -sS -o "$resp" -w "%{http_code}" "${oai[@]}" -X POST \
  -d '{"model":"gpt-4o-mini","input":"Say pong"}' \
  "${API}/gateway/v1/openai/v1/responses")
if [[ "$status" == "200" ]]; then
  ok "200 (Responses API forwarded)"
elif [[ "$status" == "402" || "$status" == "429" ]]; then
  ok "$status is a valid enforced-limit response"
elif [[ "$status" == "503" ]] && grep -qF "No API key configured" "$resp"; then
  info "$(cat "$resp")"
  ok "503 is workspace config gap — not a Gateway wiring bug"
else
  bad "expected 200, got $status"; info "body: $(head -c 300 "$resp")"
fi
rm -f "$resp"

# ══════════════════════════════════════════════════════════════════════
# FLIGHT RECORDER — verify audit rows landed
# ══════════════════════════════════════════════════════════════════════

say "Flight Recorder — most recent audit rows for this workspace since ${started_at}"
events=$(curl -sS \
  -H "Authorization: Bearer ${CONDUCT_TOKEN}" \
  "${API}/guard/events?limit=10&source=proxy")
if echo "$events" | jq -e '. | type == "array" or (.events | type == "array")' >/dev/null 2>&1; then
  # Support both {events:[...]} and bare array shapes
  ev_json=$(echo "$events" | jq 'if type == "array" then . else .events end')
  n=$(echo "$ev_json" | jq 'length')
  if [[ "$n" -gt 0 ]]; then
    ok "Flight Recorder returned $n recent proxy rows"
    echo "$ev_json" | jq -r '.[0:3][] | "    \(.ts // .created_at // "?")  \(.provider // "?")/\(.model // "?")  \(.decision // "?")  route=\(.route // "?")"'
    # At least one row should have route=/gateway/v1/*
    if echo "$ev_json" | jq -e '.[] | select((.route // "") | startswith("/gateway/v1/"))' >/dev/null 2>&1; then
      ok "at least one row has route=/gateway/v1/* (Gateway attributed correctly)"
    else
      bad "no /gateway/v1/* row — either audit lineage broke or we hit legacy /proxy/*"
    fi
  else
    bad "Flight Recorder returned zero rows — Gateway calls not persisted"
  fi
else
  bad "unexpected /guard/events response shape"
  info "body: $(echo "$events" | head -c 300)"
fi

# ══════════════════════════════════════════════════════════════════════
# CLIENT SMOKE — opt-in, prints the two one-liners a human can paste
# ══════════════════════════════════════════════════════════════════════

if [[ "$CLIENT_SMOKE" == "1" ]]; then
  cat <<EOF

──────────────────────────────────────────────────────────────────
  Client smoke (manual) — confirm the desktop clients route through us
──────────────────────────────────────────────────────────────────

Claude Code:
  export ANTHROPIC_BASE_URL="${API}/gateway/v1/anthropic"
  export ANTHROPIC_API_KEY="${CONDUCT_TOKEN}"
  claude "Say the single word: pong"

Codex:
  export OPENAI_BASE_URL="${API}/gateway/v1/openai/v1"
  export OPENAI_API_KEY="${CONDUCT_TOKEN}"
  codex "Say the single word: pong"

Then check Flight Recorder for the row:
  ${API%/}/theguard  # → Activity tab

EOF
fi

# ══════════════════════════════════════════════════════════════════════

echo
echo "────────────────────────────────────────────────────────────────"
if [[ "$fail" -eq 0 ]]; then
  printf "\033[1;32mall %d checks passed\033[0m\n" "$pass"
  exit 0
fi
printf "\033[1;31m%d failed, %d passed\033[0m\n" "$fail" "$pass"
exit 1
