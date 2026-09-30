# On-prem Environment Ownership

Authentication mode is implemented; it is not a claim that every SaaS environment
variable or every external integration has been verified on-prem. Do not copy a
Render/Vercel environment wholesale. Use deployment-owned credentials and URLs.
Never place provider keys, database URLs, or proxy secrets in `NEXT_PUBLIC_*`.

| Component | Required / review | SaaS difference |
| --- | --- | --- |
| API | `AUTH_MODE=proxy`, `ENVIRONMENT=production`, database, Redis, encryption key | No Clerk credentials |
| API console handoff | `CONSOLE_OIDC_ISSUER`, `CONSOLE_OIDC_CLIENT_ID`, `CONSOLE_OIDC_JWKS_URL`, optional `CONSOLE_OIDC_CA_FILE`, `CONSOLE_PROXY_SECRET` | Explicit identity mappings and workspace membership |
| Web | `AUTH_MODE=proxy`, `APP_URL`, private `API_URL`, public `API_BASE_URL`, `CONSOLE_PROXY_SECRET` | No Clerk publishable/secret key; runtime public allowlist only |
| Identity proxy | OIDC issuer, client ID, client secret, cookie secret, exact callback, PKCE S256 | Runs next to the web service, not inside Vercel by assumption |
| API links and OAuth | `API_BASE_URL`, `APP_URL`, `CONDUCT_WEB_URL`, `CONDUCT_OAUTH_ISSUER`, `ALLOWED_ORIGINS` | Set explicitly to deployment URLs; several legacy defaults target SaaS |
| Gateway/API | `CONDUCT_PROXY_URL`, provider/Vault credentials, Gateway profiles, admission flags | Local routes and published profiles; no inherited hosted Gateway |
| Worker | `AUTH_MODE`, database, Redis, encryption key, deployment link/Gateway URLs, required workspace integrations | Does not need the browser client secret or Clerk keys |
| Try Guard | `GUARD_TRIAL_ANTHROPIC_KEY` on the process serving inference | Operator-funded instead of Conduct-funded; never returned to the browser |
| Other model features | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, workspace provider credentials, optional embedding configuration | Different consumers; a general platform key is not automatically the trial key |
| Enforcement | `ADMISSION_*`, `MCP_ADMISSION_*`, `GATEWAY_ADMISSION_*`, `GUARD_GATEWAY_*`, `GUARD_DURABLE_AUDIT_*`, `BUDGET_LEDGER_*`, `AUTH_CACHE_ENABLED`, `INVALIDATION_BUS_ENABLED`, `GUARD_REQUIRE_HOOK_AUTH` | Same code, but flags/allowlists and outage behavior require deployment acceptance |
| Operations | `METRICS_TOKEN`, logging, optional `SENTRY_DSN` | Deployment-owned monitoring; review outbound export |
| Optional integrations | Resend/email, Slack, GitHub/Vercel webhooks | Not required for OIDC login; external SaaS dependencies conflict with a strict air gap |
| Legacy web MCP OAuth | `MCP_OAUTH_SECRET` for SaaS legacy routes | Legacy authorize/complete/callback routes are disabled in proxy mode; use API OAuth endpoints |

Encryption keys must be stable across services that read the same encrypted
credentials. The web/API handoff secret must match only between trusted web and
API processes. IdP client secrets belong to oauth2-proxy; they are not provider
keys and are not public web configuration.

## Retaining Try Guard

The dashboard entry remains. In proxy mode, missing operator funding or a Gateway
still pointing to Conduct SaaS yields a setup-required state before issuing a
trial identity or making a demo request. Configure a deployment-owned
`CONDUCT_PROXY_URL` and `GUARD_TRIAL_ANTHROPIC_KEY` on the inference service and
the API that checks demo readiness. Provision them through the deployment's
secret manager. Normal users never need to see or paste this shared key.

Workspace admins/developers can already add their own provider credentials through
the existing environment/credential management UI with RBAC and encryption at
rest. That normal BYO-provider path is distinct from shared trial funding; adding
a real workspace key can retire its trial identity under existing trial rules.

The current four-action demo uses Anthropic messages and a Claude model. Setting
an OpenAI key alone does not make this demo OpenAI-compatible. Arbitrary private
models and offline provider endpoints require a compatible Gateway profile and
a separate demo-provider adaptation; they are not established by OIDC support.

## Safe Preflight

Run inside each service's environment; it prints names/problems, never values:

```sh
rtk proxy python3 tools/console-e2e/env_check.py --service api
rtk proxy python3 tools/console-e2e/env_check.py --service web
rtk proxy python3 tools/console-e2e/env_check.py --service worker
```

This checks the core on-prem profile and known hosted defaults. It is not an
exhaustive inventory of every dynamic environment reader or a network test.
Validate published Gateway profiles, budgets, durable audit, caching/invalidation,
mail/notifications, and worker jobs separately with the intended rollout flags.
Hosted Skycloak is useful compatibility evidence, not proof of air-gapped operation.
