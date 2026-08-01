# Security policy

Conduct governs how AI agents act inside a workspace: what prompts they send, what
tools they call, what secrets they see, and what side effects they cause. This
document describes the current security model, how to report vulnerabilities, and
the material limitations of the controls.

Conduct is production software, but its security posture continues to evolve. This
document is a public summary and is not exhaustive. Nothing here is a certification
or a substitute for a deployment-specific security review.

## Reporting a vulnerability

Report suspected vulnerabilities privately by emailing `hello@conductai.ai`. Do
not open a public issue, discussion, or pull request with exploit details.

Include the affected version, configuration, impact, and the smallest reproduction
you can safely provide. We will acknowledge the report, investigate, and coordinate
disclosure. Do not access data that is not yours or test against deployments you
do not own.

## Supported versions

Security fixes ship in the current `main` branch and the most recent tagged CLI /
booster releases. Older releases are not backported.

## Threat model

### Scope

Conduct is deployed in two modes:

- **SaaS** (`conductai.ai`): multi-tenant, workspaces isolated by `workspace_id` at
  every query. Sign-in through Clerk.
- **Self-host**: single-organization deployment in the operator's own cloud. Sign-in
  through the operator's chosen identity provider.

Both modes assume authenticated internal users. External API access requires an
agent token (`cond_agt_*`) minted through the token-exchange endpoint (RFC 8693) or
the CLI sign-in flow.

Conduct's Guard proxy is designed as an in-line enforcement point for LLM and MCP
traffic within a deployment. It is not a hardened public multi-tenant service
boundary.

### Protected assets

In-scope assets:

- User credentials and third-party OAuth tokens stored in the credential vault
- Agent identity tokens (`cond_agt_`, `cond_run_`, `cond_cred_`, `cond_ref_`,
  `cond_api_`)
- Playbook definitions and run history
- Guard audit trail (hash-chained)
- Findings, remediation state, and observability data
- Workspace configuration, RBAC assignments, spend budgets, and Guard policy

### Actors

- **Internal users**: viewer, developer, admin, and security roles per workspace,
  resolved through the RBAC permission matrix.
- **Workspace admins**: privileged content readers and policy administrators. Admin
  reads are logged; they are not gated behind additional user approval.
- **Deployment operators** (self-host only): full control of the cloud account,
  database, encryption keys, network egress, and initial admin grants.
- **The agent**: an untrusted actor for authorization purposes. All policy checks
  (permissions, guard rules, credential access, spend budgets) are enforced at the
  API, proxy, and executor layers.
- **Sandbox processes**: execute model-generated commands with per-run credentials.
- **Model providers**: receive whatever prompt content is routed through them and
  are subject to their own retention policies.
- **MCP servers and connected tools**: authenticate as themselves but return
  untrusted content.

### Trust boundaries and operator assumptions

- The deployment operator controls the database, encryption keys, network egress,
  and initial admin grants. Conduct does not protect a deployment from a malicious
  or compromised operator.
- A workspace admin is a privileged content reader by design, not only a policy
  administrator. Admin content reads are logged but require no additional user
  approval.
- Model providers receive whatever content is routed through them. Guard proxy
  strips known credential patterns before forwarding, but does not sanitize all
  potentially sensitive content. Operators must evaluate provider retention
  policies.
- The agent is not trusted to make authorization decisions. Core enforces
  identity, workspace scope, RBAC permissions, credential handle allowlists, and
  deterministic effect gates around it.
- MCP servers and their outputs are untrusted content. Authentication proves the
  identity of the server; it does not make the returned content safe.
- The sandbox remains a sensitive boundary because it executes model-generated
  commands and can hold usable credentials while a run is in progress.

### What the controls do and do not guarantee

Conduct enforces:

- Workspace-scoped isolation of all persisted data (application-level filtering on
  `workspace_id`).
- RBAC-backed permission checks on every API endpoint through
  `require_permission()`.
- Guard policy evaluation on outbound LLM prompts, MCP tool calls, and shell
  execution against a rule pack maintained per workspace.
- Credential broker checks with per-token expiry, handle allowlists, and usage
  counts.
- Tamper-evident hash-chained audit trail of Guard decisions and run events.
- Configurable spend budgets with fail-closed enforcement per workspace.
- Signed webhook delivery with idempotency keys.
- Encryption at rest for the credential vault via KMS-managed keys.
- RFC 8693 token exchange for federated identity into agent tokens.

These controls are designed to reduce cross-workspace access, keep credentials
within their authorized scope, and make actions attributable. They are not a
formal non-interference proof, and they do not guarantee that a model cannot
disclose data or take unintended action.

Conduct does not guarantee:

- **Model output correctness or safety.** The agent can produce wrong or harmful
  content even when every policy check passes.
- **Prompt injection resistance from tool results.** Guard screens outbound
  prompts for credential leaks and known injection patterns, but does not
  currently screen tool result content (MCP responses, shell output, web fetches)
  before it is injected into the next model turn. Untrusted content returned by a
  tool can influence subsequent behavior.
- **Sandbox non-escape.** Sandbox backends (Modal, E2B, local, SSH) rely on their
  underlying isolation guarantees. Sandbox breakout is out of scope for the
  Conduct threat model.
- **Command policy completeness.** The Guard rule pack matches known-dangerous
  patterns with regex. Obfuscation, encoding, or writing a script and then
  executing it can evade it. Command policy is defense in depth, not a sandbox
  boundary.
- **Non-interference between admins and users.** A workspace admin can read any
  content in the workspace. Separating admin access from user data requires
  operator-level separation of duties, not a Conduct control.
- **Availability or rate-limit-as-security.** Rate limits are best-effort and are
  not designed as a security control.

### Known limitations

The following are known gaps tracked as issues on this repository:

- **`cond_cred_` tokens are stored in plaintext** in the database. Encryption at
  rest is planned.
- **`cond_run_` tokens have no default wall-clock TTL.** They are invalidated on
  run completion or manual revocation, but do not expire on time alone.
- **Refresh token storage uses bare SHA256** without salt or key derivation.
  Migration to a slow KDF is planned.
- **Tool-result screening is not yet implemented.** See the prompt-injection note
  above.
- **Sandbox credentials are plaintext in the process while in use.** A compromised
  agent process can read credentials made available to it for the duration of the
  run.
- **MCP is transport, not authentication.** An MCP server must independently
  authenticate its caller; the MCP hop adds no auth guarantee.
- **Guard tokens are opaque and validated by database lookup.** Migration to
  signed self-contained tokens (with audience and scope-version claims) is
  planned.

### Cryptographic material

- **Encryption at rest**: AES-256-GCM for the credential vault. The 32-byte key
  is supplied by the operator through the `ENCRYPTION_KEY` environment variable.
  Startup fails fast in production if the default development key is still in
  use. A shorter key is rejected at startup.
- **Subject token verification**: RS256 for Clerk-issued JWTs presented to the
  RFC 8693 token-exchange endpoint. Self-host deployments configure their own
  issuer.
- **Agent token minting**: 32-byte random hex prefixes. Stored as SHA256 hashes
  in the database, except `cond_cred_` (see limitations).
- **Audit hash chain**: SHA256 over
  `"{iso_timestamp}|{tool_call}|{decision}|{previous_entry_hash}"`. Each
  `GuardAuditEvent` row stores both `previous_hash` and `entry_hash`; the
  `/guard/verify` endpoint recomputes and checks every entry.
- **Signed webhooks**: HMAC-SHA256 for Slack (`v0=` prefix), GitHub and
  Bitbucket (`X-Hub-Signature-256`), and Clerk (svix format). Vercel uses
  HMAC-SHA1 as required by their provider. Signature comparison uses
  constant-time equality.

### Out of scope

- Denial of service against Conduct itself or against deployed workloads.
- Availability guarantees, RTO, or RPO.
- Correctness or safety of AI-generated content.
- Third-party provider security (LLM vendors, MCP servers, sandbox backends,
  identity providers).
- Deployments modified from the published `main` branch.
