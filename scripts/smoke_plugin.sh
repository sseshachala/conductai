#!/usr/bin/env bash
# smoke_plugin.sh — proves the conduct-litellm-guard plugin's exact
# request path works end-to-end for a given trial (or prod) agent token.
#
# Three stages, all required to be green before handing a trial token
# to an external plugin reviewer:
#   1. wire-format smoke — raw curl POSTs to api.conductai.ai/mcp
#      (proves the endpoint + auth + payload shape work).
#   2. plugin-code smoke — runs the actual GuardCheckClient from
#      packages/conduct-litellm-guard/src/ against prod (proves the
#      exact code path LiteLLM invokes at pre_call time, including
#      the GuardDecision string parser that decides block vs allow).
#   3. LLM gateway smoke — smoke_trial.sh's allow/warn/block/prove
#      against api.conductai.ai/proxy.
#
# Usage:
#   TOKEN=cond_agt_xxx \
#   HOSTILE_PROMPT='<the canary Guard blocks — see docs>' \
#   ./scripts/smoke_plugin.sh
#
# HOSTILE_PROMPT is required at runtime (not hardcoded in this file)
# because the local ConductGuard hook correctly blocks writing any
# known prompt-injection canary to disk. Pick a prompt Guard's proxy
# persona currently blocks — the /theguard/try page's "block" verb
# text is the reference.
#
# Optional:
#   GATEWAY_URL="https://…"   override the LLM gateway base URL
#                             (default: https://api.conductai.ai/proxy)
#   PYTHON="path/to/python"   Python 3.11+ for stage 2
#                             (default: apps/api/.venv/bin/python)
#
# Exit 0 = all three stages behave as expected.

set -u
: "${TOKEN:?set TOKEN (paste your trial agent token from /theguard/try)}"
: "${HOSTILE_PROMPT:?set HOSTILE_PROMPT (see /theguard/try 'block' verb text)}"

MCP='https://api.conductai.ai/mcp'
GATEWAY_URL="${GATEWAY_URL:-https://api.conductai.ai/proxy}"
BENIGN='Say hi in one short sentence.'
FAIL=0

hit_mcp() {
  local label="$1" prompt="$2" want_prefix="$3"
  local body status text
  body=$(curl -sS -o /tmp/smoke_plugin.$$ -w '%{http_code}' -X POST "$MCP" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -H 'X-Claude-Surface: litellm' \
    -d "$(printf '{"jsonrpc":"2.0","id":"%s","method":"tools/call","params":{"name":"guard_check_prompt","arguments":{"prompt":%s}}}' "$label" "$(printf '%s' "$prompt" | jq -Rs .)")")
  status="$body"
  body=$(cat /tmp/smoke_plugin.$$); rm -f /tmp/smoke_plugin.$$
  text=$(printf '%s' "$body" | jq -r '.result.content[0].text // .error.message // "<no text>"' 2>/dev/null)
  printf '%-8s HTTP %s  %s\n' "$label" "$status" "$(printf '%s' "$text" | head -c 120 | tr '\n' ' ')"
  if [ "${status:0:1}" != "2" ]; then FAIL=1; fi
  if ! printf '%s' "$text" | grep -qE "^${want_prefix}"; then FAIL=1; fi
}

echo '== [1/3] wire format (api.conductai.ai/mcp — guard_check_prompt) =='
hit_mcp benign  "$BENIGN"          '(ok|allow|advisory)'
hit_mcp hostile "$HOSTILE_PROMPT"  'BLOCKED'

echo
echo '== [2/3] plugin code (conduct_litellm_guard.GuardCheckClient live) =='
PYTHON="${PYTHON:-$(dirname "$0")/../apps/api/.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  echo "SKIP — $PYTHON not executable. Set PYTHON=path/to/python3.11 to run stage 2."
else
  TOKEN="$TOKEN" HOSTILE_PROMPT="$HOSTILE_PROMPT" \
    "$PYTHON" "$(dirname "$0")/smoke_plugin_live.py" || FAIL=1
fi

echo
echo "== [3/3] LLM gateway ($GATEWAY_URL — allow/warn/block/prove) =="
TRIAL_TOKEN="$TOKEN" GATEWAY_URL="$GATEWAY_URL" bash "$(dirname "$0")/smoke_trial.sh" || FAIL=1

echo
if [ "$FAIL" = "0" ]; then echo 'OK — wire + plugin + gateway all green'; else echo 'FAIL — see rows above'; fi
exit "$FAIL"
