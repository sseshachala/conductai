# Federation phases 4 and 5

## Boundaries

The LiteLLM plugin authenticates its service caller separately from the initiating
user. Its trusted custom-auth handoff sends access JWT evidence only to Conduct MCP.
Inference remains in LiteLLM. See the package's FEDERATION.md for configuration.

Gateway inference and HTTP workflow launches reuse the federation resolver and
live grant checks. The added actions are `gateway.inference` and `workflows.run`.
Grants remain workspace-scoped; these phases do not add model/workflow-specific
permissions or a new policy engine. Existing unbound authentication is preserved.
Bound callers cannot access model catalogs using an inference-only grant.

Workflow initiation stores reference-only identity and its original expiry in a
server-created RunEvent, separately from caller-controlled state. Workers recheck
before execution and before each block. Expired, revoked or changed delegation
fails closed, including resume. Approval does not replace the initiating principal.
Server-issued run tokens propagate that identity to Gateway using their persisted
run association, not a caller-provided run ID. Subject headers are stripped before
provider dispatch. Every v2 routing target rechecks live delegation.

Flight Recorder and Lens structured evidence readers expose validated reference
IDs without raw tokens, subjects or mapped claims. Existing workspace/RBAC filters
remain authoritative. Attribution is historical evidence, not proof that a grant
is currently valid. Metadata is not newly covered by the Guard event hash chain.

## Verification

- `tools/federation/phase4_harness.py`: real LiteLLM 1.103.0 proxy, HTTP MCP, signed
  synthetic JWTs, PostgreSQL, two principals, allow/block and revoked/unmapped user
  denial. Inference uses a deterministic HTTP provider stub, not a paid model.
- `tools/federation/phase5_harness.py`: real Gateway HTTP, server-issued run tokens,
  HTTP workflow creation, actual worker execution, expiry/revocation and simulated
  resume with mutated approval state. The real approval UI is not exercised.
- Phase 3 separately tests restricted PostgreSQL-role/RLS authorization. Phase 4/5
  harnesses use the disposable database owner for fixture setup and execution.
- CI installs LiteLLM in an isolated environment and runs these journeys with
  PostgreSQL and Redis. JWKS is synthetic; customer IdP/PCAI acceptance is external.

No CLI changes, new feature flag or configuration UI are included. The planned UI
phase must use existing Integrations and Agent Identity components.
