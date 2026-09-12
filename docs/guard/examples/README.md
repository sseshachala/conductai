# Guard examples

## Tier enforcement verification

Cedar rules can gate on the caller's `risk_tier` via `context.risk_tier == "tier_3"`. Enforcement lives in the MCP + LLM proxy PEPs (PR #1847).

### Files

- **`tier3-no-shell.json`** — sample Cedar policy that forbids Tier 3 identities. Importable via `POST /guard/registry/import-cedar`.
- **`verify_tier.sh`** — runnable end-to-end verification. Imports the rule, fires `guard_check` as the current identity, reports whether tier enforcement fired.

### Run it

The script reads `~/.conduct/config.json` (written by `conduct login`) for `api_url`, `agent_token`, and `workspace_id` — no env vars needed:

```bash
bash docs/guard/examples/verify_tier.sh
```

Override the config path if needed:

```bash
CONDUCT_CONFIG=/path/to/other-config.json bash docs/guard/examples/verify_tier.sh
```

### Expected output

**When the caller identity is currently Tier 3:**
```
✅ Tier enforcement fired — the caller identity is currently Tier 3.
   Next: flip the identity's Tier dropdown to Tier 1 in /agent-identity,
   then rerun this script — expect 'ok' instead of BLOCKED.
```

**When the caller identity is Tier 1 or Tier 2:**
```
ℹ️  No block — the caller identity is NOT currently Tier 3.
   To verify enforcement:
     1. Open /agent-identity, find the identity for you@example.com,
        set the Tier dropdown to Tier 3.
     2. Rerun this script — expect BLOCKED.
```

Full round-trip: run once → flip tier via UI → run again. Both outcomes prove the enforcement path end-to-end.

### Cleanup

- Uninstall the `tier-controls` pack from Guard → Registry when you're done.
- Reset the Tier 3 identity back to Tier 1 via `/agent-identity` if you flipped it.
