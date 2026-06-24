# Guard Token Model — Specification

**Status:** Draft v0.1
**Date:** 2026-06-24
**Author:** Conduct platform team
**Tracking issues:** #800, #801, #802, #803

---

## 1. Why this spec exists

Today, `guard_member_config.member_token` is forever-valid and passed in the URL query string. That's an acceptable launch posture but bad long-term:

- Token in URL lands in HTTP access logs, browser history, referer headers
- No expiry → leaked token = permanent compromise
- No machine-friendly refresh path for the **embed motion** (AI apps wanting to plug Conduct in for their customers)
- Conflates two distinct things: the durable identity (who is the developer) vs. the short-lived session credential (what is this MCP connection)

This spec consolidates the existing `conduct_api_keys` table with the new short-lived session token model, defines three clean issuance flows, and lays out the migration path.

---

## 2. The token taxonomy (three kinds)

| Kind | Purpose | Lifetime | Where stored | Surface |
|---|---|---|---|---|
| **Platform key** | Durable identity, server-to-server | Configurable (default 1 year) | API caller's secret manager | `conduct_api_keys` table (already exists) |
| **Member token** | Personal dev workstation MCP | 90 days | `~/.conduct/config.yaml` | `guard_member_config` table |
| **Session token** | One Guard MCP connection | 24 hours | Embedding app's process memory | New table `guard_session_tokens` |

### What stays the same

- Platform key (`conduct_api_keys`) — already shipped, already expirable, already revokable. We just use it more.

### What's new

- Member token gains expiry + rotation (issue #802)
- Session token is a new short-lived credential minted from a platform key

---

## 3. The three issuance flows

### Flow A — Personal dev workstation

The dev runs `conduct login` once, then `conduct guard sync` periodically.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ conduct login                                                            │
│   → opens browser to https://conductai.ai/cli-auth                       │
│   → user signs in via Clerk                                              │
│   → backend issues platform_key, returns to CLI                          │
│   → CLI writes to ~/.conduct/config.yaml                                 │
│                                                                          │
│ conduct guard sync                                                        │
│   → CLI calls POST /guard/tokens/refresh with platform_key               │
│   → backend mints new member_token (90-day TTL)                          │
│   → CLI writes MCP config to Claude Code, Cursor, Codex, etc.            │
│   → with Authorization: Bearer <member_token> in headers                 │
└──────────────────────────────────────────────────────────────────────────┘
```

**Refresh cadence:** automatic on every `conduct guard sync` (which devs run when policies change). If token has >30 days left, no-op; else mint fresh.

**Failure mode:** member_token expired and dev hasn't run `guard sync` → MCP client gets 401 → friendly error in client: *"Run `conduct guard sync` to refresh."*

### Flow B — CI / headless agent

A CI job (GitHub Action, GitLab CI, Jenkins) needs to run `conduct run` or call the Conduct API. No human, no interactive sign-in.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One-time setup (in CI secrets manager):                                  │
│   CONDUCT_API_KEY=<platform_key issued from /settings/api-keys>          │
│                                                                          │
│ Per-run:                                                                  │
│   conduct run autopilot.yaml                                              │
│   → reads CONDUCT_API_KEY from env                                       │
│   → calls API with X-Api-Key: <platform_key>                             │
│   → backend validates, runs                                              │
└──────────────────────────────────────────────────────────────────────────┘
```

**Refresh cadence:** none for the platform key. It lives until revoked or expired (default 1 year, user-configurable).

**Failure mode:** key revoked → 401 → CI fails → admin issues new key from `/settings/api-keys`.

### Flow C — Embedded AI app (B2B2B)

This is the new motion. An AI SaaS company embeds Conduct in their product. Their customers sign up for Conduct workspaces (or are auto-provisioned). The AI app calls Conduct on each customer's behalf.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ One-time setup (in AI app's secrets manager):                            │
│   CONDUCT_PLATFORM_KEY=<their durable embedding key, kind='embed'>       │
│                                                                          │
│ Per customer-session (e.g. each time a customer opens the AI app):       │
│   ai_app → POST /guard/tokens/session                                    │
│     headers: X-Api-Key: <platform_key>                                   │
│     body: {                                                              │
│       "workspace_id": "<customer's Conduct workspace>",                  │
│       "customer_identifier": "<customer's user id in their system>",     │
│       "ttl_seconds": 86400                                               │
│     }                                                                    │
│   ← {                                                                    │
│       "session_token": "ct_session_…",                                   │
│       "expires_at": "2026-06-25T14:00:00Z",                              │
│       "mcp_url": "https://api.conductai.ai/guard/mcp?workspace_id=<ws>"  │
│     }                                                                    │
│                                                                          │
│   ai_app starts its own MCP client pointed at mcp_url with header:       │
│     Authorization: Bearer <session_token>                                │
│                                                                          │
│   ai_app's agent makes tool calls → guard_check on every call            │
│   → policy enforced per customer's workspace rules                       │
│   → activity logged to customer's workspace audit feed                   │
│                                                                          │
│ When session ends (or every 23 hours):                                   │
│   ai_app calls POST /guard/tokens/session again, gets a fresh one        │
└──────────────────────────────────────────────────────────────────────────┘
```

**Refresh cadence:** 24-hour default TTL on session tokens. AI app refreshes near expiry.

**Failure mode:** session token expired mid-call → 401 → AI app catches, refreshes, retries once.

**Key property:** the **platform_key never leaves the AI app's backend**. Customer-facing surfaces only see ephemeral session tokens. So even if a customer extracts the session token from their browser, they get 24 hours of access scoped to their own workspace.

---

## 4. Database changes

### Migration `0030_guard_token_expiry.py`

```sql
-- Add expiry + revocation + audit fields to existing member_config
ALTER TABLE guard_member_config
  ADD COLUMN expires_at        timestamptz NULL,
  ADD COLUMN revoked_at        timestamptz NULL,
  ADD COLUMN last_used_at      timestamptz NULL,
  ADD COLUMN last_used_ip      inet NULL,
  ADD COLUMN last_used_client  varchar(100) NULL,
  ADD COLUMN token_kind        varchar(20) NOT NULL DEFAULT 'personal';

-- Grandfather existing tokens — 90 days from migration date
UPDATE guard_member_config
SET expires_at = NOW() + INTERVAL '90 days',
    token_kind = 'personal'
WHERE expires_at IS NULL;

CREATE INDEX idx_guard_member_config_active ON guard_member_config (workspace_id, member_token)
WHERE active = true AND revoked_at IS NULL;
```

### New table `guard_session_tokens`

```sql
CREATE TABLE guard_session_tokens (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id         uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  platform_key_id      varchar(36) NOT NULL REFERENCES conduct_api_keys(id) ON DELETE CASCADE,
  session_token_hash   varchar(64) NOT NULL UNIQUE,
  session_token_prefix varchar(20) NOT NULL,
  customer_identifier  varchar(255) NULL,    -- opaque, set by embedder for their attribution
  client_name          varchar(100) NULL,    -- detected from MCP initialize
  created_at           timestamptz NOT NULL DEFAULT NOW(),
  expires_at           timestamptz NOT NULL,
  revoked_at           timestamptz NULL,
  last_used_at         timestamptz NULL,
  last_used_ip         inet NULL
);

CREATE INDEX idx_guard_session_tokens_active ON guard_session_tokens (workspace_id, session_token_hash)
WHERE revoked_at IS NULL;
CREATE INDEX idx_guard_session_tokens_expiry ON guard_session_tokens (expires_at);
```

### Extend `conduct_api_keys` (already exists)

Add `kind` column to distinguish CI keys from embed keys (for analytics + TTL defaults):

```sql
ALTER TABLE conduct_api_keys
  ADD COLUMN kind        varchar(20) NOT NULL DEFAULT 'ci',  -- 'ci' | 'embed' | 'personal'
  ADD COLUMN revoked_at  timestamptz NULL;

-- Default TTL by kind (enforced in app code, not DB):
--   ci:       1 year
--   embed:    1 year
--   personal: 90 days
```

---

## 5. API endpoints

### Token management

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /guard/tokens/refresh` | Bearer or X-Api-Key | Mint new member_token for caller, invalidate old |
| `POST /guard/tokens/session` | X-Api-Key (platform key) | Mint session_token for embed flow |
| `POST /guard/tokens/{id}/revoke` | Bearer (admin only) | Instant revocation |
| `GET /guard/tokens` | Bearer | List all tokens for workspace (member + session + platform), masked |
| `POST /workspaces/{ws}/api-keys` | Bearer (already exists) | Mint platform key |
| `DELETE /workspaces/{ws}/api-keys/{id}` | Bearer (already exists) | Revoke platform key |

### Guard MCP endpoint (updated)

```python
@router.post("/guard/mcp")
async def mcp_endpoint(
    request: Request,
    workspace_id: str = Query(...),
    token: str | None = Query(None),  # legacy fallback
    db: Session = Depends(get_db),
):
    # 1. Prefer Authorization: Bearer header
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
    elif token:
        log.warning("guard.mcp.token_in_query", workspace_id=workspace_id)

    if not token:
        return _err(...)

    # 2. Try member_token first (covers Flow A: personal CLI)
    member = db.execute(_sql("""
        SELECT clerk_user_id FROM guard_member_config
        WHERE workspace_id = :w AND member_token = :t
          AND active = true
          AND (expires_at IS NULL OR expires_at > NOW())
          AND revoked_at IS NULL
        LIMIT 1
    """), {"w": ws, "t": token}).first()

    if member:
        return _handle_request(...)  # existing flow

    # 3. Fall through to session_token (covers Flow C: embed)
    session = db.execute(_sql("""
        SELECT customer_identifier, platform_key_id FROM guard_session_tokens
        WHERE workspace_id = :w AND session_token_hash = :h
          AND expires_at > NOW()
          AND revoked_at IS NULL
        LIMIT 1
    """), {"w": ws, "h": sha256(token)}).first()

    if session:
        return _handle_request(...)  # same enforcement path, different attribution

    return _err(401, "invalid_or_expired_token")
```

---

## 6. CLI changes

### `conduct login`

No change — still mints platform key (kind='personal') stored in `~/.conduct/config.yaml`.

### `conduct guard sync` (extend)

```python
def guard_sync():
    cfg = load_config()
    platform_key = cfg["api_key"]

    # Check if local member_token is near expiry
    local_token_expiry = cfg.get("guard_member_token_expires_at")
    if needs_refresh(local_token_expiry):
        r = post("/guard/tokens/refresh", headers={"X-Api-Key": platform_key})
        cfg["guard_member_token"] = r["token"]
        cfg["guard_member_token_expires_at"] = r["expires_at"]
        save_config(cfg)
        log.info("guard.member_token_refreshed")

    # Existing flow: write MCP configs to all detected clients
    write_mcp_configs(token=cfg["guard_member_token"], use_header_auth=True)
```

### `conduct guard tokens` (new)

```bash
conduct guard tokens                # list workspace tokens, masked, with last_used
conduct guard tokens rotate         # mint new member_token, invalidate old
conduct guard tokens revoke <id>    # admin-only, revoke any token
```

### `conduct api-keys` (already exists, extend)

```bash
conduct api-keys list
conduct api-keys create --name "embed-prod" --kind embed --ttl 1y
conduct api-keys revoke <id>
```

---

## 7. UI changes

### `/settings/tokens` (new tab)

Single source of truth for all credential types in this workspace:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Tokens                                                                  │
│                                                                         │
│ Platform keys (durable, server-to-server)                               │
│ ┌───────────────────────────────────────────────────────────────────┐  │
│ │ Name        Kind    Created      Last used      Expires    Actions│  │
│ │ embed-prod  embed   2026-06-20   3 hr ago       Jun 2027   Revoke │  │
│ │ ci-github   ci      2026-05-12   12 min ago     May 2027   Revoke │  │
│ │ + New platform key                                                 │  │
│ └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│ Member tokens (developer workstation, MCP)                              │
│ ┌───────────────────────────────────────────────────────────────────┐  │
│ │ Member         Created      Last used       Last client    Actions│  │
│ │ sudhi@…       2026-06-24   2 min ago       Claude Desktop  Rotate │  │
│ │                                                            Revoke │  │
│ └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│ Active sessions (embed flow)                                            │
│ ┌───────────────────────────────────────────────────────────────────┐  │
│ │ Customer       Parent key   Created        Expires    Actions     │  │
│ │ acme-corp-12   embed-prod   3 hr ago       in 21 hr   Revoke      │  │
│ │ beta-co-44     embed-prod   5 min ago      in 23 hr   Revoke      │  │
│ └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### `/settings/embed` (new — covers Flow C)

Setup wizard for AI app builders:

1. Mint platform_key (kind='embed')
2. Show code samples in Python / TypeScript / Go for the `POST /guard/tokens/session` flow
3. Show the MCP URL shape
4. Test mint a session token, validate it works against the MCP endpoint
5. Link to `/solutions/embed` marketing page

---

## 8. Migration plan

### Phase 1 — Header auth + log scrubbing (issues #800 + #801)

**Timing:** Today, ~45 min.

- Accept `Authorization: Bearer` header on all `/guard/mcp` endpoints
- Keep URL `?token=` for Claude.ai web compat with deprecation log
- Middleware scrubs `token=` from access logs

No DB migration, no breaking change.

### Phase 2 — Migration `0030_guard_token_expiry` (issue #802)

**Timing:** This week.

- Add expiry/revocation/audit columns to `guard_member_config`
- Create `guard_session_tokens` table
- Extend `conduct_api_keys` with `kind` column
- Grandfather existing tokens with 90-day expiry

Backwards compatible — existing tokens keep working until they hit grandfathered expiry.

### Phase 3 — CLI auto-refresh (issue #802 cont.)

**Timing:** This week, ships with conduct-cli 0.6.0.

- `conduct guard sync` detects upcoming expiry and refreshes
- Banner in CLI when token is <7 days from expiry
- New `conduct guard tokens` command

### Phase 4 — Session token endpoint (new issue #804 to be filed)

**Timing:** Next week.

- `POST /guard/tokens/session` endpoint
- MCP endpoint validates session_tokens
- Settings → Embed setup wizard
- `/solutions/embed` marketing page
- One reference customer, then announce as the embed motion

### Phase 5 — Deprecate URL token (issue #800 cleanup)

**Timing:** 30 days after Phase 4, when Claude.ai web supports headers.

- Drop URL `?token=` fallback
- Migrate any remaining tokens to header-only

---

## 9. Security properties (the design contract)

### Platform keys

- Hashed at rest (sha256, never plaintext in DB)
- Only the full key is shown ONCE at creation — user must save it
- Last-used timestamp + IP logged on every use
- Rate limit: 1000 req/min per key (DDoS guard)

### Member tokens

- Hashed at rest
- 90-day default TTL, refresh extends not resets
- Bound to a single workspace + a single Clerk user
- Auto-rotation via `conduct guard sync`

### Session tokens

- Hashed at rest
- 24-hour default TTL (configurable up to 7 days)
- Bound to a platform_key AND a workspace
- Customer_identifier opaque to Conduct — embedder's choice
- Revocation cascades from parent platform_key revoke

### Cross-cutting

- All tokens land in `last_used_at` + `last_used_ip` + `last_used_client` on validation
- Settings UI shows all three categories with one-click revoke
- Audit log entry on every mint + every revoke
- `/guard/activity` shows authentication failures (401s) so admins can spot abuse

---

## 10. Open questions

1. **Member token rotation UX** — when CLI auto-refreshes during `guard sync`, do we show the user a banner? Or silent unless near-expiry?
2. **Platform key TTL** — default 1 year. Should embed keys default shorter (90 days) given the higher blast radius if leaked?
3. **Customer revocation** — when an AI app's customer churns, who revokes their session tokens? The embedder via API, or auto-revoke when their workspace is deleted?
4. **Multi-region** — if we ever ship EU region, session tokens minted in US shouldn't be valid in EU. Add region to token payload?
5. **Token format** — currently `secrets.token_urlsafe(24)`. Consider prefixing with `ct_session_`, `ct_member_`, `ct_platform_` for human disambiguation in logs/UIs (like Stripe's `sk_test_`, `sk_live_`).

---

## 11. Out of scope (deliberately not in v1)

- OAuth 2.0 client credentials flow (later, when an enterprise customer asks)
- mTLS for the embed motion (later, much later)
- Per-tool scopes ("this token can only call guard_check, not guard_activity") — current model is workspace-scoped, not capability-scoped
- Token usage quotas per platform_key (rate limit covers DDoS, but no budget enforcement yet)
- SSO-integrated token issuance (currently sits on top of Clerk, not behind it)

---

## 12. Acceptance criteria (when this spec is "done")

- [ ] All three flows (A, B, C) have a runnable demo
- [ ] No tokens visible in HTTP access logs (verified by grepping production logs after Phase 1)
- [ ] Settings → Tokens page shows all three categories with revoke working
- [ ] At least one external developer has used `POST /guard/tokens/session` to embed Conduct in their app
- [ ] CLI auto-refresh has fired in a real session and the user didn't notice (verified via support ticket count = 0)
- [ ] `/solutions/embed` marketing page is live with a working code sample

---

## 13. Related spec docs

- `NORTHSTAR.md` — Layer 6 (Trust & Compliance) where governance lives
- `NORTHSTAR_GOVERNANCE.md` — operational spec for the AI Governance surface
- `ROLES.md` — RBAC model that token scopes inherit
- `DESIGN.md` — UI rules for the tokens settings page
