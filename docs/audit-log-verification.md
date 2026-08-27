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


def row_hash(ts: str, tool_call: str | None, decision: str, prev_hash: str) -> str:
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
