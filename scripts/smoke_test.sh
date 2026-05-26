#!/usr/bin/env bash
# smoke_test.sh — Reset project, install all agents, run all tests, save report.
#
# Usage:
#   ./scripts/smoke_test.sh --project DevOps --repo owner/repo
#   ./scripts/smoke_test.sh --project DevOps --repo owner/repo --pr 246
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

PR_FLAG=""
[[ -n "$PR" ]] && PR_FLAG="--pr $PR"

run_and_tee() {
  tee -a "$REPORT"
}

{
  echo "================================================================"
  echo "  Conduct Smoke Test"
  echo "  Project : $PROJECT"
  echo "  Repo    : $REPO"
  echo "  PR      : ${PR:-none}"
  echo "  Started : $(date)"
  echo "================================================================"
  echo ""
} | run_and_tee

echo "" | run_and_tee

# ── Step 1: Reset project ──────────────────────────────────────────────────────
echo "── Step 1: Reset project '$PROJECT' ──" | run_and_tee
conduct reset "$PROJECT" --yes 2>&1 | run_and_tee
echo "" | run_and_tee

# ── Step 2: Install all agents ────────────────────────────────────────────────
echo "── Step 2: Install all agents ──" | run_and_tee
# 5-minute cap per install-all; individual API calls now have 30s socket timeout
timeout 300 conduct install-all --project "$PROJECT" --repo "$REPO" 2>&1 | run_and_tee || true
echo "" | run_and_tee

# ── Step 3: Run all tests ─────────────────────────────────────────────────────
echo "── Step 3: Run all tests ──" | run_and_tee
EXIT_CODE=0
# shellcheck disable=SC2086
conduct test --all --project "$PROJECT" --repo "$REPO" $PR_FLAG 2>&1 | run_and_tee || EXIT_CODE=$?
echo "" | run_and_tee

# ── Footer ────────────────────────────────────────────────────────────────────
{
  echo "================================================================"
  echo "  Finished : $(date)"
  echo "  Report   : $REPORT"
  if [[ $EXIT_CODE -eq 0 ]]; then
    echo "  Result   : ALL PASSED"
  else
    echo "  Result   : SOME FAILED (exit $EXIT_CODE)"
  fi
  echo "================================================================"
} | run_and_tee

echo ""
echo "Report saved → $REPORT"
exit $EXIT_CODE
