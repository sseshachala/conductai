## On-prem deployment

For on-premises and private-cloud installations, Conduct uses
customer-controlled Keycloak for console login and existing Conduct permissions
for authorization. SaaS continues to use Clerk. Workspace OIDC delegation is a
separate trust relationship; console login never creates delegation grants.

### Release status

The September 30, 2026 verification recorded 33 passing SaaS canaries and 10
passing local console canaries using hosted Keycloak. This is compatibility
evidence, not deployment certification or air-gap acceptance. The current Docker console
launcher is a disposable evaluation environment, not a production installer.
The existing Helm chart needs proxy/runtime-auth packaging updates before it can
be used as a turnkey Keycloak installation. Do not deploy it unchanged expecting
the tested console topology.

### Choose a deployment path

| Path | Intended use | Required acceptance |
| --- | --- | --- |
| Docker evaluation | Validate identity and CLI integration with test users | Console browser and MCP checks |
| Private cloud | Operator-managed TLS, registry, secrets, data services and ingress | Customer-specific deployment, backup/restore and security acceptance |
| Disconnected installation | All runtime dependencies and model serving inside the boundary | Cold start without internet, all functional checks and network evidence |

### Prerequisites

- A reviewed Conduct revision and matching API, web, Gateway, worker and CLI artifacts.
- HTTPS console, API/Gateway and Keycloak hostnames resolvable by both containers and clients.
- Trusted certificate chains; never disable TLS verification. Use customer CA bundles where needed.
- PostgreSQL with pgvector, Redis, persistent storage, backups and a tested restore process.
- A secret manager for database credentials, encryption key, proxy exchange secret,
  OIDC client secret, cookie secret and optional provider credentials.
- A confidential Keycloak client, three test users and explicit Conduct memberships.
- A reachable model endpoint for inference acceptance. A cloud provider is optional;
  disconnected installations need an internal endpoint and locally available weights.

Do not paste credentials into commands, Helm values committed to source control,
screenshots or support tickets. Inject them through the deployment secret store.
RTK prefixes below are repository tooling; RTK is not a Conduct server dependency.

### Docker evaluation

Use a dedicated Keycloak realm and client named `conduct-console-proxy`:

1. Enable client authentication and Standard Flow. Require PKCE S256.
2. Disable Authorization Services, implicit flow, direct access grants and service accounts unless separately required.
3. Register exactly `https://localhost:3443/oauth2/callback`; do not use wildcard redirects.
4. Configure the client audience and verified email claims required by the Keycloak OIDC proxy.
5. Create `console-admin`, `console-viewer` and `console-unmapped`, with usable passwords and no unfinished first-login actions.
6. Record their immutable Keycloak subject IDs. Provision admin/viewer only; leave unmapped without Conduct access.

From a checkout with Docker, Python 3.11, API dependencies, web dependencies and
Playwright Chromium installed, run:

```sh
rtk proxy python3.11 tools/console-e2e/local.py \
  --issuer https://idp.example.internal/realms/conduct-console-test \
  --admin-subject '<admin-Keycloak-user-ID>' \
  --viewer-subject '<viewer-Keycloak-user-ID>'
```

The launcher privately prompts for the client secret. It builds isolated images,
migrates a disposable database and creates only the explicit test mappings. Leave
its terminal open. Pressing Enter removes the test containers and database.
Never put customer data in this stack. An existing stack causes startup refusal;
do not start a second launcher over it.

Export the public test CA and inspect its fingerprint:

```sh
rtk docker cp conduct-console-e2e-ingress-1:/data/caddy/pki/authorities/local/root.crt /tmp/conduct-console-test-ca.crt
rtk proxy openssl x509 -in /tmp/conduct-console-test-ca.crt -noout -subject -fingerprint -sha256
```

Explicitly trust that dedicated CA in the test browser/OS. Run the browser suite
from a second terminal, using a Python interpreter with the API/CLI dependencies:

```sh
rtk proxy python3.11 tools/console-e2e/browser.py \
  --ca /tmp/conduct-console-test-ca.crt --allow-fixture-mutations
```

Passwords are entered privately. The suite temporarily disables the viewer
mapping and restores it. It covers login, roles, unknown users, spoofed headers,
CSRF, expiry/renewal, disabled mappings, logout, OAuth refresh replay and CLI/MCP.
Its current fixture targets localhost:3443/3444; it is not a generic production
browser tester. A private-CA Keycloak issuer also requires that CA to be trusted
by the launcher, API and oauth2-proxy; the exported localhost CA alone is not enough.

### Production configuration

Use the same authentication topology, with durable services and customer URLs:
browser -> TLS ingress -> oauth2-proxy -> web -> API. Machine clients use the
API/Gateway HTTPS endpoint directly, without browser redirects. Keep upstream web,
proxy, PostgreSQL and Redis ports private. Strip caller-supplied identity and
proxy-secret headers at ingress.

| Service | Required configuration |
| --- | --- |
| API and Gateway | `AUTH_MODE=proxy`, `ENVIRONMENT=production`, `DATABASE_URL`, `REDIS_URL`, `ENCRYPTION_KEY`, `CONSOLE_PROXY_SECRET`, `CONSOLE_OIDC_ISSUER`, `CONSOLE_OIDC_CLIENT_ID`, `CONSOLE_OIDC_JWKS_URL` |
| API and Gateway URLs | `APP_URL`, `API_BASE_URL`, `CONDUCT_WEB_URL`, `CONDUCT_OAUTH_ISSUER`, `CONDUCT_PROXY_URL`, `ALLOWED_ORIGINS`, all pointing to this installation |
| Web | `AUTH_MODE=proxy`, public `APP_URL` and `API_BASE_URL`, private `API_URL`, matching `CONSOLE_PROXY_SECRET` |
| oauth2-proxy | Keycloak issuer/client/secret, dedicated cookie secret, exact public callback, secure cookies, PKCE, verified TLS and ID-token forwarding |
| Worker | Production mode, database, Redis, encryption and deployment URLs; no console client secret or Clerk keys required |
| CLI | Explicit `--server` and `--web-url`; trusted CA bundle; stored Gateway/MCP endpoints checked after login |

Remove Clerk credentials from proxy deployments. API and Gateway both validate
authentication at startup. Never select development mode to bypass a startup
failure. Keep signing algorithm RS256 separate from PKCE S256.

Run migrations with a backup and reviewed rollout procedure. Provision an existing
workspace through the deployment's approved bootstrap process before mapping users:

```sh
rtk proxy python -m app.modules.auth.console.bootstrap \
  --subject '<Keycloak-user-ID>' --workspace-id '<existing-workspace-UUID>' \
  --role admin --name 'Console administrator'
```

Repeat with `--role viewer` for the viewer. This command does not create the initial
workspace; that remains an assisted provisioning step. It does not link by email,
reactivate disabled identities or silently change existing roles.

Configure CLI login against your URLs, initially without installing local hooks:

```sh
rtk proxy conduct login --server https://api.example.internal \
  --web-url https://conduct.example.internal --no-sync
rtk proxy conduct projects
rtk proxy conduct guard sync --dry-run
```

Use `SSL_CERT_FILE` for Python CLI trust if needed. Check generated endpoints before
running a real sync. Console logout, CLI-token revocation and delegation-grant
revocation are distinct operations.

### Kubernetes packaging

The chart lives in `deploy/helm/conduct`. Before a customer deployment,
complete the chart's proxy-auth packaging checklist and validate against the target
Kubernetes distribution and version. Required operator inputs include the ingress gateway, customer DNS,
TLS termination, storage classes, secret references and private-registry paths.
Do not assume a universal hostname, service account, storage class or resource size.

The packaging gate includes oauth2-proxy, runtime web settings, private CA mounts,
header sanitization, separate machine ingress, explicit bootstrap, offline image
references and backup/restore. The current chart's embedded database services are
single replica, not an HA promise. Image tags, chart version and CLI version must
be pinned together and tested before publishing a customer installation bundle.

Keycloak documents [production container deployment](https://www.keycloak.org/server/containers);
use the official [oauth2-proxy Keycloak configuration](https://github.com/oauth2-proxy/oauth2-proxy/blob/master/docs/docs/configuration/providers/keycloak_oidc.md).

### Three-stage acceptance

Use `tools/onprem/acceptance.py` to run the existing tools and produce a sanitized
JSON evidence index. The non-secret plan is based on
`tools/onprem/acceptance.example.json`. CLI configuration and credentials remain
outside the plan; only their local file paths are referenced. Supply actual
endpoints/model aliases and a harmless dedicated blocking-rule marker.

```sh
rtk proxy python3.11 tools/onprem/acceptance.py --plan /path/to/acceptance.json --check
rtk proxy python3.11 tools/onprem/acceptance.py --plan /path/to/acceptance.json \
  --stage delegation --allow-disposable-tests --report /path/to/delegation-report.json
```

The runner fails on incomplete configuration; skipped transports are not a full
acceptance pass. Tests are interactive and may incur inference cost. Never run
outage tests against shared production services. The report is an evidence index,
not an independent certification or a replacement for audit/network records.
Run `--stage console` and `--stage outages` with separate report paths for the other
connected checks. For the complete disconnected run, use `--stage all` plus
`--airgap-evidence /path/to/reviewed-evidence.json`, based on
`tools/onprem/airgap-evidence.example.json`. Its defaults deliberately fail validation;
an operator must verify every assertion before setting it true. Keep underlying
network/audit evidence separately; the report records the attestation file's digest.

#### Live delegation and revocation

Create a separate runtime OIDC client/connection and explicit principals, caller
binding and a disposable grant. Keep this separate from console login. Configure
one allowed and one denied user. The live runner verifies both, pauses for an
operator to revoke the allowed user's grant, then retries the same unexpired token.
Confirm denial and audit attribution. Restore only the dedicated test grant after
the run. Repeat against the local installation; SaaS results do not transfer to it.

#### Controlled outages

Start with successful inference through dedicated Gateway and LiteLLM services.
The smoke runner pauses while an operator makes only their policy dependency
unavailable. The ingress and inference process must stay reachable: stopping the
whole service proves availability loss, not fail-closed policy enforcement.
Require a dependency-specific denial, no downstream model invocation in provider
logs, then successful recovery after the dependency is restored.

Separately exercise IdP/JWKS outage and key rotation: warm-cache valid keys may be
usable within the configured cache policy; unknown keys, invalid signatures and
expired evidence must never be accepted because discovery is unavailable. Record
cold-cache denial, bounded timeouts and recovery. The inference fault runner does
not automatically test these identity-service scenarios.

#### Air-gap acceptance

Use self-hosted Keycloak, internal DNS/time/certificates, internal registry and
local model serving. Hosted Skycloak and public provider APIs cannot satisfy this gate.
Preload application/base/proxy/IdP/database images, Python wheels, npm dependencies,
CLI artifacts, browser binaries and model weights in a connected preparation phase.
Build and scan artifacts before entering the disconnected network.

Block internet egress for every service and the test browser/CLI host. Retain only
the approved internal DNS, time, identity, database and inference dependencies.
Cold-start the installation without pulling images or downloading packages, then
rerun console, delegation and inference/outage checks. Record image digests,
firewall/CNI policy, DNS/egress logs, IdP/JWKS tests, provider request counters and
recovery evidence. Failed internet probes alone do not prove isolation.

Run the air-gap stage only inside this prepared environment. It reruns functional
checks and records operator attestations separately; it does not install a firewall
or certify a deployment. Customer-domain browser acceptance must be recorded separately from
the localhost fixture. No external email, telemetry, fonts, plugins, update checks,
registry access or model downloads may be required for the accepted workflows.

### Operations and handoff

Retain the tested revision, image digests, configuration schema, role mappings,
acceptance report and redacted logs. Document backup/restore, encryption-key recovery,
certificate/client-secret rotation, audit retention and upgrades. Do not delete
PVCs during a normal uninstall/rollback. Validate two customer URL configurations
using the same web image before declaring the runtime-config packaging complete.

Try Guard needs an operator-supplied provider key for its current funded-demo path;
a self-hosted model does not automatically replace that provider-specific flow.
For an air gap, use the regular local inference acceptance path unless a supported
local Try Guard adapter is delivered and tested. This is a tracked product gap,
not a reason to embed a shared cloud key in the installation.
