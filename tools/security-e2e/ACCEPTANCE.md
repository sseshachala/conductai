# Shared Local and SaaS Acceptance

Reuse the existing suites. Do not replace the production canaries with the
smaller transport smoke script, or interpret skipped tests as acceptance passes.

| Area | Existing coverage reused | Remaining live validation |
| --- | --- | --- |
| Clerk account/workspace lifecycle | Local journeys; production account preflight | Proxy/Keycloak requires separate preprovisioned identities, not Clerk signup |
| Tenant isolation and permissions | Local security journeys; production boundary canaries | Run equivalent scenarios against proxy/Keycloak |
| Refresh, replay, membership revocation | Existing local and production canaries | Repeat with real Keycloak-issued console identity and CLI session |
| MCP | Shared Playwright initialize/list/invoke helper used by both suites; shared Python allow/block probes | Real delegated caller and revoked-grant checks |
| Gateway | Existing production fixture preflight, auth, models, streaming, inference, and audit canaries | Equivalent local published profiles and provider fixtures |
| LiteLLM | Shared opt-in transport inference and configured blocking-rule probe | Real Skycloak adapter; prove no provider call on block |
| Audit | Existing production tenant-scoped audit and Flight Recorder tests | Delegated actor/caller/grant attribution on both deployments |
| Fault handling | Requires dedicated fault-test services | Unreachable backend fail-closed, disabled identity, browser expiry/logout |
| Air-gap | Not established by hosted Skycloak tests | Self-hosted IdP and outbound-network-blocked local acceptance |

## Added Live Checks

- Keycloak console browser canaries: `tools/console-e2e/browser.py`; see its README
  for private credential prompts and bounded local mapping mutation consent.
- Live delegation: append `--delegation-config PATH --manual-browser` to either
  shared transport invocation. This reuses the working PKCE IdP test in
  `tools/federation/live.py`; it prompts for a separate service `cond_api_*` key.
- Same-token grant revocation: append `--test-revocation`. After both identity
  paths pass, revoke only the disposable positive user's grant when prompted.
  The same still-unexpired token must receive `federation_grant_invalid`; expired
  tokens and generic authentication failures cannot pass this check. Restore the
  dedicated grant before another positive-path run.
- Controlled fail-closed/recovery: append `--inference --fault-tests` with each
  endpoint/model configured. For Gateway supply `--gateway-fault-marker` matching
  the intended policy/dependency error; LiteLLM defaults to `fail_closed`.
  The runner requires a successful inference baseline and explicit `TEST` consent,
  pauses while the operator disables ONLY the dedicated test service's policy
  dependency, checks a structured rejection, then prompts restoration and checks
  successful recovery. Never stop the production API for this test. A timeout,
  generic provider failure, or invalid credential is not a passing fail-closed test.

These stages are available to both runners and remain opt-in. They are not marked
passed merely because source exists. Provider-log correlation, live LiteLLM
delegated-user adapter verification, and fully offline acceptance remain distinct
evidence requirements. The fault runner deliberately does not automatically stop
services or mutate production infrastructure.

## One Entry Point Per Environment

The existing `local.py test` and `production.py` browser suites are unchanged by
default. Add `--transport-config PATH` to append shared transport checks after a
successful browser run. The config must come from a dedicated test login for
that environment. No credentials are copied into reports or command arguments.

For the running Keycloak console stack, execute just the shared transport stage
without invoking the local Clerk provisioning suite:

```sh
rtk proxy python3.11 tools/security-e2e/local.py transport-test \
  --transport-config /private/tmp/conduct-console-cli-home/.conduct/config.json \
  --transport-ca /private/tmp/conduct-console-test-ca.crt
```

For SaaS, use a dedicated disposable-workspace CLI login:

```sh
rtk proxy python3.11 tools/security-e2e/production.py --transport-only \
  --transport-config /path/to/saas-test-home/.conduct/config.json
```

`--transport-only` does not require browser passwords or the Gmail OTP broker.
It makes policy requests that can generate audit events; it does not provision
users, revoke grants, or stop services. Local transport tests reject saved SaaS
URLs; SaaS transport tests reject local or unrecognized saved Conduct URLs.

Append to either command for explicitly authorized, potentially billable inference:

```sh
--inference --model MODEL_ALIAS \
--litellm-url http://localhost:4000/v1
```

Gateway uses the saved `gateway_url` when present. An explicit `--gateway-url`
is an OpenAI base ending in `/gateway/v1/openai/v1`, and uses a separate
`GATEWAY_API_KEY` environment credential. LiteLLM uses `LITELLM_API_KEY` or a
hidden prompt. Inject credentials securely; do not put keys in shell arguments.
Different model aliases can use `--gateway-model` and `--litellm-model`.

For negative inference, install a dedicated harmless prompt-block rule first,
then pass `--blocked-prompt TEXT --block-marker UNIQUE_RULE_ID`. HTTP 401, a
generic 403, and provider outages do not count as successful policy blocking.
Inspect server/provider logs independently to prove absence of provider calls.

## Evidence and Limits

Keep existing Playwright case results as the browser/security evidence and
transport PASS/FAIL/SKIP output as the transport evidence. Transport exit zero
means the checks that ran passed, not that omitted inference or lifecycle cases
were validated. Do not claim the entire matrix passed while remaining columns
are outstanding. Existing Python/TypeScript unit tests supplement, but do not
replace, live browser and fault-injection acceptance.

The local Clerk security suite and the Skycloak console stack are distinct
fixtures. Sharing transport checks does not yet port all production browser
canaries to Keycloak. Hosted production checks must retain their disposable
workspace consent, bounded mutations, cleanup, and provider-fixture guards.
