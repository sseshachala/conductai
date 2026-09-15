#!/usr/bin/env bash
# Umbrella smoke — every Guard surface in one run.
#
# Runs against a live API (defaults to prod) with the caller's Conduct
# token from ~/.conduct/config.json:
#
#   Guard core (coverage / matrix / rule fires / divergence / Cedar)
#   LiteLLM plugin  (guard_check_prompt via /mcp — same path the LiteLLM
#                    proxy takes at request time)
#   NeMo plugin     (guard_check_prompt via /mcp — same path the NeMo
#                    Colang input rail takes at request time)
#
# This is the "pre-release" smoke — run it before tagging a new plugin
# release or after any change to app/guard/gateway.py, mcp_impls.py, or
# apps/api/app/modules/guard/enforcement.py to make sure every downstream
# surface still fires.
#
# Run:
#   bash scripts/smoke_all.sh                       # against prod
#   API=http://localhost:8000 bash scripts/smoke_all.sh
#
# Individual smokes can still be invoked standalone (see each script).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export API="${API:-https://api.conductai.ai}"

# Auto-hydrate CONDUCT_TOKEN + WORKSPACE_ID from ~/.conduct/config.json.
# smoke_1755.sh expects WORKSPACE_ID in the env; falling back to /whoami
# doesn't work against every deployment. Hydrate both up front so every
# section downstream gets a consistent env.
if command -v jq >/dev/null 2>&1 && [[ -f "$HOME/.conduct/config.json" ]]; then
    if [[ -z "${CONDUCT_TOKEN:-}" ]]; then
        CONDUCT_TOKEN="$(jq -r '.agent_token // empty' "$HOME/.conduct/config.json" 2>/dev/null || true)"
        export CONDUCT_TOKEN
    fi
    if [[ -z "${WORKSPACE_ID:-}" ]]; then
        WORKSPACE_ID="$(jq -r '.workspace_id // empty' "$HOME/.conduct/config.json" 2>/dev/null || true)"
        export WORKSPACE_ID
    fi
fi
if [[ -z "${CONDUCT_TOKEN:-}" ]]; then
    echo "error: CONDUCT_TOKEN not set and ~/.conduct/config.json missing/empty. Run: conduct login" >&2
    exit 2
fi

# ── colors ────────────────────────────────────────────────────────────
c_bold="\033[1m"; c_cyan="\033[36m"; c_green="\033[32m"; c_red="\033[31m"; c_dim="\033[90m"; c_off="\033[0m"

_section() {
    printf "\n${c_cyan}${c_bold}▸ %s${c_off}\n" "$1"
    printf "${c_dim}  %s${c_off}\n" "$2"
}

_result() {
    local rc="$1"; local label="$2"
    if [[ "$rc" -eq 0 ]]; then
        printf "  ${c_green}✓ %s pass${c_off}\n" "$label"
    else
        printf "  ${c_red}✗ %s FAIL (exit $rc)${c_off}\n" "$label"
    fi
}

total_fail=0

# ── 1. Guard core smoke (existing) ───────────────────────────────────
_section "1. Guard core" "coverage matrix + rule fires + divergence + Cedar"
API="$API" bash "$REPO_ROOT/scripts/smoke_1755.sh"
rc=$?
_result "$rc" "guard-core"
total_fail=$((total_fail + (rc != 0 ? 1 : 0)))

# ── 2. LiteLLM plugin surface ────────────────────────────────────────
# Needs a running LiteLLM proxy at $LITELLM_URL (default http://localhost:4000).
# When it's not reachable the smoke can't verify the plugin's request path, so
# skip cleanly — a red X for missing local infra isn't a useful signal.
_section "2. LiteLLM plugin" "prompt-gate rules via guard_check_prompt"
LITELLM_URL="${LITELLM_URL:-http://localhost:4000}"
if curl -sSf -o /dev/null --connect-timeout 2 "$LITELLM_URL/health" 2>/dev/null \
    || curl -sSf -o /dev/null --connect-timeout 2 "$LITELLM_URL/" 2>/dev/null; then
    CONDUCT_API_URL="$API" python3.11 "$REPO_ROOT/packages/conduct-litellm-guard/examples/test_conduct_guardrail.py" 3 4 9
    rc=$?
    _result "$rc" "litellm-plugin"
    total_fail=$((total_fail + (rc != 0 ? 1 : 0)))
else
    printf "  ${c_dim}skipped — LiteLLM proxy unreachable at %s (start it locally to include)${c_off}\n" "$LITELLM_URL"
fi

# ── 3. NeMo plugin surface ───────────────────────────────────────────
_section "3. NeMo plugin" "prompt-gate rules via guard_check_prompt (nemo surface)"
CONDUCT_API_URL="$API" python3.11 "$REPO_ROOT/packages/conduct-nemo-guard/examples/test_conduct_nemo.py" 3 4 6
rc=$?
_result "$rc" "nemo-plugin"
total_fail=$((total_fail + (rc != 0 ? 1 : 0)))

# ── 4. Gateway HTTP + audit (prod-capable) ──────────────────────────
# Fires one Gateway model-catalog call and verifies via GET /guard/events
# that the audit row landed with both agent_identity_id (#1971 Phase 0)
# and route (#1973) populated. No upstream cost, no DB access required.
# For local-dev with seeded provider keys use apps/api/scripts/proxy_smoke.sh
# standalone — it exercises the full 3-provider inference path.
_section "4. Gateway HTTP + audit" "GET /gateway/v1/anthropic/v1/models → asserts agent_identity_id + route"
CONDUCT_API_URL="$API" CONDUCT_TOKEN="$CONDUCT_TOKEN" python3.11 "$REPO_ROOT/apps/api/scripts/smoke_gateway_live.py"
rc=$?
_result "$rc" "gateway-audit"
total_fail=$((total_fail + (rc != 0 ? 1 : 0)))

# ── 5. Frontend Playwright smoke (opt-in) ────────────────────────────
# Runs pages.smoke.spec.ts in apps/web/e2e/. Opt-in via SMOKE_WEB=1 because
# the Playwright auth-setup needs Clerk cookies to be present locally.
_section "5. Frontend Playwright" "apps/web/e2e/pages.smoke.spec.ts"
if [[ "${SMOKE_WEB:-0}" == "1" ]]; then
    (cd "$REPO_ROOT/apps/web" && pnpm test:e2e pages.smoke.spec.ts)
    rc=$?
    _result "$rc" "web-playwright"
    total_fail=$((total_fail + (rc != 0 ? 1 : 0)))
else
    printf "  ${c_dim}skipped — set SMOKE_WEB=1 to include (needs Clerk auth-setup)${c_off}\n"
fi

echo
if [[ "$total_fail" -eq 0 ]]; then
    printf "${c_green}${c_bold}SMOKE ALL PASS${c_off} — every Guard surface fires\n"
    exit 0
else
    printf "${c_red}${c_bold}SMOKE ALL FAIL${c_off} — %d surface(s) broken (see above)\n" "$total_fail"
    exit 1
fi
