#!/usr/bin/env bash
# Generate a scored eval edition across all canonical models.
#
# Usage:
#   ./scripts/gen_edition.sh                  # edition slug = today's date (e.g. 20260529)
#   ./scripts/gen_edition.sh 002              # explicit slug → edition-002.json
#   ./scripts/gen_edition.sh 002 pr_reviewer  # single playbook only
#
# Output: apps/api/reports/baselines/edition-<SLUG>.json
# Requires: ANTHROPIC_API_KEY in env

set -euo pipefail

EDITION="${1:-$(date +%Y%m%d)}"
PLAYBOOK="${2:-}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$REPO_ROOT/apps/api"

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "ERROR: ANTHROPIC_API_KEY is not set" >&2
  exit 1
fi

echo "=================================================="
echo "  Conduct Eval — Edition: $EDITION"
[[ -n "$PLAYBOOK" ]] && echo "  Playbook: $PLAYBOOK"
echo "  Models:   haiku → sonnet → opus"
echo "  Flags:    --live --judge --all-models --publish"
echo "=================================================="
echo ""

cd "$API_DIR"

CMD=(python -m eval.runner --live --judge --all-models --publish --edition "$EDITION")
[[ -n "$PLAYBOOK" ]] && CMD+=(--playbook "$PLAYBOOK")

"${CMD[@]}"

echo ""
echo "Done. Edition manifest: reports/baselines/edition-${EDITION}.json"
