# Okta Trust Storage

Okta remains supported. Service credentials and identity trust have separate jobs:

| Table | Stores |
| --- | --- |
| `integrations` | Encrypted Okta API credentials, tool handle, sync metadata |
| `federation_connections` | Issuer, audience, JWKS location, token profile, status, revision |

Connections have an `authentication_mode`:
- `okta_agent` authenticates an existing Okta-synced agent by its subject.
- `delegated` requires the existing caller binding, approved principal, and grant.

Both modes can belong to the same integration. Delegation APIs and runtime
resolvers only accept `delegated` connections. Console SSO configuration is unchanged.

## Migration 0158

The migration copies existing Okta settings into `okta_agent` connections.
Disabled settings remain disabled. Incomplete enabled settings are marked
`needs_review` and cannot authenticate. No identities, memberships, or grants
are created. Existing delegated connections keep their configuration and revision.

The three `integrations.okta_*` columns remain temporarily for rolling deployments.
A transactional database trigger mirrors writes from both old and new API instances
into the trust table. Repeated writes of identical settings do not bump the revision.
The issuer index remains a candidate directory; authentication checks the trust
record under workspace RLS. It never authorizes from the compatibility columns.

Consumers updated: Okta config GET/PUT/DELETE, JWT agent resolver, delegated
connection listing/editing, bindings, grants, runtime rechecks, and workflow identity.
Okta application sync, agent lifecycle checks, audit events, and the RS256/JWKS
verifier remain in place. A token matching multiple workspace identities is denied.

An application rollback can use the retained columns. Schema downgrade refuses
to delete populated Okta trust records. Removing the compatibility columns and
their candidate-directory dependency is a separate migration.

## Tests

`tools/federation/okta_trust_harness.py` tests backfill, compatibility writes,
restricted-role RLS, signed JWT authentication, disable, and rollback on a fresh
local `conduct_federation_test` database. CI runs it before the existing delegated
OIDC and console-auth harnesses. JWT unit tests cover invalid claims, signature,
expiry, key rotation, and JWKS failure.
