---
status: accepted
date: 2026-07-30
decision-makers:
  - Conduct engineering
---

# ADR-0002: Policy-pack schema and applicability contract

## Context

Conduct ships a base policy pack and separate packs for regulatory and risk
frameworks. The same resolved rules are consumed by multiple enforcement
surfaces with different matcher support.

Historically, an action such as `block` could be mistaken for proof that every
surface could block the rule. Pack consumers could also drift by dropping
unsupported matcher fields during serialization.

## Decision

Policy packs remain separate, versioned JSON documents organized by framework
or product concern. Conduct will not merge them into one monolithic rules
file.

Each rule must include:

- a stable rule ID;
- persona applicability (`agent` or `proxy`);
- matcher fields and action;
- severity and framework references where applicable;
- a versioned `enforcement` capability contract.

The enforcement contract records Proxy, Hook, MCP, and Runtime status,
guarantee text, named dependencies, and known limitations. The allowed status
values are `hard`, `conditional`, `advisory`, and `not_supported`.

Pack validation is executable:

- every shipped rule must contain valid enforcement metadata;
- non-blocking actions cannot claim hard blocking;
- a surface cannot claim support for an incompatible persona or matcher shape;
- conditional claims must name their dependencies;
- generated documentation must match the checked-in pack metadata.

Workspace policy resolution follows these rules:

1. Resolve installed packs, honoring an exact pinned version or selecting the
   highest semantic version.
2. Merge custom workspace rules.
3. Apply workspace overrides and time-bounded exceptions.
4. Filter rules for the target persona and enforcement surface.

Overrides change effective workspace policy, not the underlying capability
claim. Disabling or weakening a pack rule requires a reason and future expiry.
Custom rules without enforcement metadata receive a conservative generated
contract and are never assumed to be hard enforcement.

## Alternatives considered

### One canonical monolithic rules artifact

Rejected because Conduct supports independently versioned compliance and risk
packs with different installation and commercial lifecycles.

### Infer capability solely from action and persona

Rejected because `block` says what should happen after a match, not whether a
surface can observe or preserve the required matcher.

### Maintain coverage documentation manually

Rejected because prose drifts from code and cannot fail CI when claims become
incorrect.

### Permit each consumer to interpret pack fields independently

Rejected because silent matcher loss can turn scoped rules into wildcard rules
or create false coverage claims.

## Consequences

### Positive

- Packs remain modular while sharing one validated contract.
- API, UI, CI, and generated evidence use the same claims.
- Pinned workspaces see coverage for the version they actually enforce.
- Capability upgrades require explicit metadata and test changes.

### Negative

- Adding or changing a rule requires maintaining enforcement metadata.
- Pack publication can fail on schema or evidence drift.
- Legacy custom rules remain conservatively described until explicitly
  upgraded.

## Implementation evidence

- `apps/api/app/modules/guard/skill_packs/*.json`
- `apps/api/app/modules/guard/enforcement.py`
- `apps/api/app/modules/guard/policy_engine.py`
- `apps/api/scripts/seed_skill_packs.py`
- `apps/api/scripts/generate_guard_enforcement_coverage.py`
- `apps/api/tests/test_guard_enforcement_coverage.py`

## Follow-up triggers

Revisit the contract version when a new enforcement surface, matcher family, or
evidence type cannot be represented without changing existing field semantics.
