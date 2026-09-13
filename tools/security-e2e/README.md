# Local Authenticated Security E2E

This harness is separate from the dev-admin smoke suite. It is a local
precursor to staging, not proof of production security or ingress behavior.
The tests call the real API with real Clerk sessions; no permission factory
is overridden. By default the application runs as a non-owner PostgreSQL role
without RLS bypass. An explicit owner compatibility mode is also available.
Existing authorization defects may correctly make tests fail.

## Isolation

- Compose project: `conduct-e2e`, separate database volume and networks.
- Only ingress port `127.0.0.1:3100` is published. No database, Redis, API,
  or web backend ports are published to the host.
- PostgreSQL trusts only clients on its private Docker network. This
  passwordless fixture configuration must not be used for staging.
- Only an explicitly supplied credentials file is loaded by the runner; it is
  never copied into images. Clerk's automatic dotenv loading is disabled.
- No production Clerk keys are accepted. No LLM keys or worker are configured.
- The API encryption key is retained in the container environment, never
  printed or written to a host file by the harness. Managed `up` rebuilds
  reuse it. First setup requires `--initialize-local-key` or an injected
  `ENCRYPTION_KEY` of at least 32 bytes. Deleting the container loses the
  generated key; retain an externally managed key if container deletion is
  needed. Without a key, normal `up` refuses implicit regeneration.
- The harness-only `/api/__e2e/peer` endpoint reports IP attribution. It is
  not added to the production entry point.
- `/api/__e2e/database` reports only runtime role and RLS flags; tests verify
  the actual connection matches the requested mode before creating users.

## Prerequisites

Docker Desktop, Node dependencies installed from the root lockfile, Python
3.11, and the Playwright Chromium browser are required.

Use a separate Clerk development instance configured for email/password
signup, email-code verification, and Clerk Organizations. Allow `localhost:3100`.
Conduct stores workspace membership and enforces its own permissions. Its
invitation delivery integration also creates linked Clerk organizations.
The current signup selectors target this configuration, not social login,
MFA, or additional mandatory profile fields.

Supply these variables through your shell or secret-manager injection,
without putting values in Git or chat:

- `CLERK_SECRET_KEY`: test-instance backend key (`sk_test_`).
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`: same instance (`pk_test_`).
- `CLERK_FRONTEND_API`: corresponding development frontend hostname.
- `CLERK_AUDIENCE`: only if that instance issues an audience claim.
- `E2E_ALLOW_TEST_USERS=1`: explicit consent to create/delete synthetic users
  and test-owned organizations in that instance.

Clerk test emails use the `+clerk_test` pattern and test verification code.
The suite does not establish real email delivery. Browser setup uses Clerk's
testing token for bot-detection compatibility, not an authorization bypass.

## Commands

From the repository root, with credentials injected into the command's process:

```sh
rtk proxy python3.11 tools/security-e2e/local.py check
rtk proxy python3.11 tools/security-e2e/local.py infra
rtk proxy python3.11 tools/security-e2e/local.py up
rtk proxy python3.11 tools/security-e2e/local.py test
rtk proxy python3.11 tools/security-e2e/local.py status
rtk proxy python3.11 tools/security-e2e/local.py stop
```

`infra` needs no Clerk configuration and starts only PostgreSQL/Redis.
For the explicitly authorized, ignored local credentials file, use:

```sh
rtk proxy python3.11 tools/security-e2e/local.py up --credentials-file .local_secret --allow-test-users --initialize-local-key
rtk proxy python3.11 tools/security-e2e/local.py test --credentials-file .local_secret --allow-test-users
```

To continue functional testing with table-owner behavior, append
`--database-mode owner` to both `up` and `test`. This uses a separate local
non-superuser owner role, not PostgreSQL's superuser. RLS stays enabled but
is bypassed through ownership on tables without FORCE RLS. These results are
compatibility tests, not proof of database tenant isolation. Render's default
connection was verified to have this behavior; the production API's actual
database role has not yet been verified. Omitting the flag selects restricted
mode; run `up` again to switch the live stack before testing that mode.
Use `--grep '@baseline'` with `test` for the five positive lifecycle journeys.
Use `--grep '@security'` for the cross-tenant and removed-member refresh checks.
Use `--grep '@onboarding'` for first-login invitation acceptance, separately
from the existing-user invitation baseline. `--grep '@smoke'` runs ingress.

For the current owner-mode baseline:

```sh
rtk proxy python3.11 tools/security-e2e/local.py test --credentials-file .local_secret --allow-test-users --database-mode owner --grep '@baseline'
rtk proxy python3.11 tools/security-e2e/local.py test --credentials-file .local_secret --allow-test-users --database-mode owner --grep '@security'
```

## Bounded Production Journey

Production uses a separate runner and never accepts Clerk admin keys. Supply
two dedicated production accounts whose single owned workspaces are disposable:

```env
PROD_E2E_A_EMAIL=
PROD_E2E_A_PASSWORD=
PROD_E2E_B_EMAIL=
PROD_E2E_B_PASSWORD=
```

Run from the repository root:

```sh
rtk proxy python3.11 tools/security-e2e/production.py --authorize-gmail

rtk proxy python3.11 tools/security-e2e/production.py \
  --credentials-file ~/.conduct/e2e/production-accounts.env \
  --allow-disposable-workspaces
```

The first command is a one-time Gmail read-only authorization. It discovers the
single OAuth desktop-client JSON in `~/.conduct/e2e/otpbroker/` and writes the
refresh token to `~/.conduct/e2e/otpbroker/token.json`. Both the directory and
token are restricted to the current OS user. During a run, the launcher starts
a random-token broker bound only to `127.0.0.1`; it accepts only the two
configured test-account addresses and returns only a fresh, previously unused
six-digit code. Runs are headless by default; use `--headed` for visual
debugging or `--manual-otp` as an explicit OTP fallback.

The `production-security-canary` GitHub workflow runs this journey daily,
supports manual dispatch, and accepts a `production_deployed` repository
dispatch event. Store the account file, OAuth client JSON, and OAuth token JSON
as environment secrets named `PROD_E2E_ACCOUNTS_FILE`,
`PROD_E2E_GMAIL_CLIENT_JSON`, and `PROD_E2E_GMAIL_TOKEN_JSON` in the protected
`production-e2e` GitHub environment. The workflow materializes them with mode
`600` only for the job and removes them in an `always()` cleanup step. Do not
upload Playwright output from this workflow as an artifact.

An External OAuth app in Testing status issues refresh tokens that expire after
seven days for Gmail scopes. Before relying on the daily schedule, make this an
Internal app in the mailbox's Google Workspace organization, have the Workspace
administrator mark it trusted, or complete Google's production verification.

The production journey does not create or delete accounts or workspaces. It
checks owner issuance, MCP access, unrelated-tenant and unknown-workspace
denial, then temporarily adds account A to account B's workspace to verify
member issuance and post-removal refresh denial. Cleanup restores the original
membership set. Gmail authorization removes interactive second-factor entry
without persisting browser state or verification codes.

The runner loads only the four allowlisted fields, redacts them from output,
and requires explicit mutation consent. Traces, screenshots, videos, retries,
and saved authentication state are disabled. Keep the credential file ignored
and use only dedicated accounts and disposable workspaces.

Security checks are normal denial assertions, not expected failures or skips.
A green baseline alone does not make the whole suite green or authorize a
security release. The remaining validation gates are listed below.

`up` builds a production Next.js application and starts the actual API behind
Nginx. Open http://localhost:3100 after it starts. Missing credentials fail
preflight; they never silently select the dev-admin smoke tests.

Stopping preserves the fixture volume. No command here resets another database
or removes unrelated containers. Reset this project only after explicitly
confirming that its fixture data can be discarded.

## Coverage and Limits

The browser suite defines ten independent scenarios:

| Selection | Journey and assertions |
| --- | --- |
| `@baseline` signup | Real signup/email verification/Clerk organization onboarding; recover automatically from a stale workspace cookie and first-projects 401; trial session returns 200 before API helpers run; admin membership exists before token issuance and is unchanged afterward; MCP works. |
| `@baseline` returning-user login | Sign out and log in again through the actual form; existing workspace membership and role remain intact; token issuance and MCP access still work. |
| `@baseline` workspace creation | Create through the workspace menu; exactly one workspace with the requested name; creator is owner/admin before issuance; old workspace access remains usable. |
| `@baseline` workspace switching | Switch through the UI as developer in A and viewer in B; both authorized token exchanges work and neither role/membership set changes. |
| `@baseline` existing-user invitation | Pending invitation exists without membership; login accepts it; pending record disappears; exactly one developer membership exists before token issuance and is preserved afterward. |
| `@onboarding` first-login invitation | Join and select the invited organization through Clerk's UI; verify an active session, no pending task, the correct organization, and the same Conduct membership/token assertions. |
| `@security` outsider-token | Nonmember requests another workspace's OAuth token; require denial and unchanged target membership. |
| `@security` identity-path | Independent users/workspaces submit a conflicting authorized header and foreign path; reads and credential mutations must be denied; target membership and identities stay unchanged. |
| `@security` removed-member refresh | Refresh succeeds while a member; after removal, OAuth refresh, CLI refresh, and new token exchange are denied without restoring membership. |
| `@smoke` ingress | Forged-header checks through local Nginx and anonymous API rejection. |

Tests use fresh synthetic accounts and attempt Clerk cleanup after every test,
including failures. Positive and negative scenarios do not share memberships
or issued credentials. Token issuance/refresh now require existing membership,
and identity routes bind their path to the authorized workspace. The positive
baselines exercise legitimate provisioning with these checks enabled.
Membership assertions use the real persisted API views;
full database before/after checks for every credential mutation remain future work.
The dedicated local database retains fixture rows for inspection. A killed
runner can leave remote test users/organizations; reconcile only the printed
test-run prefix in the test instance. Traces, video, screenshots, and saved
authentication state are disabled to avoid credential artifacts.

The current application invitation sender in `apps/api/app/routers/projects.py`
uses a Clerk organization invitation as a best-effort delivery path.
The first-login test verifies acceptance through Clerk's organization chooser
and Conduct's persisted invitation acceptance. It does not verify delivered
email or navigation from the invitation email link.
Cleanup discovers linked organizations through synthetic user memberships and
deletes only organizations named with the current run's unique prefix.

Remaining gates, even after these tests pass:

- Review historical workspace memberships and revoke affected credentials
  before rollout. These fixes do not identify or delete memberships that may
  already have been created through the former unauthorized token exchange.
- Remaining lifecycle negatives: deleted workspaces, old access tokens,
  refresh replay/concurrency, provisioning races, and broader revocation.
- Actual delivered invitation/email links, social login, MFA, and session expiry.
- Full CLI device/PKCE authorization UX, refresh/revocation, and direct-backend
  adversarial IP tests (not merely the trusted local proxy path).
- Database before/after assertions for every denied mutation.
- Sandbox failure and pending-approval execution tests from issue #1850.
- Real staging TLS, DNS, proxy CIDRs, deployment credentials, network access
  controls, and production-like email delivery. Local Nginx does not validate
  a future cloud load balancer.

Source references: [Clerk signup testing](https://clerk.com/docs/guides/development/testing/playwright/test-sign-up-flows),
[Uvicorn proxy settings](https://www.uvicorn.org/settings/),
[Playwright authentication-state safety](https://playwright.dev/docs/auth).
