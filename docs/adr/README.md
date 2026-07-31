# Architecture Decision Records

This directory records load-bearing architecture decisions for Conduct.

ADRs explain why a durable choice was made, what alternatives were rejected,
and what consequences the team accepts. They are not feature specifications,
implementation plans, or a history of every past decision.

## When to write an ADR

Write an ADR when a change establishes or materially changes:

- a security or trust boundary;
- a persistent data or policy contract;
- a runtime, compiler, or integration architecture;
- a cross-component failure-mode policy;
- a choice that would be expensive or risky to reverse.

Do not create ADRs for routine implementation choices. Do not backfill old
decisions unless they are being reconsidered or remain important to current
work.

## Process

1. Copy [`ADR-0000-template.md`](ADR-0000-template.md).
2. Use the next sequential number and a short kebab-case title.
3. Open the ADR with the implementation change it governs.
4. Set the status to `proposed` while the decision is under review.
5. Change the status to `accepted` when the implementation is approved.
6. Never rewrite the outcome of an accepted ADR. Add an amendment or a new ADR
   that supersedes it.

Documentation and implementation should land in the same pull request.

## Status values

- `proposed`: under discussion;
- `accepted`: current architecture;
- `deprecated`: retained for history but no longer recommended;
- `superseded`: replaced by another ADR.

## Index

| ADR | Decision | Status |
|---|---|---|
| [ADR-0001](ADR-0001-guard-enforcement-surfaces-and-trust-boundaries.md) | Guard enforcement surfaces and trust boundaries | Accepted |
| [ADR-0002](ADR-0002-policy-pack-schema-and-applicability-contract.md) | Policy-pack schema and applicability contract | Accepted |
| [ADR-0003](ADR-0003-fail-open-versus-fail-closed-semantics.md) | Fail-open versus fail-closed semantics | Accepted |
| [ADR-0004](ADR-0004-playbook-dsl-versus-external-orchestration-frameworks.md) | Playbook DSL versus external orchestration frameworks | Accepted |
