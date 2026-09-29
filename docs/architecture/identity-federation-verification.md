# Federation verification foundation (Phase 2)

The workspace-owned configuration endpoint is
`/workspaces/{workspace_id}/integrations/{integration_id}/federation` (GET/PUT).
It reuses `platform.workspace.edit`, existing credentials and audit storage.
PUT requires `expected_revision` (0 for creation). Stale saves return 409.
Both application queries and a composite database foreign key bind connections
to the integration's workspace. Saves do not fetch endpoints or accept tokens.

Trust configuration supports application presets `pcai`, `litellm` and `generic`;
these are labels, not alternate authentication implementations. Issuer, audience,
JWKS/discovery endpoints and claim mappings are supplied by the administrator.
Only draft/disabled lifecycle states are accepted until delegation enforcement
exists. The verifier is an internal building block, not an authorization grant.

The initial cryptographic profile is RS256 OAuth access JWTs with explicit
`at+jwt` or signed `token_use=access` purpose. ID tokens and opaque access tokens
are not supported. JWT registered-claim verification is shared with Okta without
changing its existing cache or authentication routing. Verified mapped attributes
cannot directly become Conduct roles, workspace IDs or principal IDs.

JWKS caches are bounded and partitioned by workspace, connection, configuration
and revision. Unknown keys trigger rate-limited refresh. Expired keys are not
used during an outage. Cached public keys never cache a resolved principal.

Remote metadata uses public HTTPS port 443 with TLS hostname verification,
validated/pinned DNS addresses, bounded response size and timeouts, no redirects
and no environment proxies. Private/loopback, metadata, multicast and IPv6
transition addresses are rejected. Private enterprise IdPs require a separately
reviewed egress design; this phase does not silently allow internal endpoints.
Optional discovery must match the exact configured issuer and JWKS URI.

No federation token reaches CLI, MCP or Gateway authentication in this phase.
Phase 3 must resolve live principals and delegation grants and fail closed when
required identity is missing, invalid, disabled or revoked. Application-neutral
MCP and direct Gateway remain separate required acceptance paths. Integration
assertions/replay controls are not implemented by this access-token verifier.
