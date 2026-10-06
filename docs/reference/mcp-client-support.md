## MCP Client Acceptance

All listed client surfaces are supported and user-tested as of 2026-10-05.
Detailed canary results and lifecycle checks are recorded separately below.

### Surface Coverage

The user confirmed testing all surfaces. Local adapters are listed in
[the tool catalog](tool-catalog.md).

| Surface | Connection | Status |
|---|---|---|
| Claude.ai | OAuth MCP connection | Supported (user-tested) |
| ChatGPT web | Custom MCP plugin | Supported (user-tested) |
| Copilot VS Code | OAuth MCP connection | Supported (user-tested) |
| Copilot CLI | OAuth or bearer-token MCP connection | Supported (user-tested) |
| GitHub coding agent | Scoped Agents secret and MCP fixture | Supported (user-tested) |
| Claude Code | Local MCP configuration adapter | Supported (user-tested) |
| Codex CLI | Local MCP configuration adapter | Supported (user-tested) |
| Codex Desktop | Local MCP configuration adapter | Supported (user-tested) |
| Cursor | Local MCP configuration adapter | Supported (user-tested) |
| Windsurf | Local MCP configuration adapter | Supported (user-tested) |

OpenAI also supports plugins across ChatGPT and Codex, including ChatGPT Work.
Local hooks need scripts installed in the runtime; a remote MCP connection does not
install hooks. See [OpenAI plugin architecture](https://developers.openai.com/plugins/concepts/plugins)
and [plugin packaging](https://developers.openai.com/plugins/build/plugins).

### Lifecycle Acceptance

Surface testing and approval checks are user-confirmed.

| Client | Authentication | Connect/read | Refresh | Reconnect | Workspace switch | Revocation | Mutation | Approval |
|---|---|---|---|---|---|---|---|---|
| Claude.ai | OAuth + PKCE | Passed (user-tested) | Pending | Pending | Pending | Pending | Pending | Passed (user-tested) |
| ChatGPT web | OAuth + PKCE | Passed (user-tested) | Pending | Pending | Pending | Pending | Pending | Passed (user-tested) |
| Copilot VS Code | OAuth + PKCE | Passed (user-tested) | Pending | Pending | Pending | Pending | Pending | Passed (user-tested) |
| Copilot CLI | OAuth + PKCE; token mode retained | Passed (user-tested; token canary recorded) | Pending | Passed (token) | Pending | Pending | Pending | Passed (user-tested) |
| GitHub coding agent | Scoped Agents secret | Passed (user-tested) | Secret rotation | Pending | Pending | Pending | Pending | Passed (user-tested) |

### Server Lifecycle Results

2026-10-05: **235 passed, 0 failed, 0 skipped** on Python 3.11 and isolated
PostgreSQL fixtures, including 46 persisted credential/MCP integration cases.

| Check | Server result |
|---|---|
| Refresh | Passed: expired access renews; old tokens and refresh replay are rejected. |
| Revocation | Passed: revoked credentials, removed members and deactivated identities cannot call MCP or refresh, including previously initialized sessions. |
| Workspace switching | Passed: each authorized grant stays in its workspace; forged headers and unauthorized grants are rejected. |
| Approval | Passed: pending actions leave state unchanged; approval permits the action; denial and timeout prevent it. Self-approval, cross-workspace decisions and late decisions are rejected. |

The approval integration cases use the real persisted request and HTTP decision
flow with a disposable action and fixture approver identity/role. Native-client
lifecycle results above remain separate. Production and saved client settings
were unchanged.

Results and test paths are recorded in
`tools/mcp-acceptance/results/2026-10-05-server-lifecycle.json`.

### Latest Live Runs

2026-10-05, user confirmation:

- The user confirmed testing all listed surfaces and requested marking them supported.
- The user also confirmed testing Conduct approval checks, including denial and timeout.
- Confirmation is recorded in
  `tools/mcp-acceptance/results/2026-10-05-user-surface-confirmation.json`.
- The server-side attribution fix passed 181 regressions. Its deployment and a
  fresh, independently verified ChatGPT audit label are still outstanding.

2026-10-05 at 21:39 UTC, SaaS, ChatGPT web, manual canary:

- The user confirmed the call ran on `chatgpt.com` and returned the exact marker.
- Conduct recorded `guard_activity` as allowed with the correct actor, agent
  identity and workspace.
- Client attribution did not pass: the server recorded `codex`, not ChatGPT.
  That run was partial because of the client-label mismatch.
- The client build and authentication mode were not captured. Lifecycle and
  Conduct approval checks were not part of that canary.

Nonsecret evidence is recorded in
`tools/mcp-acceptance/results/2026-10-05-saas-chatgpt-canary.json`.

The attribution fix recognizes ChatGPT in MCP `clientInfo.name` and preserves
that label on later calls and token refresh. Clients can also send
`X-Conduct-Ai-Tool: chatgpt`. It does not relabel actual Codex clients. After
deployment, reconnect the ChatGPT plugin and run a new canary to verify its audit
label. A connector that reports only `codex` must identify its ChatGPT frontend;
Conduct cannot distinguish the two from that name alone.

2026-10-05 at 21:04 UTC, SaaS, Claude.ai, manual canary:

- `guard_activity` succeeded after the user allowed the tool in Claude.ai.
- Conduct recorded the exact marker as allowed with the correct actor, agent
  identity, workspace and `claude.ai` label.
- The result was checked independently against the server audit event.
- The client build and authentication mode were not captured. OAuth lifecycle
  checks were not part of that canary. Claude.ai's tool permission is not a Conduct approval check.

Nonsecret evidence is recorded in
`tools/mcp-acceptance/results/2026-10-05-saas-claude-ai-canary.json`.

2026-10-05 at 17:22 UTC, SaaS, Copilot CLI 1.0.91, bearer-token mode:

- Connect and reconnect passed through the installed native client.
- Both MCP events had the correct actor, agent identity, workspace and `copilot-cli` label.
- The saved credential returned 200. This run used the unchanged saved Copilot
  MCP configuration, without a temporary override.
- A separate run using the current Conduct CLI login also passed both phases.
- OAuth lifecycle and mutation checks were not run. Other surfaces were not
  exercised in that run.

Nonsecret rerun evidence is recorded in
`tools/mcp-acceptance/results/2026-10-05-saas-copilot-cli-rerun.json`.
The earlier failed run is preserved in
`tools/mcp-acceptance/results/2026-10-05-saas-copilot-cli.json`.

### Run the Checks

Server checks run in CI against PostgreSQL. They cover registration, PKCE, discovery,
invocation, attribution, expiry, refresh replay, reconnect, workspace switching,
revocation, and the mutation/approval transport gate. Existing Keycloak browser
canaries test the on-prem browser login and CLI callback.

Native checks use `tools/mcp-acceptance/acceptance.py`. The same runner works for SaaS
and on-prem; select the deployment and API in the plan. Credentials are environment
references, not values in the plan.

```bash
rtk proxy python3 tools/mcp-acceptance/acceptance.py \
  --plan /private/tmp/mcp-acceptance-plan.json \
  --report /private/tmp/mcp-acceptance-results.json \
  --matrix /private/tmp/mcp-client-support.md \
  --ca /private/tmp/conduct-console-test-ca.crt \
  --allow-fixture-mutations \
  --allow-github-agent \
  --require-all
```

Start with `tools/mcp-acceptance/plan.example.json`. Set the workspace, actor and
agent IDs to dedicated test fixtures, and set the installed client version.
`MCP_ACCEPTANCE_OBSERVER_TOKEN` must have access to the fixture's audit events.
Omit `--ca` when the deployment uses a publicly trusted certificate.

Missing client phases stay pending. A failed phase stops that client's remaining
phases. Zero completed probes is an error. `--require-all` fails until every
client/scenario has completed. Reports contain event references, not raw tool
payloads, browser traces or credentials.

### Native Client Setup

Copilot CLI runs the installed `copilot` command with only the declared Conduct
tools allowed. Shell, file and web tools are denied. Existing OAuth configuration
is used unchanged. The runner checks the installed version and verifies fresh MCP
events against the expected actor, agent and workspace.

Claude.ai, ChatGPT and VS Code run through Playwright attached to their real UI.
Use a dedicated browser or VS Code profile with loopback-only remote debugging.
Set `cdp`, `page_prefix`, `version`, and the current client's selectors in the plan.
Each phase has `steps`, `output_selector`, and `output_text`. Supported actions are
`click`, `fill`, `press`, `visible`, and `fill_env`. Use `fill_env` for test IdP
credentials named `MCP_NATIVE_*`, and explicitly list the allowed `auth_origins`.
An optional step `page_prefix` selects the authorization tab or popup.
No cookies, passwords, traces or screenshots are exported.

```json
{
  "cdp": "http://127.0.0.1:9222",
  "page_prefix": "https://chatgpt.com/",
  "version": "2026-10-05",
  "phases": {
    "connect": {
      "steps": [
        {"action": "fill", "selector": "[contenteditable=true]", "value": "Use Conduct MCP guard_activity with summary {marker}, then conduct_current_workspace. Return the marker after the tool succeeds."},
        {"action": "press", "selector": "[contenteditable=true]", "value": "Enter"}
      ],
      "output_selector": "[data-message-author-role=assistant]",
      "output_text": "{marker}",
      "checks": [{"kind": "audit", "tool": "guard_activity", "decision": "allowed"}]
    }
  }
}
```

Selectors must match the client build under test. This snippet is a prompt-step
example, not a recorded successful ChatGPT run. Connect phases can include the
actual connector creation, OAuth consent and discovery UI steps before the prompt.

### Lifecycle Fixtures

Configure seven phases per client: `connect`, `refresh`, `reconnect`,
`workspace-switch`, `revocation`, `mutation`, and `approval`.

Each phase requires independent server `checks`. An `audit` check matches a fresh
marker, MCP source, tool, decision, actor, agent and workspace. A `json` check reads
an API-relative `path`, follows a `pointer` array, and compares `equals`. A `denied`
check uses a fixture `token_env` and requires HTTP 401 or 403 from canonical MCP.
Use JSON checks to assert that a disposable mutation did or did not happen.

`before`, `verify`, and `after` contain argument arrays for trusted fixture commands.
They run without a shell and receive only the explicitly listed `fixture_env`
variables. `after` runs even on failure; failed restoration fails the test.
Mutation phases need both `--allow-fixture-mutations` and `disposable: true`.

For the dedicated local stack, `fixture.py` can expire or revoke exactly one
credential UUID, verify it, and restore fixture changes. It accepts only a
loopback database connection supplied through `MCP_ACCEPTANCE_DATABASE_URL`.
Its snapshot stores UUIDs and timestamps, never tokens or hashes.

```bash
rtk proxy python3 tools/mcp-acceptance/fixture.py expire \
  --workspace WORKSPACE_UUID --identity AGENT_UUID --credential CREDENTIAL_UUID \
  --snapshot /private/tmp/mcp-credential-fixture.json --allow-disposable-fixture
```

Use `verify-refresh` after the native client renews. It requires an extended expiry
and fresh MCP events for the same credential session and agent. Token rotation
keeps the session UUID; also check that the old access token is rejected.
`verify-revoked` requires the credential to be revoked and no new
MCP events for the marker. `restore` reverses explicit test expiry/revocation but
does not undo refresh rotation. Identify the credential session from MCP audit
`routing_meta.credential_session_id`; do not guess another client's credential.

For SaaS, supply fixture commands using the dedicated test workspace's supported
admin/token APIs. Do not run lifecycle mutations on a user's ordinary workspace.

Approval phases have at least two `rounds`: the first invokes the protected action
and checks pending approval plus unchanged state; `control_after` invokes the
separate approver fixture; the next round retries through the native client and
checks the actual mutation. Use the same session and exact action across rounds.
The outer phase `checks` assert the final state. Also test rejected and timed-out
approvals in the fixture verifier. Model text alone is not approval evidence.

### GitHub Coding Agent

Use a disposable repository. Put the reviewed fixture profile from
`tools/mcp-acceptance/github-agent.example.md` at
`.github/agents/conduct-acceptance.agent.md` in that repository.

Add **Agents** secrets/variables, not ordinary Actions secrets:

- `COPILOT_MCP_CONDUCT_URL`: the selected deployment's public `/mcp` endpoint.
- `COPILOT_MCP_CONDUCT_TOKEN`: a dedicated scoped integration token.

Allow only the canary tools in the profile and scope the token to the fixture
workspace. Run against a dedicated test user with cloud-agent entitlement.
Set the plan's `github-agent` `repo`, `custom_agent`, `base_branch`, `version`,
workspace/actor/agent IDs, and phases. The runner assigns a real task to
`copilot-swe-agent[bot]` and requires its pull request plus matching server evidence.
An ordinary Actions job does not count. The runner never merges the PR.
Fixture cleanup should close the canary issue/PR by its exact marker.

GitHub does not support remote MCP OAuth. For its `refresh` phase, rotate the
scoped Agents secret and verify the old token is denied while a new actual agent
task succeeds. Workspace switching uses another scoped fixture token, not a header
that changes the existing token's authority.

Client requirements: [ChatGPT OAuth](https://developers.openai.com/plugins/build/auth),
[Copilot CLI](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference),
[GitHub MCP support](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/mcp-and-cloud-agent),
[Agents secrets](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/configure-mcp-servers).
