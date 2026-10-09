"""`conduct audit verify <export.ndjson>` — offline hash-chain check for audit exports (#2385).

Recomputes the chain exactly as the API writes it
(``apps/api/app/modules/guard/models/__init__.py::chain_hash_for_insert``)::

    entry_hash = sha256(f"{ts}|{tool_call or ''}|{decision}|{previous_hash}").hexdigest()

``ts`` is the exported ISO-8601 string verbatim (the API emits ``ts.isoformat()``,
the same string it hashed). Genesis ``previous_hash`` is ``""``. Rows with no
``entry_hash`` are not part of the chain and are skipped. An export that starts
mid-chain is anchored on its first row's ``previous_hash``.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_REQUIRED = ("id", "ts", "decision", "entry_hash")


def compute_entry_hash(ts: str, tool_call: str | None, decision: str, previous_hash: str | None) -> str:
    return hashlib.sha256(f"{ts}|{tool_call or ''}|{decision}|{previous_hash or ''}".encode()).hexdigest()


def verify_lines(lines, *, allow_gaps: bool = False) -> dict:
    """Walk NDJSON lines. Returns {ok, rows, chained, anchor, broken}; ``broken`` is the first failure."""
    previous: str | None = None
    anchor = None
    rows = chained = 0

    def broken(line_no, rec, reason, expected=None, actual=None):
        return {"ok": False, "rows": rows, "chained": chained, "anchor": anchor,
                "broken": {"line": line_no, "id": (rec or {}).get("id"), "reason": reason,
                           "expected": expected, "actual": actual}}

    for line_no, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        rows += 1
        try:
            rec = json.loads(raw)
            if not isinstance(rec, dict):
                raise ValueError("not an object")
        except ValueError as exc:
            return broken(line_no, None, f"invalid JSON: {exc}")
        if not rec.get("entry_hash"):
            continue  # not chained
        missing = [k for k in _REQUIRED if k not in rec]
        if missing:
            return broken(line_no, rec, f"missing fields: {', '.join(missing)}")
        prev = rec.get("previous_hash") or ""
        if previous is None:
            anchor = prev
        elif not allow_gaps and prev != previous:
            return broken(line_no, rec, "previous_hash does not match prior row's entry_hash", previous, prev)
        expected = compute_entry_hash(rec["ts"], rec.get("tool_call"), rec["decision"], prev)
        if rec["entry_hash"] != expected:
            return broken(line_no, rec, "entry_hash does not match recomputed hash", expected, rec["entry_hash"])
        previous = rec["entry_hash"]
        chained += 1
    return {"ok": True, "rows": rows, "chained": chained, "anchor": anchor, "broken": None}


def cmd_audit(args) -> None:
    if getattr(args, "audit_command", None) != "verify":
        print("Usage: conduct audit verify <export.ndjson> [--allow-gaps]", file=sys.stderr)
        sys.exit(1)
    try:
        with Path(args.file).open(encoding="utf-8") as fh:
            result = verify_lines(fh, allow_gaps=args.allow_gaps)
    except OSError as exc:
        print(f"Cannot read {args.file}: {exc}", file=sys.stderr)
        sys.exit(1)
    if result["ok"]:
        start = "genesis" if result["anchor"] == "" else f"mid-chain (anchor {str(result['anchor'])[:12]}...)"
        print(f"OK: {result['rows']} rows, {result['chained']} chained, chain verified from {start}")
        return
    b = result["broken"]
    print(f"BROKEN at line {b['line']} (id {b['id']}): {b['reason']}", file=sys.stderr)
    if b["expected"] is not None:
        print(f"  expected: {b['expected']}\n  actual:   {b['actual']}", file=sys.stderr)
    sys.exit(1)


def register_audit(sub) -> None:
    audit_p = sub.add_parser("audit", help="Audit log tools (offline export verification)")
    audit_sub = audit_p.add_subparsers(dest="audit_command")
    v = audit_sub.add_parser("verify", help="Verify the hash chain of an NDJSON audit export")
    v.add_argument("file", help="NDJSON file from `GET /guard/events/export` / Lens")
    v.add_argument("--allow-gaps", action="store_true",
                   help="Only recompute each row's hash; skip linkage (for decision/tool-filtered exports)")
