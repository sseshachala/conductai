# Live console login acceptance

This isolated Docker project exercises the real web/API with oauth2-proxy and
an external Keycloak realm. It does not change SaaS or runtime OIDC connections.
It is a test launcher, not a production deployment template. The API uses a
database-owner test role; restricted database-role acceptance remains separate.

Run `local.py --help` for inputs. Use a dedicated realm and confidential client,
PKCE S256, and exact callback `https://localhost:3443/oauth2/callback`. Configure
the client audience mapper and verified test email addresses. The client secret
is collected via `getpass`, not command arguments or an environment file.

`--check` fetches public discovery and validates Compose syntax only. A full run
builds images, prompts for the secret, migrates a fresh in-memory test database,
and provisions only the supplied admin/viewer subjects. The unmapped user must
remain unprovisioned. Do not use real business data or provider credentials.

Credentials reside in container environments, readable by Docker administrators.
Do not print `docker inspect` or expanded `docker compose config` output. No
Clerk/provider credentials are inherited. Only loopback HTTPS ports 3443/3444
are exposed; web, proxy, PostgreSQL, and Redis have no host ports. Test containers
and database contents are removed when Enter is pressed or the launcher exits
after startup. The generated Caddy CA remains in the dedicated volume.

## Trust local HTTPS explicitly

After ingress starts, export its **public certificate only**:

```sh
rtk docker cp conduct-console-e2e-ingress-1:/data/caddy/pki/authorities/local/root.crt /private/tmp/conduct-console-test-ca.crt
rtk proxy openssl x509 -in /private/tmp/conduct-console-test-ca.crt -noout -subject -fingerprint -sha256
```

Review and import this dedicated test root into the user login keychain using
Keychain Access; explicitly approve SSL trust. This is a trust-store change,
not something the launcher performs automatically. Never bypass TLS errors.
Remove the test CA trust after acceptance. CLI Python clients may require this
public CA via their documented CA-bundle configuration as well as OS trust.

## Acceptance record

- Login through Skycloak and return to `https://localhost:3443`.
- Admin and viewer see only their provisioned workspace and expected permissions.
- An unprovisioned user is denied despite successful IdP authentication.
- Verify disabled mappings, expired sessions, forged headers, CSRF, and renewal.
- Logout clears the proxy session; global Keycloak logout is a separate check.
- `conduct login` targets this local API and console, using an isolated CLI
  configuration rather than overwriting the normal CLI profile.
- Independently rerun Clerk regression tests.

Do not mark any of these passed based on `--check`, container startup, or a
successful metadata fetch. Hosted Skycloak testing is not air-gap acceptance.

## Isolated CLI login

The unreleased CLI changes add `login --web-url` and `--no-sync`. Run the CLI
from this worktree using its source path, not the globally installed release.
For this local test, use a separate empty HOME directory for the command so
existing SaaS credentials, update caches, and tool configuration remain intact.
Disable automatic updates to keep testing the checked-out source. Set
`SSL_CERT_FILE` to the exported public test CA; never disable TLS verification.

```sh
rtk proxy env HOME=/private/tmp/conduct-console-cli-home \
  CONDUCT_NO_AUTOUPDATE=1 SSL_CERT_FILE=/private/tmp/conduct-console-test-ca.crt \
  PYTHONPATH=<worktree>/packages/conduct-cli/src \
  <python-with-cli-dependencies> -m conduct_cli.main login \
  --server https://localhost:3444 --web-url https://localhost:3443 --no-sync
```

Use a fresh directory if that test HOME already contains unrelated credentials.
`--no-sync` prevents login from installing hooks or changing project/tool setup.
Default SaaS login is unchanged. A new custom server requires an explicit console
origin; subsequent login reuses the stored origin only for that API server.
The local CLI callback still uses a short-lived loopback HTTP listener, while
console and API connections use verified HTTPS. Do not share callback URLs,
configuration file contents, or bearer tokens in screenshots.

## Automated Keycloak Browser Canaries

Keep the existing disposable stack running, trust its CA in the browser, and run:

```sh
rtk proxy python3.11 tools/console-e2e/browser.py \
  --ca /private/tmp/conduct-console-test-ca.crt --allow-fixture-mutations
```

The runner prompts privately for admin, viewer, and unmapped passwords (or reads
`CONSOLE_E2E_{ADMIN,VIEWER,UNMAPPED}_{USERNAME,PASSWORD}` from injected process
environment). No credentials, screenshots, traces, or browser storage are saved.
Use the API virtualenv Python so the CLI callback test can import its dependencies.

Canaries cover admin workspace access and a foreign path, viewer mutation denial,
unmapped denial, forged headers, CSRF, session expiry/renewal, disabled mapping,
logout, OAuth token exchange/refresh/replay with actual MCP calls, and the actual
CLI loopback browser callback. The disable test touches only the known local
viewer mapping and restores it in `finally`. If the process is forcibly killed,
restore it with `python3 tools/console-e2e/mapping_control.py enable` before rerun.
The test database/container identity is checked before this mutation.

These are added tests, not recorded passes. Rebuild the web/API when testing
changed source; the existing running containers may still contain older code.
The suite uses the real Keycloak form, not mocked sessions. It requires compatible
username/password test accounts without additional required actions or MFA.
Full production tenant/Gateway profile coverage continues in the existing security
suite; this is console-auth parity, not a duplicate of all production fixtures.
