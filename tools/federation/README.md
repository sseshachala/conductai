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
