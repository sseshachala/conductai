# Common identity federation: Phase 1 contract

Epic: #2283. Status: proposed contract implemented as schema tests, not runtime
federation support. No router, migration, feature flag or CLI behavior changes.

MCP is application-neutral: existing OAuth and Agent-token clients need no PCAI
configuration or headers. Federation is an additional per-integration trust path,
not a new global prerequisite. See [the harness matrix](identity-federation-testing.md)
for separate configured and unconfigured release gates.

## Ingress and ownership

1. PCAI -> LiteLLM plugin -> Conduct MCP: the plugin enforces the Guard decision;
   LiteLLM retains inference routing. Conduct Gateway is not required.
2. Client -> Conduct Gateway -> provider: Gateway applies Guard and proxies
   inference. The same trusted identity resolver serves both paths.

Both paths use an authenticated calling Agent Identity plus a separately verified
human/workload principal. A policy-check audit is not proof of inference success
or a spend receipt. Never forward identity evidence to a model provider.

## Reuse decisions

| Existing implementation | Decision |
| --- | --- |
| `app/core/auth.py` Agent-token resolution | Reuse caller authentication and workspace membership checks; keep existing public behavior. Add a narrow resolver boundary rather than another token authenticator. |
| `app/core/okta_jwt.py` | Reuse PyJWT and verification tests. Extract shared verification in Phase 2 with an Okta compatibility wrapper. Its `/v1/keys` convention is not generic OIDC discovery. |
| `app/models/integration.py` | Reuse Connections ownership and admin authorization; add a typed child trust record instead of more provider-specific columns. |
| `app/modules/auth/oauth/grants/token_exchange.py` | Existing exchange verifies Clerk and provisions CLI credentials. Preserve that flow. Extend only after specifying external subject and caller semantics; do not create a competing token endpoint. |
| `app/modules/agent_identity/models.py` | Reuse calling Agent Identity and credential lifecycle. Do not create an agent per human. |
| `app/models/user.py`, `workspace_user.py` | Keep console membership unchanged. Email and Clerk IDs cannot serve as a universal external-subject key. |
| `app/modules/guard/mcp_impls.py`, `routers/mcp.py` | Attach resolved context to the trusted request context, not tool arguments. Reuse policy evaluation and audit writers. |
| `app/modules/guard/gateway_runtime.py` | Consume the same resolver at ingress; reuse downstream policy/receipt paths. |
| `packages/conduct-litellm-guard/.../guardrail.py` | Authenticated user context currently does not reach the policy call. Add evidence handoff, not a second verifier or policy engine. |

Related work to reconcile: #1111/#1052 Okta, #844 run AgentIAM, #588 exchange.
This is not #1050 console SSO. Existing oversized modules receive only small
integration calls; extracted functionality belongs in focused modules.

## Internal contract

`app/modules/auth/federation/contracts.py` defines version 1:

- Common: server-authorized workspace, calling Agent Identity, request/run IDs.
- `service_only`: no verified principal or delegation evidence.
- `delegated`: workspace-scoped principal keyed by exact issuer + subject,
  human/workload kind, checked grant binding, mapped attributes with provenance,
  connection/audience/method, verification expiry and mapping version.
- Evidence binds the same workspace and exact issuer/subject as the principal.
  Its issuer is the identity namespace verified by the selected trust profile;
  assertion signer/key provenance is identified by the versioned connection.
- No raw tokens, email-based keys, free-form claims or secrets in the context.
- Frozen models and tuples avoid request-to-request mutation. Reject extra fields,
  cross-workspace bindings, mismatched caller/principal and empty grant scope.

These models are INTERNAL. Constructing valid JSON is not proof of identity.
The resolver verifies signatures, caller permission, connection ownership,
principal status and live grant state before constructing a context. It must
recheck expiry at use; a structurally valid historical context is not authority.
Attribute mapping may not grant console membership or roles implicitly.
Grant actions/resources represent the authorized scope for this request, not
unfiltered token scopes or the grant's entire possible authority. Runtime checks
must intersect caller permissions, principal permissions and grant scope. Resolve
resource ownership before matching scope; wildcard semantics come from existing
authorization helpers, not ad hoc string matching. Evidence expiry does not extend
grant validity. Live grant expiry/status and principal status are checked at use.

## Configuration and activation

Application preset (`pcai`, `litellm`, generic) is separate from trust method and
identity provider. Changing a preset never grants trust. Runtime policy has no
PCAI-specific branches. Issuer, audience, mappings and deployment endpoints are
workspace configuration; allowed algorithms and network protections are code
security constraints. Unknown preset support is not implied.

No new feature flag. An unconfigured integration keeps its existing service-only
path. Once configured for required principal identity, missing, invalid, expired
or unavailable verification fails closed. A disabled connection or revoked grant
must not fall through to legacy service authentication. Retain disabled bindings
so disabling trust cannot accidentally remove its enforcement requirement.
Explicitly removing federation requires authorized, audited reconfiguration.
Required-identity policy is bound to the authenticated caller and applicable
server-selected resource scope, not to the optional connection header. Omitting
that header must not select service-only mode. If multiple connections are allowed,
require an unambiguous configured selection; do not search all tenants or choose
the first successful issuer. Unknown or disabled selected connections deny.

## Trust and endpoint contract for later phases

The existing Agent credential continues authenticating the integration. User
evidence is separate from `Authorization`, never a prompt, email or `user` field.
For the direct API/MCP/Gateway handoff, reserve `Conduct-Federation-Connection`
(connection UUID) and `Conduct-Subject-Token` (sensitive bearer evidence). These
headers are proposals, not accepted by current routes. Strip them before provider
forwarding and redact them at ingress, proxies and instrumentation before rollout.
Browser direct use requires an explicit CORS review; it is not assumed.

The connection ID is a selector, not authority: resolve it only inside the
authenticated caller's workspace and verify its caller binding. Reject multiple
or conflicting evidence sources. MCP must resolve per HTTP request, never cache
one user's evidence in a shared transport/session. Missing required evidence on
any new request fails closed. An exchange-produced delegated credential, if
implemented, must carry the same server-resolved binding without losing caller
identity. Final header compatibility is an explicit Phase 2 review gate.

Trust path A: an OAuth access token with issuer, audience and token purpose
appropriate for Conduct. Do not accept OIDC ID tokens as API authorization.
Generic JWT syntax alone does not distinguish these; each connection needs a
documented access-token profile. Opaque tokens require a separately reviewed
introspection implementation, not blind JWT fallback.

Trust path B: an authorized integration's short-lived signed assertion, bound to
issuer, audience, subject, caller, workspace and scope. Require an assertion ID
and atomic replay reservation shared across workers. A legitimate retry may reuse
a completed result only when authenticated caller, request binding and payload
digest match; otherwise reject replay. No raw assertion storage.

Prefer existing RFC 8693 exchange infrastructure if the customer's token cannot
be consumed directly. Do not extend the Clerk exchange semantics implicitly.
PCAI handoff capability/audience is a customer gate, not an assumed feature.

Invalid evidence returns 401; authenticated but forbidden delegation returns 403;
verification dependency outage returns 503 with no policy/inference execution.
Use stable error codes and correlation IDs, never raw tokens or claims in errors.
The LiteLLM adapter must not turn required-identity verification failures into an
allow under its legacy optional fail-open policy. Test this explicitly in Phase 4.
For MCP, preserve existing JSON-RPC protocol semantics: authentication can fail at
the HTTP boundary, while authorization failures during a tool call need stable
structured error codes. The adapter must recognize both HTTP and tool-level
identity failures as non-bypassable, including dependency outages when identity
is required. A generic transport error must not erase this distinction.

## Persistence and migration plan

Phase 2: additive federation connection child records keyed by workspace and
Integration, holding trust configuration, status, caller binding and version.
Use existing secret storage references, not signing secrets in config JSON.

Phase 3: add external principals unique on (workspace, exact issuer, exact subject)
and grants binding workspace, calling agent, principal/explicit principal selector,
actions/resources, status and expiry. Unknown users deny by default; approved
provisioning is a separate configured policy. Optional links to console membership
require explicit verified mapping, never email matching or automatic role grants.
Keep exact issuer identity; do not normalize two issuer URLs into one identity.

Persist audit provenance by reference/version alongside caller and principal IDs,
including the checked scope. Keep the existing audit hash/serialization contract:
new provenance must be covered by the established integrity mechanism or a
versioned extension, not silently advertised as hash-protected. Phase 3 supplies
basic attribution before the LiteLLM pilot; Phase 5 extends platform readers.

No backfill invents verified humans for legacy events. Existing Okta rows keep
their resolver and behavior until an explicit reviewed migration is available.
Deploy additive schema before readers/writers. Rollback must disable/reject
federated traffic, not revert a required-identity caller to service-only access.

## Threat model and required tests

| Threat | Required control / test |
| --- | --- |
| User metadata spoofing | Only verified evidence produces principal context; ignore identity tool arguments. |
| Confused deputy / tenant substitution | Workspace from caller authentication; caller AND principal grants constrain actions/resources. |
| ID-token or wrong-audience substitution | Explicit token profile, exact issuer/audience, signature/expiry/not-before and algorithm validation. |
| SSRF / malicious keys | Admin-configured HTTPS endpoints, redirect denial, DNS/private-address protections and bounded responses/timeouts. Enterprise internal IdPs need explicit network policy, not a global protection bypass. |
| Replay and rotation | Atomic assertion replay handling, bounded key cache, unknown-key refresh rate limits, tested key rollover. |
| Revoked user or connection | Live local status/grant checks. Document IdP revocation propagation: signature verification alone cannot detect immediate upstream revocation. |
| Concurrent users | Immutable request contexts; key caches may be shared, principal authorization must not leak across requests/tenants. |
| Async workflow / approvals | Persist initiating attribution, distinguish executor and approver. Reauthorize sensitive steps with current grants; expired initiating evidence is historical provenance, not perpetual authority. |
| Secret leakage | Evidence redacted at ingress/logging; never persisted in audit or forwarded to model providers. |
| Legacy regression | Existing Okta, Clerk exchange, Agent-token, CLI/sync and unconfigured Gateway/MCP behavior unchanged. |

Runtime tests belong to their implementation phases; Phase 1 schema tests do not
claim signature verification or production security acceptance.

## Delivery gates

1. Phase 1: approve this contract/storage plan and schema invariants.
2. Phase 2: connection admin authz + two issuer fixtures + verification failures.
3. Phase 3: shared resolver, delegation checks and initial auditable attribution.
4. Phase 4: real LiteLLM/MCP test, two users/different decisions, no Conduct Gateway
   inference dependency. Customer PCAI acceptance is a separate external gate.
5. Phase 5: direct Gateway plus workflows, expiry/revocation and tenant-scoped reads.
6. Phase 6: Connections/Agent ID UI, Flight Recorder/Lens, rotation diagnostics,
   documentation and customer acceptance. No CLI changes required.

Every PR: reuse existing helpers; target under 500 lines, maximum 600 per new
handwritten source/test file; split by responsibility. No customer hard-coding.
Any LLM prompts go in the owning module's `prompts/*.txt`; identity decisions
remain deterministic. This phase needs no prompts.
