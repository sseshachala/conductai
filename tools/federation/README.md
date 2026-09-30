# Phase 2 verification harness

This harness uses real PostgreSQL, persisted encrypted synthetic credentials,
the production authentication/permission dependencies, and ASGI HTTP requests.
It runs outside `apps/api/tests`, whose shared conftest replaces permission
dependencies. There are no dependency overrides or external identity services.

Create a disposable loopback database (never reuse a development/production DB):

```sh
rtk docker run --rm -d --name conduct-federation-phase2 \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=conduct_federation_test \
  -p 127.0.0.1::5432 pgvector/pgvector:pg16
rtk proxy docker port conduct-federation-phase2 5432
```

From `apps/api`, set `DATABASE_URL` to
`postgresql://postgres@127.0.0.1:<reported-port>/conduct_federation_test` and run:

```sh
rtk proxy env PYTHONPATH=. python -m alembic upgrade head
rtk proxy env PYTHONPATH=. python ../../tools/federation/phase2_harness.py
rtk proxy env PYTHONPATH=. python -m alembic downgrade 0153
```

The final command must fail with the explicit data-preserving rollback message:
the harness has saved configuration, which downgrade must not silently discard.
Stop the disposable container when finished:

```sh
rtk docker stop conduct-federation-phase2
```

Covered: missing authentication, existing machine-token admin authorization,
developer denial, unconfigured and draft/disabled connections, tenant boundaries,
optimistic revisions, audit persistence, and database cross-tenant constraints.

Complementary tests in `apps/api/tests/test_federation_{verifier,network}.py`
exercise signed JWTs from two independent issuer fixtures, key rotation, expiry,
outage, token purpose, claim allowlists, concurrent cache isolation, and SSRF
transport controls. They inject JWKS/transport responses; they do not prove a
customer IdP or network/TLS deployment works.

Phase 3 must add live principal/delegation enforcement and configured/unconfigured
MCP/Gateway end-to-end tests. Passing this harness is not that acceptance test.

## Phase 3 MCP harness

On a fresh disposable `conduct_federation_test` database, migrate to head and run:

```sh
rtk proxy env PYTHONPATH=. FEDERATION_RESTRICTED_TEST=1 python ../../tools/federation/phase3_harness.py
```

Run from `apps/api` with `DATABASE_URL` set as above. The harness first reuses the
Phase 2 setup/authorization checks, then switches runtime connections to a
non-owner PostgreSQL role. It exercises real caller authentication, signed JWT
verification, delegated and unconfigured requests on both MCP endpoints, Guard
dispatch, revocation, outages, concurrent identity isolation and audit persistence.
Only JWKS document retrieval is injected; the IdP network/TLS deployment is not
tested. No external identity service or model provider is contacted. Omit
`FEDERATION_RESTRICTED_TEST=1` to separately test table-owner behavior.

The isolated database user must be able to create the restricted test role and
grant table privileges. CI provisions a dedicated database and runs this harness;
missing database prerequisites fail the job, rather than skipping the test.

## Console authentication foundation (#2297)

After migrating the disposable database above, run from `apps/api`:

```sh
rtk proxy env PYTHONPATH=. python ../../tools/federation/console_foundation_harness.py
```

This reuses the database safety gate and synthetic credential setup. It checks
real RSA-signed Clerk-compatible fixtures, existing workspace roles, cross-tenant
denial, machine credentials, SSE transport authorization, and missing-config
rejection. Only signing-key retrieval is substituted; authentication, database
membership and RBAC are not mocked. It does not test live Clerk, proxy login,
Keycloak sessions or HPE deployment. No production credentials are needed.

## Migration contention regression

Use a fresh disposable loopback database named `conduct_migration_test`, set
`DATABASE_URL`, and run from `apps/api`:

```sh
rtk proxy env PYTHONPATH=. python ../../tools/federation/migration_lock_harness.py
```

The harness migrates to 0153, holds a read transaction on `integrations`, proves
the original `ALTER TABLE ADD UNIQUE` times out, then runs two concurrent upgrade
processes. Both must complete while the reader remains open. It also verifies
empty rollback, prompt failure under write-lock contention, and successful retry.
Only this disposable database is modified; never use a production database.

The replacement index still takes a SHARE lock, so writes can briefly wait.
Migration 0154 bounds lock acquisition to three seconds and statement execution
to sixty seconds. API/Gateway migrations use one session-level advisory lock
before Alembic reads its revision, avoiding simultaneous schema changes.
