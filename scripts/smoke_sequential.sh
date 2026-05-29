#!/usr/bin/env bash
# Run SmokeTest agents sequentially — one finishes before the next starts.
# Usage:
#   ./scripts/smoke_sequential.sh                    # all 12 agents
#   ./scripts/smoke_sequential.sh "CI Failure Alert" "Issue Triage"  # specific agents

set -euo pipefail

SERVER="https://api.conductai.ai"
API_KEY="cond_live_e5181942a2675be697686bba51296e86ab2470c5995e83b3f4dcfad0cbd09b3e"
WORKSPACE="ef0a7e36-42a7-4968-9e6f-ee30d8e45383"
PROJECT="SmokeTest"

CONDUCT="conduct --server $SERVER --api-key $API_KEY --workspace $WORKSPACE"

# Default order: fast/simple agents first, agentic agents last
DEFAULT_AGENTS=(
  "CI Failure Alert"
  "Issue Triage"
  "Incident Responder"
  "PR Reviewer"
  "Copilot / AI PR Reviewer"
  "Security Scanner"
  "Release Notes"
  "Dependency Updater"
  "Security Patch Updater"
  "Autopilot Quick"
  "Autopilot Full"
  "Autopilot + Approval"
)

if [[ $# -gt 0 ]]; then
  AGENTS=("$@")
else
  AGENTS=("${DEFAULT_AGENTS[@]}")
fi

PASS=0
FAIL=0
RESULTS=()

echo ""
echo "▶ Sequential smoke test — ${#AGENTS[@]} agent(s)"
echo ""

for agent in "${AGENTS[@]}"; do
  echo "── $agent"
  if $CONDUCT test "$agent" --project "$PROJECT" --repo sseshachala/conductai-testbed-python; then
    PASS=$((PASS + 1))
    RESULTS+=("✓  $agent")
  else
    FAIL=$((FAIL + 1))
    RESULTS+=("✗  $agent")
  fi
  echo ""
done

echo "════════════════════════════════════════"
echo "Results:"
for r in "${RESULTS[@]}"; do
  echo "  $r"
done
echo ""
echo "$PASS/$((PASS + FAIL)) passed"
