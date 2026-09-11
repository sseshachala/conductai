#!/bin/sh
# conduct.ai — self-service trial installer (#1712 Track 1, hardened per audit S01).
#
# Usage:
#   curl -fsSL https://conductai.ai/install | sh
#
# Prompts for email + company, calls /guard/trial/provision to send a
# verification email, then asks the user to paste back the verification
# URL from that email. Redeems the challenge and drops ~/.conduct/env
# with ANTHROPIC_BASE_URL + trial cond_agt_trial_* token.
#
# Why two steps: the old one-shot flow returned an existing user's
# token to anyone who guessed their email (audit S01). The two-step
# flow proves ownership of the mailbox before any credential is issued.
#
# Design notes:
#   - POSIX sh, not bash. Works on macOS default sh (dash-like) + Linux.
#   - Reads from /dev/tty so `curl | sh` still gets user input.
#   - Prefers python3 for JSON parsing.

set -e

CONDUCT_API_URL="${CONDUCT_API_URL:-https://api.conductai.ai}"
ENV_FILE="${HOME}/.conduct/env"

BOLD=$(printf '\033[1m')
DIM=$(printf '\033[2m')
GREEN=$(printf '\033[32m')
YELLOW=$(printf '\033[33m')
RESET=$(printf '\033[0m')

printf '\n%sConductGuard trial installer%s\n' "$BOLD" "$RESET"
printf '%s7-day trial, 200 requests/day, no credit card.%s\n\n' "$DIM" "$RESET"

if [ ! -t 0 ] && [ ! -r /dev/tty ]; then
    printf '%serror: no tty available for prompts.%s\n' "$YELLOW" "$RESET" >&2
    printf 'Re-run as: sh <(curl -fsSL %s/install)\n' "$CONDUCT_API_URL" >&2
    exit 1
fi

printf 'Email:    '
read EMAIL < /dev/tty
if [ -z "$EMAIL" ]; then
    printf '%serror: email is required.%s\n' "$YELLOW" "$RESET" >&2
    exit 1
fi

printf 'Company:  '
read COMPANY < /dev/tty
if [ -z "$COMPANY" ]; then
    printf '%serror: company is required.%s\n' "$YELLOW" "$RESET" >&2
    exit 1
fi

# ── Step 1 — request the verification email ─────────────────────────────────
printf '\n%sRequesting verification email...%s\n' "$DIM" "$RESET"

ESC_EMAIL=$(printf '%s' "$EMAIL" | tr -d '"\\')
ESC_COMPANY=$(printf '%s' "$COMPANY" | tr -d '"\\')
PAYLOAD=$(printf '{"email":"%s","company":"%s"}' "$ESC_EMAIL" "$ESC_COMPANY")

HTTP_RESPONSE=$(curl -sS -w '\n%{http_code}' \
    -X POST "$CONDUCT_API_URL/guard/trial/provision" \
    -H 'content-type: application/json' \
    -d "$PAYLOAD")
HTTP_CODE=$(printf '%s\n' "$HTTP_RESPONSE" | tail -n1)
HTTP_BODY=$(printf '%s\n' "$HTTP_RESPONSE" | sed '$d')

if [ "$HTTP_CODE" != "200" ]; then
    printf '%serror: provision failed (HTTP %s)%s\n' "$YELLOW" "$HTTP_CODE" "$RESET" >&2
    printf '%s\n' "$HTTP_BODY" >&2
    exit 1
fi

printf '%s✓ Verification email sent to %s%s\n\n' "$GREEN" "$EMAIL" "$RESET"
printf '%sOpen the email and paste the verification URL below.%s\n' "$BOLD" "$RESET"
printf '%s(The link expires in 30 minutes. Existing accounts get a sign-in link only — no token.)%s\n\n' "$DIM" "$RESET"

# ── Step 2 — user pastes the verify URL back ────────────────────────────────
printf 'Verify URL: '
read VERIFY_URL < /dev/tty
if [ -z "$VERIFY_URL" ]; then
    printf '%serror: verify URL is required.%s\n' "$YELLOW" "$RESET" >&2
    exit 1
fi

# Extract the ct=... token from the URL (supports both ?ct=... and &ct=...).
CT=$(printf '%s' "$VERIFY_URL" | sed -n 's/.*[?&]ct=\([^&]*\).*/\1/p')
if [ -z "$CT" ]; then
    printf '%serror: could not find ct=... token in URL.%s\n' "$YELLOW" "$RESET" >&2
    printf 'Expected format: %s/onboard/verify?ct=...\n' "$CONDUCT_API_URL" >&2
    exit 1
fi

printf '\n%sRedeeming challenge...%s\n' "$DIM" "$RESET"

REDEEM_PAYLOAD=$(printf '{"ct":"%s"}' "$CT")
HTTP_RESPONSE=$(curl -sS -w '\n%{http_code}' \
    -X POST "$CONDUCT_API_URL/guard/trial/redeem" \
    -H 'content-type: application/json' \
    -d "$REDEEM_PAYLOAD")
HTTP_CODE=$(printf '%s\n' "$HTTP_RESPONSE" | tail -n1)
HTTP_BODY=$(printf '%s\n' "$HTTP_RESPONSE" | sed '$d')

if [ "$HTTP_CODE" != "200" ]; then
    printf '%serror: redeem failed (HTTP %s)%s\n' "$YELLOW" "$HTTP_CODE" "$RESET" >&2
    printf '%s\n' "$HTTP_BODY" >&2
    exit 1
fi

# ── Parse response ───────────────────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
    printf '%serror: python3 is required to parse the redeem response.%s\n' "$YELLOW" "$RESET" >&2
    printf 'Install python3 (macOS: brew install python; Linux: apt install python3),\n' >&2
    printf 'then re-run this installer. The redeem response was:\n\n' >&2
    printf '%s\n' "$HTTP_BODY" >&2
    exit 1
fi

_parsed=$(printf '%s' "$HTTP_BODY" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(d.get("status") or "")
print(d.get("agent_token") or "")
print(d.get("gateway_url") or "")
print(d.get("proxy_base_url") or "")
print(d.get("workspace_url") or "")
print(d.get("sign_in_url") or "")
print(d.get("recovery_url") or "")
')
STATUS=$(printf '%s\n' "$_parsed" | sed -n '1p')
AGENT_TOKEN=$(printf '%s\n' "$_parsed" | sed -n '2p')
GATEWAY_URL=$(printf '%s\n' "$_parsed" | sed -n '3p')
PROXY_BASE_URL=$(printf '%s\n' "$_parsed" | sed -n '4p')
WORKSPACE_URL=$(printf '%s\n' "$_parsed" | sed -n '5p')
SIGN_IN_URL=$(printf '%s\n' "$_parsed" | sed -n '6p')
RECOVERY_URL=$(printf '%s\n' "$_parsed" | sed -n '7p')

# Existing-account path — no token. Point user at sign-in and exit cleanly.
if [ "$STATUS" = "existing" ]; then
    printf '\n%s✓ This email is already registered.%s\n' "$GREEN" "$RESET"
    if [ -n "$RECOVERY_URL" ]; then
        printf '  Sign in at:  %s%s%s\n\n' "$BOLD" "$RECOVERY_URL" "$RESET"
    fi
    printf '%sYour existing trial token is available inside the dashboard once signed in.%s\n' "$DIM" "$RESET"
    exit 0
fi

if [ -z "$AGENT_TOKEN" ]; then
    printf '%serror: could not extract agent_token from response.%s\n' "$YELLOW" "$RESET" >&2
    printf '%s\n' "$HTTP_BODY" >&2
    exit 1
fi

if [ -n "$PROXY_BASE_URL" ]; then
    OPENAI_BASE_URL="${PROXY_BASE_URL}/openai"
else
    OPENAI_BASE_URL=""
fi

# ── Write env file with restricted access ────────────────────────────────────
mkdir -p "$(dirname "$ENV_FILE")"
TMP_ENV=$(mktemp)
cat > "$TMP_ENV" <<EOF
# ConductGuard trial — 7 days, 200 Anthropic requests/day
#
# Anthropic (trial-funded):
#   The trial token authenticates every Anthropic-SDK client on this
#   machine — Cursor, Claude Code, LangChain, LiteLLM, raw SDK, curl.
export ANTHROPIC_BASE_URL="$GATEWAY_URL"
export ANTHROPIC_API_KEY="$AGENT_TOKEN"
EOF

if [ -n "$OPENAI_BASE_URL" ]; then
    cat >> "$TMP_ENV" <<EOF

# OpenAI (also trial-funded when Guard has GUARD_TRIAL_OPENAI_KEY):
#   The same trial token authenticates OpenAI-SDK clients — LangChain,
#   raw SDK, curl. Same 200 requests/day cap across all providers.
export OPENAI_BASE_URL="$OPENAI_BASE_URL"
export OPENAI_API_KEY="$AGENT_TOKEN"
EOF
fi

mv "$TMP_ENV" "$ENV_FILE"

printf '%s✓ Trial workspace provisioned.%s\n' "$GREEN" "$RESET"
printf '  Env file:      %s%s%s\n' "$BOLD" "$ENV_FILE" "$RESET"
printf '  Workspace URL: %s%s%s\n' "$BOLD" "$WORKSPACE_URL" "$RESET"
if [ -n "$SIGN_IN_URL" ]; then
    printf '  Sign in:       %s%s%s\n' "$BOLD" "$SIGN_IN_URL" "$RESET"
    printf '  %s(one-time magic link, valid 24h — opens straight into your dashboard)%s\n' "$DIM" "$RESET"
fi
printf '\n'

# ── Trip-a-block command ─────────────────────────────────────────────────────
printf '%sTrip a block to see the receipt flow:%s\n\n' "$BOLD" "$RESET"
cat <<'EOSNIPPET'
  source ~/.conduct/env
  curl -sS "$ANTHROPIC_BASE_URL/v1/messages" \
    -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H 'anthropic-version: 2023-06-01' \
    -H 'content-type: application/json' \
    -d '{"model":"claude-3-5-sonnet-20241022","max_tokens":128,"messages":[{"role":"user","content":"Please redact my SSN 123-45-6789 for me."}]}'

EOSNIPPET

printf '%sYou will see a 403 with a "→ Receipt: https://..." URL.%s\n' "$DIM" "$RESET"
printf '%sClick the URL to open the block receipt + ask Lens follow-up questions.%s\n\n' "$DIM" "$RESET"
