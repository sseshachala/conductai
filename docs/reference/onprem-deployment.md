## On-prem deployment

Run Conduct in your own environment. Use your identity provider, provider keys,
and model endpoints. SaaS continues to use Clerk.

### Install with Helm

The chart installs the console, API, Gateway, worker, OIDC login proxy,
PostgreSQL and Redis. You provide a Kubernetes cluster with an ingress controller,
persistent storage, TLS, and a Keycloak OIDC client.

1. Start with `deploy/helm/conduct/customer.example.yaml`.
2. Set your image repositories/tags, console/API/Gateway hostnames, and OIDC settings.
3. Create the Kubernetes Secrets listed below in the `conduct` namespace.
4. Set the initial workspace name, UUID, and administrator's Keycloak user ID.
5. Install:

```sh
helm upgrade --install conduct ./deploy/helm/conduct \
  --namespace conduct --create-namespace \
  --values customer-values.yaml --wait --timeout 10m
```

Open your console URL and sign in. The initial workspace and administrator are
created during startup. Other users need an explicit identity mapping and workspace membership.

### Configuration

| Value | What to provide |
| --- | --- |
| `image.api`, `image.web` | Your built Conduct image repositories and matching release tags |
| `image.pullSecrets` | Registry access Secret names, when required |
| `hosts.console`, `hosts.api`, `hosts.gateway` | Three distinct DNS hostnames |
| `ingress.className`, `ingress.tlsSecretName` | Your ingress class and TLS Secret covering all three hosts |
| `oidc.issuer`, `oidc.clientId`, `oidc.jwksUrl` | Your Keycloak realm and client settings |
| `oidc.caConfigMap` | Optional ConfigMap with your complete CA bundle in `ca.crt` |
| `bootstrap.workspaceId`, `bootstrap.workspaceName` | Initial workspace UUID and name |
| `bootstrap.adminSubject`, `bootstrap.adminName` | Administrator's Keycloak user ID and display name |
| `postgres.storage`, `redis.storage` | Storage size and optional storage class |
| `config.extraEnv` | Additional non-secret backend environment variables |
| `api.extraEnv`, `gateway.extraEnv`, `worker.extraEnv`, `web.extraEnv` | Per-service Kubernetes environment entries, including `valueFrom` Secret references |

Configure Keycloak with client authentication, Standard Flow, and PKCE S256.
Register the exact callback: `https://YOUR-CONSOLE-HOST/oauth2/callback`.
Use the client's Credentials tab to obtain its client secret.

### Secrets

Create `conduct-backend` and `conduct-login`, or set your own names in
`secrets.existingSecret` and `secrets.proxySecret`. Do not put secret values in Git.

| Secret | Required keys |
| --- | --- |
| `conduct-backend` | `DATABASE_URL`, `REDIS_URL`, `POSTGRES_PASSWORD`, `ENCRYPTION_KEY`, `CONSOLE_PROXY_SECRET` |
| `conduct-login` | `OAUTH2_PROXY_CLIENT_SECRET`, `OAUTH2_PROXY_COOKIE_SECRET` |

For release name `conduct`, the bundled data services are `conduct-postgres:5432`
and `conduct-redis:6379`. The default database and user are both `conduct`.
Use the same PostgreSQL password in `DATABASE_URL` and `POSTGRES_PASSWORD`,
URL-encoding it in the connection string. `REDIS_URL` is `redis://conduct-redis:6379`.
Use a random encryption key and proxy secret of at least 32 bytes, and a
base64-encoded 32-byte cookie secret for oauth2-proxy.

Add provider keys such as `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` to the backend
Secret when needed. Configure Gateway models and credentials in Conduct after login.
For an existing database or Redis service, set `postgres.enabled=false` or
`redis.enabled=false` and supply its URL in the backend Secret.

The chart uses proxy login. Do not include Clerk credentials in the backend Secret.
Keep TLS verification enabled. Configure your ingress to redirect HTTP to HTTPS.

### Check the install

```sh
kubectl -n conduct get pods
conduct login --server https://YOUR-API-HOST --web-url https://YOUR-CONSOLE-HOST
conduct projects
conduct guard sync --dry-run
```

After changing a Secret, restart the affected deployments. Preserve database
PVCs when uninstalling. The bundled PostgreSQL and Redis each use one replica.

### Try locally

The local Docker setup is also available:

```sh
rtk proxy python3.11 tools/console-e2e/local.py \
  --issuer https://YOUR-IDP/realms/YOUR-REALM \
  --admin-subject YOUR-ADMIN-USER-ID \
  --viewer-subject YOUR-VIEWER-USER-ID
```

It prompts for the client secret and serves the console at `https://localhost:3443`.
Register `https://localhost:3443/oauth2/callback` in Keycloak and trust the local
test CA. Keep the terminal open; pressing Enter removes the local test stack and data.

### Tests and feedback

The existing local Keycloak browser suite passed all 10 checks. The Helm chart
packages that setup; a customer-cluster install still needs to be tested.
Use `tools/onprem/acceptance.py` for delegation/revocation and outage checks.
Air-gap testing can be done in the target environment.

Report installation issues at [GitHub Issues](https://github.com/sseshachala/conductai/issues).
Include your chart/image versions and redacted error output. Do not include credentials.
