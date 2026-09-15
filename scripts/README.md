# scripts/

Cross-cutting smokes and dev helpers. The **umbrella** lives here.

## Smokes (run these to verify the deployment)

| File | Scope |
|---|---|
| `smoke_all.sh` | **Umbrella** — invokes every Guard surface: core, LiteLLM plugin, NeMo plugin, Gateway HTTP + audit, frontend Playwright. Defaults to prod. |
| `smoke_1755.sh` | Guard core matrix (coverage / rule fires / divergence / Cedar). |
| `smoke_plugin.sh`, `smoke_plugin_live.py` | conduct-litellm-guard plugin end-to-end. |
| `smoke_trial.sh` | Try-It verb flow (epic #1567). |
| `smoke_test.sh` | Reserved smoke project reset. |

Run: `bash scripts/smoke_all.sh` (with `~/.conduct/config.json` populated).

## Where else smokes live

- **`apps/api/scripts/*smoke*`** — API-only smokes (need local DB / KMS).
- **`apps/web/e2e/`** — frontend Playwright (opt-in via `SMOKE_WEB=1`).
- **`tools/security-e2e/`** — separate authenticated security harness.

## Dev helpers (not smokes — one-off tools)

Prefixed `dev_*` so they don't get mistaken for smokes:

- `dev_autopilot_node.py` — Autopilot agent trigger against a testbed repo.
- `dev_github_webhook.py` — GitHub PAT webhook capability probe.
- `dev_hooks_and_booster.sh` — Claude Code hook + Agent Booster RRF check.

## CI hook

`.github/workflows/smoke-gateway.yml` runs `apps/api/scripts/smoke_gateway_live.py`
hourly against prod. Failure = maintainer email. Needs the
`SMOKE_GATEWAY_TOKEN` GitHub secret (a `cond_agt_*` token minted for a
smoke-only agent identity). Skips cleanly if the secret is unset.
