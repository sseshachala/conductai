# ACD-0002: Local Policy Evaluation with Bounded Sync

**Status:** Accepted  
**Date:** 2026-07-01  
**Patent claim:** Cached policy with bounded freshness; fail-closed enforcement

---

## Decision

Policy is evaluated locally from a cached JSON file (`~/.conduct/policy.json`). The policy syncs from the server at most once per 60 seconds, or instantly via a local daemon. Evaluation is a pure function — no network call per tool use. If the policy file is absent and `fail_mode=fail_closed`, all tool calls are blocked.

```
Tool call fires
      │
      ▼
check_policy(tool_name, tool_input)   ← pure function, reads local file
      │
      ├─ policy.json exists → evaluate rules → decision in < 1ms
      │
      └─ policy.json absent + fail_closed → block immediately
            (no network call, no fallback, hard stop)

Sync runs separately, at most once per 60s:
      server version == local version → no-op
      server version differs → verify HMAC → write file
```

---

## Context

The hook fires on every tool call — potentially hundreds per session. A network round-trip per call would add 50-200ms latency to every Bash, Read, and Write operation. This is unacceptable for interactive development.

At the same time, policies must stay fresh. A security team changing a rule should see enforcement within minutes, not hours.

The 60-second sync window provides a bounded staleness guarantee: policies are at most 60 seconds stale at any point. This is acceptable for governance — no security rule changes are so time-critical that a 60-second window is dangerous.

---

## Alternatives Rejected

**Per-call remote evaluation**: Unacceptable latency. 100-200ms per tool call means a 50-tool session adds 5-10 seconds of overhead. Fails completely if the server is unreachable.

**Long-lived cache (hours)**: Reduces sync load but creates a large window where a disabled rule continues to fire, or an enabled block rule isn't enforced. Unacceptable for security policy.

**No cache, always-online**: Any server outage disables enforcement. This is fail-open by default — the opposite of what enterprise security requires.

**Policy pushed via webhook**: Eliminates polling but requires the client to be reachable (no NAT/firewall issues in dev environments). Pull-based sync works everywhere.

---

## Consequences

- Policy changes take up to 60 seconds to reach all developers — must be communicated in team policy update flow
- HMAC signature on the policy JSON prevents a compromised server from pushing a malicious policy that disables rules without a valid signing key
- `fail_mode=fail_closed` is the default for new installations — agents cannot run without a synced policy
- Fail-closed with no local cache is a hard block, not a soft warning — this is intentional for air-gapped or offline scenarios
- Downgrading `fail_closed` → `fail_open` requires a signed `fail_mode_downgrade_token` in the policy, preventing silent relaxation of security posture
