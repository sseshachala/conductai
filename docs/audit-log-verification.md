# Audit log verification

## Purpose

Conduct audit entries are hash-chained to make tampering detectable.
Each entry links to the prior entry using `prev_hash` and stores its own `entry_hash`.

## Hash-chain invariants

For each workspace sequence ordered by timestamp/insertion order:

1. `prev_hash` of the first entry is empty (or null-equivalent by exporter convention).
2. For every next entry `i`, `prev_hash[i] == entry_hash[i-1]`.
3. `entry_hash[i] == SHA256("{ts_iso}|{tool_call}|{decision}|{prev_hash[i]}")`.
4. Any missing/reordered/edited row breaks invariant 2 or 3.

## Hash versions (chain v2)

Rows carry `hash_version`. Invariant 3 above is **v1** (rows written before v2;
never rehashed). New rows are **v2**, which covers the whole record:

```text
entry_hash = SHA256(canonical_json(record) + prev_hash)
```

`record` is every stored audit field except `entry_hash` and `archive_segment_id`
(a retention pointer set when the payload is archived). Canonical JSON: sorted
keys, no whitespace, UTF-8, every timestamp as `YYYY-MM-DDTHH:MM:SS.ffffffZ`
(UTC), values normalised by column type (UUIDs lower-case, integers as ints,
floats as floats, absent = null). The v1 -> v2 boundary row links to the last v1
`entry_hash` like any other. Exports and the SIEM feed carry `hash_version` and
every hashed field; `conduct audit verify` verifies each row under its own
version. A row whose payload was archived (`archive_segment_id` set, payload
fields null) is verified by linkage only.

## Hash version 3 and what is hashed

New rows are **v3**: v2 with `share_token_hash` removed from the record. Sharing a
block receipt writes that column on an already-sealed row, so covering it would
make every shared receipt fail verification; the value is a hash of a capability
token, not audit content. v1 and v2 rows are never rehashed and verify under their
own version (`conduct audit verify` and `verify_audit_history` dispatch on
`hash_version`). The only stored columns outside the v3 hash are `entry_hash`,
`archive_segment_id` and `share_token_hash`.

## Every writer is chained

All Guard audit rows are appended through `chain_begin` / `chain_seal` /
`chain_seal_values` in `apps/api/app/modules/guard/models/__init__.py` (per-workspace
advisory lock, monotonic `ts`, full-record hash): hook and MCP events, approvals,
policy and budget edits, SSO logins, ingested events, the verify battery, runtime
(brain/guard block) verdicts, `conduct guard sync` local-audit findings (these rows are
now append-only; a re-sync skips findings already recorded instead of deleting
them) and gateway decisions. There are no excluded writers.
`tests/guard/test_audit_writers_chained.py` scans `app/` and fails if any code path
inserts a `GuardAuditEvent` or raw `INSERT INTO guard_audit_events` without the chain
helpers, or UPDATEs/DELETEs audit rows outside a reviewed allowlist.

### Gateway two-phase rows

A durable gateway request writes an `accepted` row before inference and updates it
afterwards, so its stored fields change. It is therefore **sealed once, at the end**:

- `insert_accepted` writes the row with `entry_hash` NULL. Unchained rows are skipped
  by both verifiers, exactly like pre-chain rows.
- `finalize` takes the workspace chain lock, then in one transaction writes the final
  fields together with a new `ts`, `previous_hash` and `hash_version = 3`, and sets
  `entry_hash` from the stored values. `ts` is the seal time so `(ts, id)` order equals
  chain order; `accepted_at` keeps the request start and `finalized_at` the outcome time.
- A row that never finalizes (crash, timeout) is terminalized by the reconciler
  (`orphaned`, `decision = error`) and sealed the same way, one transaction per row,
  same lock order (chain lock, then row).
- After sealing nothing mutates a hashed field. A late `finalize` on a sealed row
  matches zero rows. `renew_lease` only touches an unsealed `accepted` row.

Consequence: while a request is in flight its row is not yet covered by the chain
(typically seconds, bounded by the lease). A row that is `accepted` past its lease is
visible in the audit view until the reconciler seals it.

## Known append-race forks (before 2026-11-04)

Before #2518 (merged 2026-11-04T01:10:20Z) concurrent appends were not
serialised, so two rows could share one `previous_hash` (a fork) while every
`entry_hash` is individually correct. The verifiers (`verify_audit_history`,
`conduct audit verify`) classify such a fork as a **known append race** when both
rows' own hashes are valid, the shared `previous_hash` belongs to an earlier row,
and both rows are older than that instant. They are reported separately
(`known_append_races`) and do not fail verification. The cutoff is a fixed
constant so the server and an offline verifier agree. A fork at or after the
cutoff, a fork with an invalid row hash, or a link to a hash no earlier row
holds is reported as broken.

## Chain complete from

Gateway audit rows written before #2518 carry no chain fields and cannot be
backfilled. `chain_complete_from` is the timestamp of the first chained row
after the last unchained row older than the #2518 merge instant (the first
chained row when there is no such gap). It is derived from the rows, with no
schema change, and returned by `GET /guard/verify/chain`,
`GET /guard/events/audit/verify`, the Audit page feed status
(`GET /workspaces/{id}/audit-log/feed-status`, shown on the SIEM card) and the
`get_audit_feed_status` tool. History before it is not covered by the chain.

## Independent verification procedure

1. Export audit records for one workspace in deterministic order.
2. Ensure export includes at least: `ts`, `tool_call`, `decision`, `prev_hash`, `entry_hash`.
3. Recompute each row hash in order using the canonical string format.
4. Compare recomputed hash to stored `entry_hash`.
5. Validate each row’s `prev_hash` points to prior row’s stored `entry_hash`.
6. Report first mismatch index and stop, or report full pass.

## Pseudocode

```text
prev = ""
for row in rows_sorted:
  assert row.prev_hash == prev
  expected = sha256(f"{row.ts}|{row.tool_call or ''}|{row.decision}|{prev}")
  assert row.entry_hash == expected
  prev = row.entry_hash
```

## Runnable Python example

The script below verifies an exported JSON array file.

Input schema per row:

```json
{
  "ts": "2026-08-27T13:10:00+00:00",
  "tool_call": "bash",
  "decision": "blocked",
  "prev_hash": "...",
  "entry_hash": "..."
}
```

Save as `/tmp/verify_conduct_chain.py` and run:

```bash
python /tmp/verify_conduct_chain.py /path/to/export.json
```

```python
#!/usr/bin/env python3
import hashlib
import json
import sys
from pathlib import Path
from typing import Optional


def row_hash(ts: str, tool_call: Optional[str], decision: str, prev_hash: str) -> str:
    payload = f"{ts}|{tool_call or ''}|{decision}|{prev_hash}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify(path: Path) -> int:
    rows = json.loads(path.read_text())
    prev = ""

    for i, row in enumerate(rows):
        ts = row["ts"]
        tool_call = row.get("tool_call")
        decision = row["decision"]
        stored_prev = row.get("prev_hash") or ""
        stored_entry = row.get("entry_hash") or ""

        if stored_prev != prev:
            print(f"FAIL prev_hash mismatch at index={i}: expected={prev} actual={stored_prev}")
            return 1

        expected_entry = row_hash(ts, tool_call, decision, stored_prev)
        if stored_entry != expected_entry:
            print(
                f"FAIL entry_hash mismatch at index={i}: expected={expected_entry} actual={stored_entry}"
            )
            return 1

        prev = stored_entry

    print(f"OK chain verified for {len(rows)} rows")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: verify_conduct_chain.py /path/to/export.json")
        raise SystemExit(2)
    raise SystemExit(verify(Path(sys.argv[1])))
```

## Verification failure meaning

A failure indicates one of:

- Log tampering (edit/delete/reorder).
- Incomplete export window or wrong ordering.
- Schema/format mismatch in exported timestamps or fields.
- Migration/import bug writing chain fields.

## Incident response when verification fails

1. Preserve the failing export and verifier output.
2. Freeze retention/cleanup jobs for the affected workspace.
3. Compare against a second source (database snapshot, backup export, or replica).
4. Identify first broken entry and blast radius window.
5. Rotate sensitive credentials if integrity cannot be re-established quickly.
6. Open a security incident and notify workspace owners with timeline + impact.
7. After remediation, re-run verification and attach evidence to incident closure.
