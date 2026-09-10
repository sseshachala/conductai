#!/usr/bin/env bash
# #1755 Slice 2 — end-to-end smoke test against a running API.
#
# Verifies that the endpoints shipped in #1751 + #1755 respond with the
# fields the Policies UI depends on. Assumes:
#   - API running at ${API:-http://localhost:8000}
#   - Valid CONDUCT_TOKEN env var (workspace member token or agent token)
#   - Optional WORKSPACE_ID (falls back to a smoke test workspace)
#
# Run:
#   API=http://localhost:8000 CONDUCT_TOKEN=cond_agt_xxx bash scripts/smoke_1755.sh
#
# Exit codes:
#   0 — all checks pass
#   1 — one or more assertions failed (details on stderr)
#   2 — missing prerequisite (jq / curl / env var)

set -euo pipefail

API=${API:-http://localhost:8000}
CONDUCT_TOKEN=${CONDUCT_TOKEN:-}
WORKSPACE_ID=${WORKSPACE_ID:-}

fail=0
say()  { printf "\033[1;36m→\033[0m %s\n" "$*"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }
bad()  { printf "  \033[31m✗\033[0m %s\n" "$*" >&2; fail=1; }

# ── Prerequisites ────────────────────────────────────────────────────
command -v jq   >/dev/null || { echo "missing: jq"; exit 2; }
command -v curl >/dev/null || { echo "missing: curl"; exit 2; }
[[ -n "$CONDUCT_TOKEN" ]]  || { echo "missing: CONDUCT_TOKEN env"; exit 2; }

hdr=(-H "Authorization: Bearer ${CONDUCT_TOKEN}" -H "Content-Type: application/json")

# Resolve workspace_id if not provided — first workspace the token can see.
if [[ -z "$WORKSPACE_ID" ]]; then
  WORKSPACE_ID=$(curl -sS "${hdr[@]}" "${API}/whoami" | jq -r '.workspace_id // empty')
  [[ -n "$WORKSPACE_ID" ]] || { echo "could not resolve WORKSPACE_ID"; exit 2; }
fi
qs="workspace_id=${WORKSPACE_ID}"

say "API=${API}  WORKSPACE_ID=${WORKSPACE_ID}"

# ── 1. Coverage matrix carries derived_<surface> per rule (#1755 PR 5) ─
say "GET /guard/policies/coverage — derived_<surface> present"
resp=$(curl -sS "${hdr[@]}" "${API}/guard/policies/coverage?${qs}")
count=$(jq 'length' <<<"$resp")
first=$(jq '.[0]' <<<"$resp")
[[ "$count" -gt 0 ]] && ok "returned ${count} rules" || bad "empty coverage response"
for k in derived_proxy derived_hook derived_mcp derived_runtime; do
  v=$(jq -r ".${k} // empty" <<<"$first")
  if [[ -n "$v" ]]; then
    ok "${k}=${v}"
  else
    bad "${k} missing on first coverage row — PR 5 didn't ship or is behind main"
  fi
done

# ── 2. Pack coverage matrix endpoint (#1751 PR 5) ───────────────────
say "GET /guard/policies/packs/conduct-base/coverage-matrix"
resp=$(curl -sS "${hdr[@]}" "${API}/guard/policies/packs/conduct-base/coverage-matrix?${qs}")
total=$(jq -r '.total_rules' <<<"$resp")
mcp_hard=$(jq -r '.by_surface.mcp.hard' <<<"$resp")
action_ct=$(jq -r '.by_gate.action' <<<"$resp")
if [[ "$total" -gt 0 && "$mcp_hard" -gt 0 && "$action_ct" -gt 0 ]]; then
  ok "total_rules=${total}  by_surface.mcp.hard=${mcp_hard}  by_gate.action=${action_ct}"
else
  bad "coverage matrix zero-filled for conduct-base — pack not installed or endpoint broken"
fi

# ── 3. Rule fires endpoint returns redacted preview (#1755 PR 3) ─────
say "GET /guard/events/rule/{first_rule}/fires — redacted"
rule_id=$(jq -r '.[0].rule_id' <<<"$(curl -sS "${hdr[@]}" "${API}/guard/policies?${qs}" | jq '.[:1]')")
if [[ -z "$rule_id" || "$rule_id" == "null" ]]; then
  bad "could not pick a rule_id from /guard/policies — workspace empty?"
else
  resp=$(curl -sS "${hdr[@]}" "${API}/guard/events/rule/${rule_id}/fires?${qs}&limit=5")
  n=$(jq 'length' <<<"$resp")
  ok "rule_id=${rule_id}  fires_returned=${n}"
  # Property 9: for any returned row, input_summary_redacted must NOT contain
  # obvious secret markers. Absence of fires is also fine.
  leaked=$(jq -r '.[] | select(.input_summary_redacted != null) | .input_summary_redacted' <<<"$resp" \
           | grep -Ei '(sk-[a-z0-9]{20,}|xox[bp]-[0-9]+-[0-9]+|-----BEGIN.*PRIVATE KEY-----)' || true)
  if [[ -z "$leaked" ]]; then
    ok "no obvious raw secrets in redacted preview"
  else
    bad "possible raw secret in redacted preview: ${leaked}"
  fi
fi

# ── 4. Divergence signal — Phase D readiness ────────────────────────
say "Divergence: hand-authored vs derived"
resp=$(curl -sS "${hdr[@]}" "${API}/guard/policies/coverage?${qs}")
divergent=$(jq '[.[] | select(
  ((.proxy == "hard" or .proxy == "not_supported") and .derived_proxy != null and .proxy != .derived_proxy) or
  ((.hook == "hard" or .hook == "not_supported") and .derived_hook != null and .hook != .derived_hook) or
  ((.mcp == "hard" or .mcp == "not_supported") and .derived_mcp != null and .mcp != .derived_mcp) or
  ((.runtime == "hard" or .runtime == "not_supported") and .derived_runtime != null and .runtime != .derived_runtime)
)] | length' <<<"$resp")
if [[ "$divergent" -eq 0 ]]; then
  ok "zero rules with authored↔derived divergence — Phase D can proceed for this workspace"
else
  ok "${divergent} rules diverge — Phase D signal (see server logs for details)"
fi

# ── Summary ─────────────────────────────────────────────────────────
echo
if [[ "$fail" -eq 0 ]]; then
  printf "\033[32mSMOKE PASS\033[0m — every endpoint responds with the expected shape\n"
else
  printf "\033[31mSMOKE FAIL\033[0m — see errors above\n"
fi
exit "$fail"
