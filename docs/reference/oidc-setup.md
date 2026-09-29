## Configure OIDC identity and delegation

Use OIDC federation when an external application calls Conduct on behalf of a verified user or workload. This configures runtime identity, not login to the Conduct console. [HPE's PCAI (Private Cloud AI)](https://www.hpe.com/us/en/products/private-cloud/pcai.html) is one application that can use this generic connection type, subject to configuring and verifying its identity-provider handoff.

### Before you begin

- Select the intended workspace. Administration requires `platform.workspace.edit`.
- Ask your IdP administrator for the exact issuer, intended Conduct audience, public HTTPS JWKS URL, access-token profile, and stable subject IDs for two test users.
- Use RS256-signed OAuth access tokens. Login ID tokens, opaque tokens, and access tokens intended only for another service are not supported by this flow.
- Identity endpoints must be publicly reachable over HTTPS on port 443. Private network endpoints, embedded credentials, query strings, fragments, and redirects are not supported by the verifier.
- Keep tokens in your secret manager, never in connection fields, issues, logs, or prompts.

### 1. Create a connection

Open **Agent Identity > Integrations > OIDC**, then select **New connection**.

| Field | What to enter |
| --- | --- |
| Connection name | A recognizable name, such as `HPE PCAI Production`. The name does not determine the trust protocol. |
| Issuer URL | The exact issuer matching the access token's `iss` claim. |
| Audience | The intended Conduct API audience matching `aud`. Agree this value with the IdP administrator; do not reuse an unrelated service audience. |
| JWKS URL | The trusted public signing-key endpoint. Never enter a private key. |
| Discovery URL | Optional provider metadata URL. Its issuer and JWKS location must match the explicit configuration. |
| Access token profile | Match the IdP's actual profile: JWT header `typ: at+jwt`, or claim `token_use: access`. |
| Signing algorithm | RS256, currently the only supported algorithm. |
| Claim mappings | Optional explicit token-claim mappings. They cannot assign Conduct roles, workspace IDs, principal IDs, or Agent Identity IDs. |

Select **Save** (labelled **Save draft** in earlier builds). The new connection is stored as a **draft**, not activated. The form closes and the saved connection appears in the list.

### 2. Validate and enable trust

In the connection's **Actions** column, select the shield-check **Validate** icon. It checks fresh metadata and usable signing keys using the runtime verifier's network restrictions. It does not verify a user's token or approve delegation.

Resolve validation errors, then select **Enable** and confirm. The connection becomes **active**, and the button changes to **Disable**. Validation and activation are separate actions; saving alone never enables a new connection.

Record the connection ID shown in the list for the integration configuration.

### 3. Approve principals

Select **Manage principals and delegation**, or open **Agent Identity > Delegation**. Under **Principals**, select **Add principal**.

Enter the issuer and stable subject (`sub`), select human or workload, and approve only necessary actions. An email address is not a substitute for the issuer/subject pair. Repeat for each approved test user.

A principal represents the acting user or workload, separately from the service's Conduct Agent Identity. Do not create a service identity for every human user.

### 4. Bind the calling integration

Create or select a dedicated API-type Agent Identity for the calling service and securely provision its Conduct-issued `cond_api_*` credential.

Under **Caller bindings**, add a binding selecting that service identity, the active OIDC connection, and permitted actions. This identifies which application may submit delegated identity evidence through the connection.

The Conduct credential authenticates the application. The IdP access token identifies the acting user. Neither credential replaces the other.

### 5. Grant delegation

Under **Grants**, select the caller binding and approved principal, choose allowed actions, and set an expiry in UTC. Grants are workspace-scoped and cannot exceed either the principal's or binding's approved actions.

For example, permit the LiteLLM service to perform `mcp.guard_check_prompt` on Alice's behalf. Direct Gateway inference needs its own `gateway.inference` permission; workflow initiation needs `workflows.run`.

### 6. Connect LiteLLM

Use a Conduct LiteLLM plugin build containing federation support. Configure these variables on the plugin host through your deployment's secret/configuration management:

| Variable | Purpose |
| --- | --- |
| `CONDUCT_API_URL` | Your Conduct API origin. |
| `CONDUCT_AGENT_TOKEN` | The service's Conduct-issued API credential (`cond_api_*`). Despite the variable name, delegated mode requires an API-type credential. |
| `CONDUCT_FEDERATION_CONNECTION` | The saved OIDC connection ID. |

The host's trusted LiteLLM authentication integration must call `conduct_litellm_guard.auth.with_subject_token(auth, access_token)` after authenticating the user and return that enriched authentication context. Environment variables alone do not implement the customer's authentication handoff.

The plugin supplies the Conduct credential and separate user evidence to Conduct MCP. Conduct verifies the token, active connection, principal, binding, and grant before applying Guard policies. Unsigned request metadata or a supplied user name cannot establish identity.

**Inference remains in LiteLLM.** This plugin path needs no Conduct Gateway configuration. Direct Gateway clients use a separate enforcement path with the same identity contract.

### 7. Verify and revoke

Test two approved users with policies producing different expected outcomes. Inspect Flight Recorder for the calling integration, acting principal, and policy decision. Lens exposes recorded attribution through its existing evidence readers.

Revoke one user's grant and repeat their request: it must be denied without falling back to service-only identity. Also test expired evidence and an unapproved subject. Metadata validation does not replace runtime tests.

A plugin policy-check event does not prove inference completed and is not a Gateway receipt or spend record. Customer PCAI/IdP acceptance requires the actual customer authentication flow, not only synthetic tokens.

### Troubleshooting and rotation

- **Revision conflict:** refresh, review the current record, and retry.
- **Endpoint unavailable or not public:** check public HTTPS DNS, TLS, and JWKS reachability. Private IdP networking is not supported by this fetcher.
- **Invalid identity:** check signature, issuer, audience, expiry, and access-token profile. Do not substitute a login ID token.
- **Unmapped principal or denied delegation:** check issuer/subject, active binding, approved actions, workspace, and grant expiry.
- **Key rotation:** publish overlapping keys. Runtime JWKS caching lasts up to 300 seconds; unknown key IDs trigger refresh subject to a 10-second cooldown. Removing a key does not instantly clear every process cache.
- **Urgent revocation:** disable the connection, principal, binding, or grant. Subsequent supported authorization boundaries recheck state. Disabling a binding does not restore service-only access.
- **Active configuration edits:** confirmation is required. Saving increments the revision and invalidates existing delegated evidence, including pending workflows. Already dispatched provider requests cannot be recalled.

Integrations without federation bindings retain their existing authentication behavior. This setup does not require a CLI upgrade or changes to `conduct guard sync`.
