# Delegated identity through LiteLLM

This optional integration keeps inference in LiteLLM. Conduct receives the policy
check over MCP, using two separate credentials:

- `CONDUCT_AGENT_TOKEN`: the dedicated integration's Conduct `cond_api_` credential.
- Subject evidence: an authenticated user's OAuth access JWT whose audience permits
  Conduct, handed off by server-side custom authentication.

Configure `CONDUCT_FEDERATION_CONNECTION` with the workspace connection UUID and
`CONDUCT_API_URL` with the Conduct API origin. An administrator must activate the
connection, approve issuer/subject principals, bind the integration and grant
`mcp.guard_check_prompt`. Configure the existing Conduct guardrail as a default-on
`pre_call` guardrail.

In your existing LiteLLM custom-auth callback, after successful authentication:

```python
from conduct_litellm_guard.auth import with_subject_token

# authenticated_context is the UserAPIKeyAuth returned by your trusted auth layer.
# conduct_access_token must be issued for Conduct, not merely for LiteLLM.
return with_subject_token(authenticated_context, conduct_access_token)
```

Do not obtain evidence from user-supplied request metadata. The helper stores it
in a private, masked attribute, not serialized auth metadata. Conduct independently
validates its signature, issuer, audience, expiry, principal and grant on every call.
This does not implement token exchange: an IdP token intended only for another
audience must not be forwarded as Conduct evidence.

Missing or invalid identity always blocks, even with legacy `fail_open` settings.
Configured federation also fails closed on policy-service outages. Unconfigured
integrations retain the existing service-only path; bound callers cannot downgrade
by omitting the configuration or evidence headers.

The integration harness tests LiteLLM Proxy **1.103.0**, custom auth and chat
completions `pre_call` over real HTTP. Other versions, endpoints and a customer's
PCAI deployment require separate acceptance testing. No provider keys or user
tokens should be placed in examples or committed configuration.
