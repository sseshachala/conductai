# ACD-0003: Hash-Chained Append-Only Audit Log

**Status:** Accepted  
**Date:** 2026-07-01  
**Patent claim:** Tamper-evident audit trail via hash chaining

---

## Decision

Every Guard audit event carries a `policy_hash` field: a SHA-256 hash of the current event's key fields concatenated with the hash of the previous event. This creates a chain where any modification to a past event invalidates all subsequent hashes — making tampering detectable without an external ledger.

```
Event N-1:  hash = SHA256(ts | tool | decision | hash[N-2])
                                                      ↑
Event N:    hash = SHA256(ts | tool | decision | hash[N-1])
                                                      ↑
Event N+1:  hash = SHA256(ts | tool | decision | hash[N])
```

Verify integrity: recompute the chain from event 1. Any gap or mismatch identifies the tampered record and everything after it.

---

## Context

Enterprise compliance requirements (SOC 2, ISO 27001, financial services) treat audit logs as evidence. An audit log that can be quietly edited — by an insider, a compromised admin account, or a misconfigured database migration — has no evidentiary value.

Traditional approaches rely on write-once storage (S3 Object Lock, WORM drives) or external append-only ledgers (blockchain, QLDB). Both add infrastructure cost and operational complexity.

Hash chaining achieves tamper-evidence with zero additional infrastructure. The chain lives in the existing `guard_audit_events` table. Verification is a single SQL scan.

---

## Alternatives Rejected

**Write-once cloud storage (S3 Object Lock)**: Adds AWS dependency, cost, and operational complexity. Doesn't work for self-hosted deployments. Still vulnerable to insider deletion before the lock period applies.

**External blockchain ledger**: High overhead, external dependency, near-zero practical adoption in enterprise security tooling. Proof-of-concept credibility without operational credibility.

**Signed events only (no chain)**: Each event carries its own HMAC signature — proves the event wasn't modified after creation, but doesn't prove no events were deleted from the middle of the sequence. A gap in the event sequence is undetectable.

**No tamper protection**: Acceptable for activity logs. Not acceptable for security enforcement logs that serve as evidence in incident investigations or compliance audits.

---

## Consequences

- Events must be written sequentially within a workspace — parallel writes require a serialization point (database lock or sequence number)
- `SELECT FOR UPDATE` on the most recent event row prevents race conditions between concurrent Guard events
- Verification requires a full table scan per workspace — acceptable for periodic audits, not per-request
- The chain does not prevent deletion of the entire log — protection against that requires backup policy, not hash chaining
- Policy version at decision time is included in each hash (`policy_hash` field) — links enforcement decisions to the exact policy version that produced them, enabling retrospective policy audits
