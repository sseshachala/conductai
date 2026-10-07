# Conduct Helm install

Installs web, API, Gateway, worker, oauth2-proxy, PostgreSQL and Redis.
Supply your images, DNS/TLS, Keycloak settings and Kubernetes Secrets.

1. Use `customer.example.yaml` as your values file.
2. Create the backend and login Secrets described in the [installation guide](../../../docs/reference/onprem-deployment.md#secrets).
3. Install:

```sh
helm upgrade --install conduct ./deploy/helm/conduct \
  --namespace conduct --create-namespace \
  --values customer-values.yaml --wait --timeout 10m
```

Open your console hostname and sign in as the configured administrator.
The chart creates the initial workspace and admin mapping during startup.

Requires an ingress controller, a storage class, and a TLS Secret covering the
three hostnames. Use HTTPS redirects at ingress. Network policies require a
supporting CNI. Set `postgres.enabled=false` / `redis.enabled=false` to use your
own data services. Keep provider credentials in Kubernetes Secrets or Conduct's vault.

Projection processing ships safe-off through `config.extraEnv`. Rollout order:
migrate -> worker deployed -> dry-run -> queue enable -> cleanup enable. Keep
`GUARD_PROJECTION_RETENTION_DRY_RUN=true` until retention metrics and aggregate
logs match the expected volume. The retention daemon is independent of workflow
and projection consumer concurrency.

Audit archives use S3-compatible storage on SaaS and on-prem. Cleanup defaults
off. Supply the bucket, compliance period, and separate signing/encryption keys;
use `GUARD_AUDIT_ARCHIVE_ENDPOINT` for private storage. See the
[retention guide](../../../docs/reference/audit-retention.md) for settings and checks.

Check `values.yaml` for configuration. The chart uses the same components as the
local test stack; customer-cluster installation has been verified.
File problems at https://github.com/sseshachala/conductai/issues with redacted logs.
