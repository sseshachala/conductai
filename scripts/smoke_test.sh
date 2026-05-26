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

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --repo)    REPO="$2";    shift 2 ;;
    --pr)      PR="$2";      shift 2 ;;
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

# ── Step 1: Reset project ──────────────────────────────────────────────────────
echo "── Step 1: Reset project '$PROJECT' ──" | run_and_tee
conduct reset "$PROJECT" --yes 2>&1 | run_and_tee
echo "" | run_and_tee

# ── Step 2: Install all agents ────────────────────────────────────────────────
echo "── Step 2: Install all agents ──" | run_and_tee
timeout 300 conduct install-all --project "$PROJECT" --repo "$REPO" 2>&1 | run_and_tee || true
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

# ── Footer ────────────────────────────────────────────────────────────────────
EXIT_CODE=$(( EXIT_A || EXIT_B ))
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
