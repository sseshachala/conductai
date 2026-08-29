#!/usr/bin/env bash
# smoke_test.sh — Reset project, install all agents, run all tests, save report.
#
# Usage:
#   ./scripts/smoke_test.sh --project DevOps --repo owner/repo
#   ./scripts/smoke_test.sh --project DevOps --repo owner/repo --pr 246
#
# Pass 1: issue/schedule/inbound agents (no PR needed)
# Pass 2: PR-based agents (skipped if --pr not provided)
#
# Output: reports/smoke_YYYYMMDD_HHMMSS.txt

set -euo pipefail

PROJECT=""
REPO=""
PR=""
TIER3=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --repo)    REPO="$2";    shift 2 ;;
    --pr)      PR="$2";      shift 2 ;;
    --tier3)   TIER3=1;      shift ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

if [[ -z "$PROJECT" || -z "$REPO" ]]; then
  echo "Usage: $0 --project <name> --repo <owner/repo> [--pr <number>]"
  exit 1
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORTS_DIR="$(dirname "$0")/../reports"
mkdir -p "$REPORTS_DIR"
REPORT="$REPORTS_DIR/smoke_${TIMESTAMP}.txt"

run_and_tee() { tee -a "$REPORT"; }

# ── Agent classification ───────────────────────────────────────────────────────
# PR-based: need a real PR number to be meaningful
PR_AGENTS=(
  "PR Reviewer"
  "Copilot / AI PR Reviewer"
  "Security Scanner"
)

# Issue/schedule/inbound: work without a PR
NON_PR_AGENTS=(
  "Autopilot Quick"
  "Autopilot + Tests"
  "Autopilot + Approval"
  "CI Failure Alert"
  "Incident Responder"
  "Dependency Updater"
  "Issue Triage"
  "Release Notes"
  "Security Patch Updater"
)

{
  echo "================================================================"
  echo "  Conduct Smoke Test"
  echo "  Project : $PROJECT"
  echo "  Repo    : $REPO"
  echo "  PR      : ${PR:-none (PR agents will be skipped)}"
  echo "  Started : $(date)"
  echo "================================================================"
  echo ""
} | run_and_tee

# ── Step 0: Tier 1 — every subcommand's --help must exit 0 ──────────────────
# Catches import breaks, argparse drift, missing deps before we touch the API.
# Source of truth: `sub.add_parser("...")` in packages/conduct-cli/src/conduct_cli/main.py
echo "── Step 0: Tier 1 — CLI --help sweep ──" | run_and_tee
TIER1_CMDS=(
  agents create credentials delete emit environments guard import-cedar install install-all
  login mcp memory playbooks projects reset run session-report sessions set skill switch sync
  test test-guard test-security test-security-verify token verify whoami
)
TIER1_FAILS=()
conduct --help >/dev/null 2>&1 || { echo "conduct --help failed" | run_and_tee; exit 1; }
for c in "${TIER1_CMDS[@]}"; do
  if ! conduct "$c" --help >/dev/null 2>&1; then
    TIER1_FAILS+=("$c")
    echo "  FAIL: conduct $c --help" | run_and_tee
  fi
done
if [[ ${#TIER1_FAILS[@]} -gt 0 ]]; then
  echo "Tier 1 failed on: ${TIER1_FAILS[*]}" | run_and_tee
  exit 1
fi
echo "  ok: ${#TIER1_CMDS[@]} subcommands" | run_and_tee
echo "" | run_and_tee

# ── Step 1: Reset project ──────────────────────────────────────────────────────
echo "── Step 1: Reset project '$PROJECT' ──" | run_and_tee
conduct reset "$PROJECT" --yes 2>&1 | run_and_tee
echo "" | run_and_tee

# ── Step 2: Install all agents ────────────────────────────────────────────────
echo "── Step 2: Install all agents ──" | run_and_tee
timeout 300 conduct install-all --project "$PROJECT" --repo "$REPO" 2>&1 | run_and_tee
echo "" | run_and_tee

# ── Step 2b: Confirm what actually landed in the workspace ───────────────────
echo "── Step 2b: Installed agents ──" | run_and_tee
conduct agents 2>&1 | run_and_tee || true
echo "" | run_and_tee

# ── Step 3a: Non-PR agents ────────────────────────────────────────────────────
echo "── Step 3a: Issue / schedule agents ──" | run_and_tee
NON_PR_ARGS=()
for name in "${NON_PR_AGENTS[@]}"; do NON_PR_ARGS+=("$name"); done

EXIT_A=0
conduct test "${NON_PR_ARGS[@]}" --project "$PROJECT" --repo "$REPO" 2>&1 | run_and_tee || EXIT_A=$?
echo "" | run_and_tee

# ── Step 3b: PR-based agents (only if --pr provided) ─────────────────────────
EXIT_B=0
if [[ -n "$PR" ]]; then
  echo "── Step 3b: PR-based agents (PR #$PR) ──" | run_and_tee
  PR_ARGS=()
  for name in "${PR_AGENTS[@]}"; do PR_ARGS+=("$name"); done

  conduct test "${PR_ARGS[@]}" --project "$PROJECT" --repo "$REPO" --pr "$PR" 2>&1 | run_and_tee || EXIT_B=$?
  echo "" | run_and_tee
else
  echo "── Step 3b: PR-based agents — SKIPPED (pass --pr <number> to enable) ──" | run_and_tee
  echo "" | run_and_tee
fi

# ── Step 4: Tier 3 — mutating commands against scratch project (opt-in) ─────
# Only run when --tier3 is passed. Nightly workflow points at the TESTING
# workspace where scratch projects are safe to create/destroy.
EXIT_C=0
if [[ $TIER3 -eq 1 ]]; then
  STAMP=$(date +%s)
  SCRATCH_PROJECT="smoke-tier3-${STAMP}"
  SCRATCH_ENV="smoke-tier3-env-${STAMP}"
  cleanup_tier3() {
    echo "── Tier 3 cleanup: removing scratch project/env ──" | run_and_tee
    conduct delete environment "$SCRATCH_ENV" --yes 2>&1 | run_and_tee || true
    conduct delete "$SCRATCH_PROJECT" --yes 2>&1 | run_and_tee || true
  }
  trap cleanup_tier3 EXIT

  echo "── Step 4: Tier 3 — mutating commands (scratch: $SCRATCH_PROJECT) ──" | run_and_tee
  {
    conduct create "$SCRATCH_PROJECT" 2>&1 &&
    conduct create environment "$SCRATCH_ENV" 2>&1 &&
    conduct set credential --environment "$SCRATCH_ENV" --key SMOKE_TEST_KEY --value "smoke-value-${STAMP}" 2>&1 &&
    conduct emit finding --severity info --type smoke-test --description "Tier 3 smoke test finding ${STAMP}" --repo "$REPO" 2>&1 &&
    conduct session-report --developer "smoke-tier3-${STAMP}" 2>&1
  } | run_and_tee || EXIT_C=$?
  echo "" | run_and_tee
else
  echo "── Step 4: Tier 3 — SKIPPED (pass --tier3 against a scratch workspace) ──" | run_and_tee
  echo "" | run_and_tee
fi

# ── Footer ────────────────────────────────────────────────────────────────────
EXIT_CODE=$(( EXIT_A || EXIT_B || EXIT_C ))
{
  echo "================================================================"
  echo "  Finished : $(date)"
  echo "  Report   : $REPORT"
  if [[ $EXIT_CODE -eq 0 ]]; then
    echo "  Result   : ALL PASSED"
  else
    echo "  Result   : SOME FAILED"
  fi
  echo "================================================================"
} | run_and_tee

echo ""
echo "Report saved → $REPORT"
exit $EXIT_CODE
