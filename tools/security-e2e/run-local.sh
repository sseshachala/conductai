#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

exec rtk proxy python3.11 tools/security-e2e/local.py test \
  --credentials-file .local_secret \
  --allow-test-users \
  --database-mode restricted \
  "$@"
