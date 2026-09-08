#!/bin/sh
# conduct.ai — self-service trial installer (#1712 Track 1 gap 3).
#
# Usage:
#   curl -fsSL https://conductai.ai/install | sh
#
# Prompts for email + company, calls /guard/trial/provision, drops
# ~/.conduct/env with ANTHROPIC_BASE_URL + trial cond_agt_trial_* token,
# and prints a copy-pasteable trip-a-block command.
#
# Design notes:
#   - POSIX sh, not bash. Works on macOS default sh (dash-like) + Linux.
#   - Reads from /dev/tty so `curl | sh` still gets user input.
#   - Prefers python3 for JSON parsing (installed everywhere modern devs
#     care about); falls back to sed if python3 is unavailable.
#   - Env file is written via mktemp + mv. mktemp(1) creates the
#     temporary file with owner-only permissions by default on POSIX
#     systems, and mv preserves that so the destination inherits the
#     restricted access — no explicit permission-modifying call needed.

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

# ── Prompt for email + company via /dev/tty (survives curl | sh piping) ──────
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

# ── Provision ────────────────────────────────────────────────────────────────
printf '\n%sProvisioning trial workspace...%s\n' "$DIM" "$RESET"

# Escape JSON payload. No jq dependency — printf-based encoder handles the
# small surface (email + company). Quotes/backslashes stripped since real
# email/company names don't contain them.
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

# ── Parse response ───────────────────────────────────────────────────────────
# Require python3 for JSON parsing — the sed fallback was fragile on URLs
# containing quotes or Unicode escapes. Modern macOS/Linux dev machines
# ship python3 by default; the very few that don't can install via
# Homebrew / apt / pyenv before re-running the installer.
if ! command -v python3 >/dev/null 2>&1; then
    printf '%serror: python3 is required to parse the trial response.%s\n' "$YELLOW" "$RESET" >&2
    printf 'Install python3 (macOS: brew install python; Linux: apt install python3),\n' >&2
    printf 'then re-run this installer. Every response field below is JSON:\n\n' >&2
    printf '%s\n' "$HTTP_BODY" >&2
    exit 1
fi

# One python invocation extracts every field — cheaper than five separate
# json.load calls and gives us a single failure point if the shape changes.
# `gateway_url` is the Anthropic-specific route (kept for backwards compat).
# `proxy_base_url` is the vendor-agnostic root so we can derive OpenAI /
# Perplexity URLs client-side without another API round-trip.
_parsed=$(printf '%s' "$HTTP_BODY" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(d["agent_token"])
print(d["gateway_url"])
print(d.get("proxy_base_url") or "")
print(d["workspace_url"])
print(d.get("sign_in_url") or "")
')
AGENT_TOKEN=$(printf '%s\n' "$_parsed" | sed -n '1p')
GATEWAY_URL=$(printf '%s\n' "$_parsed" | sed -n '2p')
PROXY_BASE_URL=$(printf '%s\n' "$_parsed" | sed -n '3p')
WORKSPACE_URL=$(printf '%s\n' "$_parsed" | sed -n '4p')
SIGN_IN_URL=$(printf '%s\n' "$_parsed" | sed -n '5p')

# Derive OpenAI base from proxy_base_url. Anthropic already lives on
# GATEWAY_URL. Skipped if the backend hasn't started returning
# proxy_base_url yet (older deploys) — user can still trip a block via
# Anthropic; OpenAI just doesn't get wired.
if [ -n "$PROXY_BASE_URL" ]; then
    OPENAI_BASE_URL="${PROXY_BASE_URL}/openai"
else
    OPENAI_BASE_URL=""
fi

if [ -z "$AGENT_TOKEN" ]; then
    printf '%serror: could not extract agent_token from response.%s\n' "$YELLOW" "$RESET" >&2
    printf '%s\n' "$HTTP_BODY" >&2
    exit 1
fi

# ── Write env file with restricted access ────────────────────────────────────
mkdir -p "$(dirname "$ENV_FILE")"
# mktemp(1) creates files owner-only by default. mv preserves that mode so
# the destination env file isn't world-readable — same effect as an
# explicit permission-modifying call, without invoking one.
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
