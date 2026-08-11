#!/usr/bin/env bash
# okta-verify.sh — end-to-end check of Okta JWT auth against Conduct prod.
#
# Fetches a client_credentials JWT from your Okta tenant (trying scopes
# in order until one works), hands it to /auth/whoami, and shows the
# most recent Okta verify audit events.
#
# Required env:
#   OKTA_CLIENT_SECRET   — the app's client secret
# Optional (all have sensible defaults):
#   OKTA_DOMAIN          — default: integrator-2944519.okta.com
#   OKTA_AUTH_SERVER     — default: default
#   OKTA_CLIENT_ID       — default: 0oa1677gbczxbjmcI698
#   OKTA_SCOPES          — space-separated list to try; default: a common set
#   CONDUCT_API          — default: https://api.conductai.ai
#   CONDUCT_WS           — default: ef0a7e36-42a7-4968-9e6f-ee30d8e45383
#   CONDUCT_TOKEN        — Conduct cond_agt_/cond_api_ token
#                          (default: read from ~/.conduct/config.json)

set -euo pipefail

OKTA_DOMAIN="${OKTA_DOMAIN:-integrator-2944519.okta.com}"
OKTA_DOMAIN="${OKTA_DOMAIN#https://}"
OKTA_DOMAIN="${OKTA_DOMAIN#http://}"
OKTA_DOMAIN="${OKTA_DOMAIN%/}"
OKTA_AUTH_SERVER="${OKTA_AUTH_SERVER:-default}"
OKTA_CLIENT_ID="${OKTA_CLIENT_ID:-0oa1677gbczxbjmcI698}"
OKTA_SCOPES="${OKTA_SCOPES:-agent.act okta.apps.read okta.users.read _NONE_}"
CONDUCT_API="${CONDUCT_API:-https://api.conductai.ai}"
CONDUCT_WS="${CONDUCT_WS:-ef0a7e36-42a7-4968-9e6f-ee30d8e45383}"

if [[ -z "${OKTA_CLIENT_SECRET:-}" ]]; then
    echo "ERROR: OKTA_CLIENT_SECRET is not set." >&2
    echo "  Grab it from: Okta admin → Applications → Test-AI-Agent-RefundBot → General → Client secrets → Show" >&2
    exit 2
fi

if [[ -z "${CONDUCT_TOKEN:-}" ]]; then
    CONDUCT_TOKEN=$(python3 -c "import json; print(json.load(open('$HOME/.conduct/config.json'))['agent_token'])" 2>/dev/null || echo "")
    if [[ -z "$CONDUCT_TOKEN" ]]; then
        echo "ERROR: no CONDUCT_TOKEN and could not read from ~/.conduct/config.json." >&2
        echo "  Run: conduct login" >&2
        exit 2
    fi
fi

echo "== Config =="
echo "  Okta:    https://$OKTA_DOMAIN/oauth2/$OKTA_AUTH_SERVER"
echo "  Client:  $OKTA_CLIENT_ID"
echo "  Conduct: $CONDUCT_API  ws=$CONDUCT_WS"
echo

# ── Step 1: fetch JWT, trying scopes until one works ───────────────────────
JWT=""
LAST_ERR=""
for SCOPE in $OKTA_SCOPES; do
    if [[ "$SCOPE" == "_NONE_" ]]; then
        LABEL="(no scope)"
        DATA="grant_type=client_credentials"
    else
        LABEL="scope=$SCOPE"
        DATA="grant_type=client_credentials&scope=$SCOPE"
    fi
    RESP=$(curl -s -X POST "https://$OKTA_DOMAIN/oauth2/$OKTA_AUTH_SERVER/v1/token" \
        -u "$OKTA_CLIENT_ID:$OKTA_CLIENT_SECRET" \
        -d "$DATA")
    TOK=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('access_token',''))" "$RESP" 2>/dev/null || echo "")
    if [[ -n "$TOK" ]]; then
        echo "== Step 1: got JWT ($LABEL) =="
        echo "  $(echo -n "$TOK" | head -c 60)…"
        echo
        JWT="$TOK"
        break
    else
        LAST_ERR=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('error','?')+': '+d.get('error_description','?'))" "$RESP" 2>/dev/null || echo "$RESP")
        echo "  ✗ $LABEL → $LAST_ERR"
    fi
done

if [[ -z "$JWT" ]]; then
    echo
    echo "ERROR: no scope worked. Last error: $LAST_ERR" >&2
    echo "  Define a scope in Okta admin → Security → API → Authorization Servers → default → Scopes → Add Scope" >&2
    exit 1
fi

# ── Step 2: hit /auth/whoami with the JWT ──────────────────────────────────
echo "== Step 2: /auth/whoami =="
WHOAMI=$(curl -s "$CONDUCT_API/auth/whoami?workspace_id=$CONDUCT_WS" \
    -H "Authorization: Bearer $JWT")
echo "$WHOAMI" | python3 -m json.tool
echo

KIND=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('token_kind','?'))" "$WHOAMI")
if [[ "$KIND" != "okta_jwt" ]]; then
    echo "WARNING: token_kind is '$KIND', expected 'okta_jwt'." >&2
    echo "  Check that the workspace has issuer='https://$OKTA_DOMAIN/oauth2/$OKTA_AUTH_SERVER' and jwt_auth_enabled=true." >&2
fi
echo

# ── Step 3: verify an audit event was written ──────────────────────────────
echo "== Step 3: recent Okta audit events =="
sleep 1
EVENTS=$(curl -s "$CONDUCT_API/guard/events?workspace_id=$CONDUCT_WS&rule_id=okta_jwt&limit=5" \
    -H "Authorization: Bearer $CONDUCT_TOKEN")
echo "$EVENTS" | python3 -m json.tool
echo

COUNT=$(python3 -c "import json,sys; print(len(json.loads(sys.argv[1])))" "$EVENTS")
if [[ "$COUNT" -eq 0 ]]; then
    echo "WARNING: no audit events found. Deploy may still be catching up — retry in ~30s." >&2
else
    echo "OK — $COUNT audit event(s) recorded."
fi
