# Federation management UI

Agent Identity owns the management surface:

- Integrations has horizontal Okta and OIDC tabs. Existing Okta sync/JWT settings
  are unchanged. OIDC connections are generic; PCAI or another product can be a
  connection name without changing trust or authorization behavior.
- OIDC supports named draft connections, issuer, audience, explicit JWKS/discovery
  URLs, supported access-token profiles and claim mappings. Validation checks
  metadata and usable public signing keys using the runtime verifier's existing
  SSRF-safe fetcher. It does not authenticate a user or confer authorization.
- Enabling/disabling trust and editing active configuration require confirmation.
  Saving a draft does not enable it. Active configuration changes increment the
  revision and invalidate previously verified delegated evidence.
- Delegation contains Principals, Caller bindings and Grants. Binding targets are
  immutable. Grants are workspace-scoped, action-limited and expire at the entered
  UTC time. Revoke disables a record rather than removing its security boundary.

All management APIs require `platform.workspace.edit`, validate the workspace and
retain existing revision checks/audits. The overview returns only the fields needed
for configuration, never service tokens or encrypted credential data. Configuration
remains separate from identities; no customer-specific protocol was introduced.

Flight Recorder event details render calling integration and acting principal as
separate fields, with grant, trust revision, verification request and evidence
expiry. Legacy/service-only events do not acquire a fabricated delegated identity.

## Rotation and operator diagnostics

The existing verifier caches JWKS for up to 300 seconds. An unknown key ID triggers
a refresh, subject to a 10-second per-connection cooldown. Rotate keys at the IdP
with an overlap window; removing a key does not evict every process cache instantly.
For urgent revocation, disable the Conduct connection or increment its revision by
saving configuration. Calls and supported workflow boundaries recheck connection
state and revision; already dispatched provider requests are not recalled.

Grant and principal revocations are read live at supported dispatch boundaries.
Expired workflow evidence cannot be extended by an approver or a state edit.
Connection validation fetches fresh public metadata/keys without receiving a user
token, but it does not invalidate other processes' runtime caches.

| Diagnostic | Operator action |
| --- | --- |
| Revision conflict | Refresh and review the current record before saving. |
| Endpoint not public / unavailable | Check public HTTPS DNS, TLS and JWKS reachability. Private IdP networking is not supported by this fetcher. |
| Discovery mismatch | Match the explicit issuer and JWKS URL to trusted discovery metadata. |
| Identity required / unmapped principal | Check service binding and approved issuer/subject, not an email address or prompt metadata. |
| Scope exceeds approval | Reduce grant actions or separately approve the binding/principal scope. |
| Evidence expired / configuration changed | Obtain fresh authenticated evidence and initiate a newly authorized request. |

## Verification

`tools/federation/phase6_harness.py` exercises real API authentication and a disposable
PostgreSQL database: admin/developer isolation, cross-workspace denial, draft-only
creation, duplicate names, revision conflicts, public-endpoint restrictions,
principal/binding/grant creation and revocation. CI runs it after phases 3-5.

The web component tests cover denied admin controls, generic draft requests,
conflict retention, explicit action selection and stale workspace responses.
`tools/federation/ui_harness.cjs` runs desktop/mobile Chromium checks with synthetic
API fixtures. It does not connect to customer identity providers. Run the web app
with `NEXT_PUBLIC_API_URL=http://127.0.0.1:59112` and Clerk disabled on port 3116,
then run the harness. Real customer IdP acceptance is still required.
