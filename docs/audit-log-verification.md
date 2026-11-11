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

## Signed chain-head checkpoints (tail truncation)

A hash chain alone cannot show that rows were deleted from its **end**: every remaining
row still links and hashes correctly. Checkpoints close that gap. Each hour (per workspace
with new rows) the worker signs the chain head:

```json
{"workspace_id": "...", "ts": "2026-11-11T12:00:00.000000Z", "head_entry_hash": "...",
 "row_count": 5, "hash_version": 2, "key_id": "a050837d...", "alg": "Ed25519"}
```

The signature covers that object as canonical JSON (sorted keys, no whitespace, UTF-8) and
is stored base64 beside it. `row_count` counts rows that have chain fields
(`entry_hash IS NOT NULL`), so archival does not change it. Head and count are read under the
same per-workspace lock that serialises appends. Workspaces with no new rows since the last
checkpoint are skipped. Checkpoints are kept 1 year (the newest per workspace is always kept).

**Algorithms.** `alg` is part of the signed payload.

| `alg` | Backend |
|---|---|
| `Ed25519` | AWS KMS `ECC_NIST_EDWARDS25519` (`ED25519_SHA_512`, which is pure Ed25519), or a key held in settings (on-prem/dev) |
| `ECDSA-P256-SHA256` | AWS KMS `ECC_NIST_P256` (`ECDSA_SHA_256`, DER signature) |

**Public keys.** `GET /.well-known/conduct-audit-keys` (no authentication; public keys only)
returns `{"keys": {key_id: {"alg", "public_key" (base64 SPKI DER), "created_at"}}}`. Old keys
are never removed, so checkpoints signed before a rotation stay verifiable. Keys are also
bundled with every checkpoint: on each `get_audit_feed` page (`checkpoint`, `audit_keys`) and
as the last NDJSON line of an unfiltered, uncapped export:

```json
{"kind":"audit_checkpoint","checkpoint":{...},"keys":{...}}
```

**Verify.** `conduct audit verify export.ndjson --keys https://<api-host>/.well-known/conduct-audit-keys`
checks the signature, then that the export reaches the checkpoint: the row at chain position
`row_count` must have `head_entry_hash`. An export that ends earlier fails with
`export ends before the checkpoint head`. Keys taken from the export itself are reported as
untrusted: whoever can rewrite the export can also swap the bundled key, so pin the keys from the
endpoint (or a copy you saved earlier). `--checkpoint page.json` checks a checkpoint from a feed
page against an export, and `--require-checkpoint` fails when none is present. Filtered or
capped exports carry no checkpoint. `verify` needs the `cryptography` Python package, which
`conduct-cli` now depends on.

Server side, `verify_audit_history` also checks the newest checkpoint: signature, that the
signed head row still exists and that the chain has at least `row_count` rows. Failures set
`valid=false` with `broken_at` of `checkpoint_truncated`, `checkpoint_invalid_signature` or
`checkpoint_unknown_key`.

**What this does and does not prove.** An attacker who can delete tail rows and also reach the
signing key can sign a new checkpoint for the shortened chain. With a settings-held key that is
anyone who can read the app's configuration. With a KMS sign-only key, the operator can still call
Sign through the application role, so the stronger guarantee is a restricted KMS key policy and
CloudTrail for `kms:Sign`; checkpoints you have already downloaded cannot be rewritten. Keep the
latest checkpoint with each export you archive.

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
