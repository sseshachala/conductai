# Keycloak console login (PR2)

## Status and boundaries

Implementation and signed-fixture tests are available. On September 30, 2026,
all 10 local browser canaries passed using hosted Keycloak and oauth2-proxy.
Disconnected-network and customer deployment acceptance remain pending. See the
[installation guide](../reference/onprem-deployment.md) for scope and the three
additional acceptance stages. Do not describe this as verified air-gap support.

SaaS keeps `AUTH_MODE=clerk`. On-prem selects `AUTH_MODE=proxy` on both API and
web. Keycloak owns accounts, passwords, MFA, and any user self-registration.
Conduct owns explicit identity mappings, workspace membership, and permissions.
An authenticated but unprovisioned Keycloak user gets no Conduct access.

Workspace OIDC connections remain separate: those govern delegated runtime
requests, not console login. No runtime connection or grant is created by login.
The current console evidence profile is Keycloak-specific; other OIDC providers
need an explicitly reviewed ID-token profile, not a relaxed verification fallback.

## Request path

1. Browser reaches oauth2-proxy over HTTPS and completes Keycloak authorization
   code login with PKCE. The proxy validates state, nonce and its browser session.
2. The proxy replaces upstream Authorization with the signed Keycloak ID token.
3. Next.js exchanges that token at `/auth/console/session`, using a separate
   server-only shared secret. The API independently checks signature, issuer,
   client audience, authorized party, lifetime and token purpose.
4. `(issuer, subject)` must match an active `console_identity_mappings` row.
   Conduct issues a credential valid for at most 60 seconds, bounded by the
   original ID token expiry. The browser never receives the Keycloak ID token.
5. Browser API calls use `/api/backend/*`. The server performs the exchange,
   forwards the Conduct credential, and checks Origin on mutations. The API
   checks the active mapping and its existing workspace/RBAC records.

Machine clients continue using the API/Gateway origin and their existing bearer
credentials. Do not place machine endpoints behind browser-login redirects.

## Deployment configuration

Supply secrets using your deployment secret store. No real values belong in git.

| Service | Variable | Meaning |
| --- | --- | --- |
| API and web | `AUTH_MODE` | `proxy` |
| API and web | `CONSOLE_PROXY_SECRET` | Same random secret, at least 32 bytes; only the API and web know it |
| API | `CONSOLE_OIDC_ISSUER` | Exact Keycloak realm issuer, HTTPS |
| API | `CONSOLE_OIDC_CLIENT_ID` | Dedicated console client; not the delegated runtime client |
| API | `CONSOLE_OIDC_JWKS_URL` | Administrator-approved HTTPS signing-key endpoint |
| API | `CONSOLE_OIDC_CA_FILE` | Optional private CA bundle; TLS verification stays enabled |
| API | `CONDUCT_WEB_URL` | Public HTTPS console origin for CLI/MCP consent |
| API | `CONDUCT_OAUTH_ISSUER` | Public HTTPS API origin for Conduct OAuth discovery |
| Web | `APP_URL` | Public HTTPS console origin; authoritative for CSRF checks |
| Web | `API_URL` | Internal API origin, with no path or credentials |
| Web | `API_BASE_URL` | Public API origin displayed in generated webhook URLs |
| Web | `NODE_EXTRA_CA_CERTS` | Node trust bundle if the internal API uses a private CA |

Remove Clerk credentials from proxy deployments; the API rejects mixed console
configuration. Workers validate the mode but do not need browser credentials.
Keep existing database, encryption, worker, Gateway and service configuration.
Do not switch existing Vercel/Render SaaS services to proxy mode.

The web serializes only mode, browser/public API routing and the Clerk public key
(Clerk mode only). Internal URLs, client secrets and exchange secrets are absent.

## Proxy requirements

Use the official [oauth2-proxy Keycloak OIDC configuration](https://oauth2-proxy.github.io/oauth2-proxy/configuration/providers/keycloak_oidc/)
and [option reference](https://oauth2-proxy.github.io/oauth2-proxy/configuration/overview/).
The integration contract requires:

- Dedicated confidential client, exact HTTPS `/oauth2/callback` redirect URI,
  authorization code flow and `code_challenge_method = "S256"`.
- `provider = "keycloak-oidc"` and the configured realm issuer/client credentials.
- `pass_authorization_header = true`, `skip_auth_strip_headers = true`,
  `pass_access_token = false`, `skip_jwt_bearer_tokens = false`.
- Secure, HttpOnly, SameSite=Lax host-only cookies and a dedicated random cookie
  secret. Configure session refresh so unexpired ID-token evidence is forwarded.
- API routes return 401 instead of redirecting fetch requests to the IdP.
  Exempt only `/signed-out` from browser authentication for the logout landing page.
- Strip incoming identity and exchange-secret headers at ingress. Never expose
  the web upstream directly; the API exchange additionally requires signed
  evidence and the server secret. The proxy never learns that exchange secret.
- Never configure broad redirect allowlists, skip issuer/audience verification,
  disable TLS verification, or grant Conduct roles from IdP claims.

Console sign-out clears the oauth2-proxy session. It does not promise global
Keycloak logout; configure and test IdP session termination separately. Already
issued Conduct console credentials can remain valid for at most 60 seconds.
Disabling the local identity mapping invalidates them on their next API request.
Existing CLI/API credentials retain their independent lifecycle and revocation.

## Explicit provisioning

Migrate to `0157` first. An administrator with deployment database access can map
a Keycloak subject to an existing Conduct workspace:

```sh
rtk proxy python -m app.modules.auth.console.bootstrap \
  --subject '<Keycloak user ID>' --workspace-id '<existing workspace UUID>' \
  --role admin --name 'Console administrator'
```

Use `viewer` or another existing Conduct role for subsequent users. The command
is idempotent for an unchanged subject/workspace/role, records an audit event,
does not link by email, and does not reactivate disabled identities or silently
change existing roles. Initial workspace creation remains a separate deployment
provisioning step; first browser login never creates an administrator.

Existing membership management can add already-provisioned local IDs. Email
invitations and automatic email-based invite acceptance are not enabled for proxy
users. The existing `clerk_user_id` storage column carries the opaque local ID;
it is not evidence that Clerk authenticated the user.

The migration refuses downgrade while mappings exist to prevent accidental
identity loss. Switching modes does not merge Clerk and Keycloak accounts.

## Verification

Run `tests/core/test_console_proxy.py`, the existing console/OAuth/machine auth
tests, and the web `src/lib/auth/*.test.*` tests. For real PostgreSQL checks, use
the disposable database procedure in `tools/federation/README.md`, then run:

```sh
rtk proxy env PYTHONPATH=. python ../../tools/federation/console_proxy_harness.py
```

The harness verifies signed identity exchange, explicit provisioning,
admin/viewer permissions, tenant isolation, disabled mappings, and machine-token
compatibility without bypassing the real API dependencies. JWKS transport alone
is injected. This is not a live login test.

Before production acceptance: run actual browser login/logout through Keycloak
and oauth2-proxy; test renewal, expiry, unprovisioned users, proxy/header spoofing,
CSRF, private CA validation, rotation/outages, CLI/MCP consent, and two customer
URL configurations from the same image. Test disconnected operation separately.
