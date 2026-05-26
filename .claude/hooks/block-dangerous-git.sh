#!/usr/bin/env bash
# Blocks dangerous git operations — requires explicit user confirmation before proceeding.
set -euo pipefail

input=$(cat)
cmd=$(echo "$input" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('command',''))" 2>/dev/null || echo "")

dangerous_patterns=(
  "git push --force"
  "git push -f"
  "git reset --hard"
  "git clean -f"
  "git branch -D"
  "git checkout \."
  "git restore \."
)

for pattern in "${dangerous_patterns[@]}"; do
  if echo "$cmd" | grep -qE "$pattern"; then
    echo "Blocked: '$pattern' is a destructive git operation. Confirm with the user before running this." >&2
    exit 2
  fi
done

exit 0
