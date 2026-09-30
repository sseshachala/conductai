# On-prem console authentication (#2297)

## Delivery status

The foundation adds explicit API authentication mode selection, startup validation,
normalized console identity, and shared HTTP/SSE authorization. PR2 adds the
Keycloak proxy identity exchange, explicit account provisioning, short-lived
console sessions, a provider-neutral web adapter, and runtime web configuration.
Signed-fixture and real-database verification do not establish live browser SSO
or air-gap readiness. No production configuration is changed by this branch.
See [proxy deployment](onprem-console-proxy.md) for configuration and acceptance gaps.

## Deployment modes

`AUTH_MODE` is a startup deployment setting, not a workspace setting or feature flag.

| Mode | Current behavior |
| --- | --- |
| `clerk` (default) | Existing Clerk browser authentication and Conduct machine credentials. API startup requires `CLERK_SECRET_KEY` and `CLERK_FRONTEND_API`. Missing keys never grant access. |
| `development` | Explicit unauthenticated local access, only when `ENVIRONMENT` is exactly `local` or `development`. Supplied bearer credentials still undergo verification. |
| `proxy` | Dedicated Keycloak ID-token handoff through oauth2-proxy; explicit local identity mapping and existing Conduct memberships. Requires deployment trust and a server-only exchange secret. Live browser acceptance remains pending. |

Unknown modes are rejected. A worker importing shared settings validates mode and
environment but does not require Clerk browser credentials. API/Gateway HTTP
startup validates the complete selected authentication configuration before cache
warming, background tasks, or request handling.

The current optional `CLERK_AUDIENCE` setting retains its existing behavior. This
slice does not require a new audience claim from existing Clerk sessions. The
future proxy contract requires an explicitly configured issuer and audience.

### Environment ownership

| Surface | Foundation behavior | Later proxy delivery |
| --- | --- | --- |
| Render API/Gateway | Default `AUTH_MODE=clerk`; retain Clerk keys and all service settings. Check keys before deploying the startup validation. | Verify configured console evidence; preserve machine bearer authentication. |
| Render worker | Retain existing worker settings. No new Clerk secret is required. | Preserve verified principal context and recheck grants at execution. |
| Vercel web | Existing SaaS Clerk mode remains the default. | PR2 adds provider-neutral hooks and allowlisted runtime configuration. |
| Docker/Helm | Keep current service URLs, database/Redis, encryption and secret references. | Add proxy settings, customer issuer/client, exact callback URLs and private CA trust. |

For isolated development without Clerk, explicitly set both
`AUTH_MODE=development` and `ENVIRONMENT=development`. Never use this configuration
on an exposed installation. Existing production deployments must set
`ENVIRONMENT=production`; leaving the environment at its local default is not a
production configuration. Do not remove existing production Clerk variables.

## Console identity contract

`ConsoleIdentity` contains provider, issuer, subject, local user ID and optional
organization ID. It is immutable and constructed only after verification.
Clerk retains its existing local user IDs. A token's organization hint does not
replace a Conduct workspace-membership check.

For proxy identities, resolve `(issuer, subject)` to an explicit local identity
mapping. Reuse existing Conduct user/membership/RBAC stores; do not create a
parallel authorization system or link accounts by email. Inventory the remaining
`clerk_user_id` storage and integrations before implementing the mapping. The
existing runtime `FederationPrincipal` represents delegation approval and is not
automatically a console account or workspace membership.

## Proxy-to-application contract

- Use an established OIDC proxy for authorization-code login and browser sessions.
- Accept only verifiable, issuer/audience-bound identity evidence at the backend.
  PR2 accepts RS256 Keycloak ID tokens with the dedicated client audience and
  authorized-party claim, and the Keycloak `typ=ID` payload marker. ID tokens
  and delegated API access tokens remain distinct; do not reuse the runtime
  federation endpoint as a general console-session validator.
- Strip browser-supplied identity headers. Bare `X-Auth-User`/email headers cannot
  create a session or authority. A network allowlist alone is insufficient proof
  of the acting user; protect upstream services and verify evidence independently.
- Restrict issuer/JWKS access to deployment-admin-approved endpoints. Support
  internal DNS and private CAs without disabling TLS or loosening multi-tenant
  federation SSRF controls. Bound JWKS caching and test rotation/outage behavior.
- Keep machine authentication routes separate from browser redirects. Existing
  Conduct API/agent/run tokens, MCP OAuth and delegated identity retain their
  current contracts; no cookie/redirect fallback for failed machine credentials.
- Use same-origin authenticated browser API requests. Define secure HttpOnly
  cookies, CSRF defenses, exact redirect allowlists, expiry, logout and downstream
  session invalidation. Do not forward evidence or cookies to model providers.

## Bootstrap and provisioning

Bootstrap cannot depend on a connection created after console login. Deployment
configuration supplies the trust and one explicit administrator issuer/subject
mapping. Provision the local user and chosen workspace membership through an
idempotent privileged bootstrap command, with an audit entry. Do not grant admin
to the first browser login, use email matching, or accept token-provided workspace
roles as Conduct authorization. Additional users require explicit provisioning or
approved invitations. Group-based provisioning is deferred until its mapping and
revocation rules are specified and tested.

## Web/runtime configuration contract

The web server owns the deployment mode and returns only an allowlisted public
mode and routing configuration; it must agree with the API. Reuse existing
`APP_URL`, `API_BASE_URL`, `API_URL` and browser API routing settings instead of
adding a competing URL configuration. Keep public URLs separate from internal
service addresses. Never expose client secrets, cookie secrets, provider keys or
backend credentials. Mode is fixed at startup, not request-controlled.

Relevant auth and browser API settings now come from an allowlisted runtime
document emitted by the web server. Proxy browser API requests use a same-origin
server proxy, which exchanges identity evidence and forwards only the minted
Conduct credential and selected headers. No Keycloak ID token is returned to
browser JavaScript. Two deployed URLs using the same built image remain an
acceptance gate. Legacy web-only MCP OAuth routes are not enabled in proxy mode;
use the API OAuth discovery, consent and token endpoints instead.

## Verification and remaining gates

Foundation tests cover invalid configuration, explicit local mode, no implicit
user/admin/workspace fallback, service-token compatibility, scoped workspaces,
SSE authentication and forged-header rejection. These are local tests, not proof
of proxy login. No auth dependency may bypass checks solely because Clerk keys
are absent.

Before completing #2297, run actual Keycloak + proxy + Conduct + PostgreSQL with
two users and different roles. Verify login/logout/expiry, CSRF, forged evidence,
direct upstream requests, tenant isolation, private CA trust, rotation and
Clerk/machine-client regression. Test two deployment URLs with the same images.
Record Docker/kind results separately from HPE PCAI customer installation and
air-gap validation. Hosted Skycloak delegation tests do not satisfy console SSO
acceptance or disconnected-network acceptance.
