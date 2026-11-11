"""`conduct audit verify <export.ndjson>` — offline hash-chain check for audit exports (#2385, #2421).

Signed chain-head checkpoints (#2524 item 2): an export ends with an
``{"kind": "audit_checkpoint", checkpoint, keys}`` trailer. The signature is checked
(``audit_checkpoint.py``) and the export must reach the checkpoint's head and row_count,
which detects deletion of the chain's tail. Use ``--keys`` with the well-known endpoint
for keys that do not come from the export.

Each row is verified under its own ``hash_version`` (absent means 1). The API
writes the same hashes (``apps/api/app/modules/guard/audit_chain.py``)::

    v1: sha256(f"{ts}|{tool_call or ''}|{decision}|{previous_hash}")
    v2: sha256(canonical_json(every stored field except entry_hash and
               archive_segment_id) + previous_hash)

v1 ``ts`` is the exported ISO-8601 string verbatim. v2 canonical JSON is sorted
keys, no whitespace, UTF-8, timestamps as ``YYYY-MM-DDTHH:MM:SS.ffffffZ`` (UTC),
values normalised by column type. Genesis ``previous_hash`` is ``""``. Rows with
no ``entry_hash`` are not part of the chain and are skipped. An export that
starts mid-chain is anchored on its first row's ``previous_hash``. A v1 -> v2
boundary links like any other row.

A row whose payload was archived (``archive_segment_id`` set and all of
``input_summary``/``result_summary``/``blast_radius`` null) cannot be rehashed
offline; its linkage is still checked and it is counted in ``linkage_only``.

Forks. Before #2518 (merged 2026-11-04T01:10:20Z) concurrent appends could make
two rows share one ``previous_hash`` while every ``entry_hash`` is individually
correct. A row that links to a hash an earlier row already claimed, has a valid
own hash, and where both rows predate that instant is reported as a *known append
race* (``known_append_races``), not as tampering. Anything else that fails to link
is BROKEN. The cutoff is a constant so the API and this verifier agree.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

_REQUIRED = ("id", "ts", "decision", "entry_hash")

# Must match apps/api/app/modules/guard/audit_chain.py (pinned by tests on both sides).
_TS_FIELDS = ("ts", "accepted_at", "finalized_at", "lease_expires_at")
_UUID_FIELDS = ("id", "workspace_id", "session_id", "request_id", "agent_identity_id")
_INT_FIELDS = ("tokens_before", "tokens_after", "tokens_saved", "duration_ms",
               "defense_score", "hash_version")
_FLOAT_FIELDS = ("cost_usd_before", "cost_usd_after")
_JSON_FIELDS = ("blast_radius", "evaluated_rules", "routing_meta")
_TEXT_FIELDS = (
    "clerk_user_id", "user_email", "ai_tool", "tool_call", "source", "provider", "model",
    "input_summary", "decision", "rule_id", "rule_message", "tool_use_id", "hook_session_id",
    "conductai_run_id", "conductai_workflow", "conductai_workflow_id", "os_info", "hostname",
    "execution_status", "result_summary", "previous_hash", "policy_hash", "goal_id",
    "goal_name", "share_token_hash", "route", "lifecycle_state",
    # Track B (#2545, flight-recorder usage provenance): hashed from day one so the
    # chain covers them the moment the columns exist; NULL (absent) until then.
    "usage_source", "usage_status",
)
HASHED_FIELDS = tuple(sorted(
    _TS_FIELDS + _UUID_FIELDS + _INT_FIELDS + _FLOAT_FIELDS + _JSON_FIELDS + _TEXT_FIELDS))
_PAYLOAD_FIELDS = ("input_summary", "result_summary", "blast_radius")
# Must match audit_chain.APPEND_RACE_FIXED_AT in the API.
APPEND_RACE_FIXED_AT = "2026-11-04T01:10:20.000000Z"
_FORK_WINDOW = 256


def compute_entry_hash(ts: str, tool_call: str | None, decision: str, previous_hash: str | None) -> str:
    """v1 hash."""
    return hashlib.sha256(f"{ts}|{tool_call or ''}|{decision}|{previous_hash or ''}".encode()).hexdigest()


def _format_ts(value) -> str:
    dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _uuid(value) -> str:
    try:
        return str(UUID(str(value)))
    except ValueError:
        return str(value)


def _normalise(name: str, value):
    if value is None:
        return None
    if name in _TS_FIELDS:
        return _format_ts(value)
    if name in _UUID_FIELDS:
        return _uuid(value)
    if name in _INT_FIELDS:
        return int(value)
    if name in _FLOAT_FIELDS:
        return float(value)
    if name in _JSON_FIELDS:
        return value
    return value if isinstance(value, str) else str(value)


def compute_entry_hash_v2(rec: dict, previous_hash: str) -> str:
    """v2 hash. Raises KeyError(<names>) if the export lacks a hashed field."""
    missing = [n for n in HASHED_FIELDS if n not in rec]
    if missing:
        raise KeyError(", ".join(missing))
    record = {n: _normalise(n, rec[n]) for n in HASHED_FIELDS}
    record["previous_hash"] = previous_hash or ""
    body = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256((body + (previous_hash or "")).encode("utf-8")).hexdigest()


def _is_archived(rec: dict) -> bool:
    return bool(rec.get("archive_segment_id")) and all(rec.get(f) is None for f in _PAYLOAD_FIELDS)


def verify_lines(lines, *, allow_gaps: bool = False, checkpoint=None, keys=None,
                 require_checkpoint: bool = False, bundled_keys=None) -> dict:
    """Walk NDJSON lines. Returns {ok, rows, chained, anchor, versions, linkage_only,
    known_append_races, checkpoint, broken}; ``broken`` is the first failure.

    A signed chain-head checkpoint (export trailer, or ``checkpoint``) is verified
    after the chain walk: signature, then that the export reaches its head and
    row_count. ``keys`` (key_id -> {alg, public_key}) are the independently
    obtained verification keys; without them the keys bundled with the
    checkpoint are used and reported as untrusted.
    """
    from conduct_cli import audit_checkpoint as _checkpoint

    previous: str | None = None
    trailer = None  # (line_no, record) of the export's checkpoint trailer
    by_hash: dict = {}  # entry_hash -> chain position (None when unknown)
    first_pos = last_pos = None
    anchor = None
    rows = chained = linkage_only = 0
    versions: dict[int, int] = {}
    races: list[dict] = []
    children: dict[str, tuple[str, str]] = {}  # previous_hash -> (id, ts) of first child

    def broken(line_no, rec, reason, expected=None, actual=None):
        return {"ok": False, "rows": rows, "chained": chained, "anchor": anchor,
                "versions": versions, "linkage_only": linkage_only, "known_append_races": races,
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
        if rec.get("kind") == _checkpoint.TRAILER_KIND and isinstance(rec.get("checkpoint"), dict):
            rows -= 1  # trailer, not an event
            trailer = (line_no, rec)
            continue
        if not rec.get("entry_hash"):
            continue  # not chained
        missing = [k for k in _REQUIRED if k not in rec]
        if missing:
            return broken(line_no, rec, f"missing fields: {', '.join(missing)}")
        prev = rec.get("previous_hash") or ""
        try:
            version = int(rec.get("hash_version") or 1)
        except (TypeError, ValueError):
            return broken(line_no, rec, f"invalid hash_version: {rec.get('hash_version')!r}")
        if version == 1:
            expected = compute_entry_hash(rec["ts"], rec.get("tool_call"), rec["decision"], prev)
        elif version == 2:
            if _is_archived(rec):
                expected = None  # payload archived: cannot rehash; linkage is checked below
                linkage_only += 1
            else:
                try:
                    expected = compute_entry_hash_v2(rec, prev)
                except KeyError as exc:
                    return broken(line_no, rec, f"export lacks hashed field(s): {exc.args[0]}")
                except (ValueError, TypeError) as exc:
                    return broken(line_no, rec, f"unparseable field: {exc}")
        else:
            return broken(line_no, rec, f"unknown hash_version {version}")
        if expected is not None and rec["entry_hash"] != expected:
            return broken(line_no, rec, "entry_hash does not match recomputed hash", expected, rec["entry_hash"])
        try:
            ts = _format_ts(rec["ts"])
        except (ValueError, TypeError) as exc:
            return broken(line_no, rec, f"unparseable ts: {exc}")
        if previous is None:
            anchor = prev
        elif not allow_gaps and prev != previous:
            sibling = children.get(prev)
            if sibling is None or ts >= APPEND_RACE_FIXED_AT or sibling[1] >= APPEND_RACE_FIXED_AT:
                return broken(line_no, rec, "previous_hash does not match prior row's entry_hash", previous, prev)
            races.append({"line": line_no, "id": rec.get("id"), "sibling_id": sibling[0], "ts": ts})
        children.setdefault(prev, (str(rec.get("id")), ts))
        if len(children) > _FORK_WINDOW:
            del children[next(iter(children))]
        versions[version] = versions.get(version, 0) + 1
        position = rec.get("chain_position")
        if not isinstance(position, int) or isinstance(position, bool):
            position = chained + 1 if (anchor == "" and not allow_gaps) else None
        by_hash[rec["entry_hash"]] = position
        if position is not None:
            first_pos = position if first_pos is None else first_pos
            last_pos = position
        previous = rec["entry_hash"]
        chained += 1
    result = {"ok": True, "rows": rows, "chained": chained, "anchor": anchor, "versions": versions,
              "linkage_only": linkage_only, "known_append_races": races, "broken": None,
              "checkpoint": {"status": "none", "reason": None, "trusted_keys": False}}
    cp, bundled = checkpoint, {}
    cp_line = 0
    if cp is None and trailer is not None:
        cp_line, cp, bundled = trailer[0], trailer[1]["checkpoint"], trailer[1].get("keys") or {}
    if cp is None:
        if require_checkpoint:
            result.update(ok=False, broken={"line": 0, "id": None, "expected": None, "actual": None,
                          "reason": "no signed checkpoint in the export (--require-checkpoint)"})
        return result
    use_keys = keys if keys is not None else (bundled or bundled_keys or {})
    result["checkpoint"] = {"status": "invalid", "reason": None, "trusted_keys": keys is not None,
                            "row_count": cp.get("row_count"), "key_id": cp.get("key_id"), "alg": cp.get("alg"),
                            "ts": cp.get("ts")}
    try:
        outcome = _checkpoint.check(cp, use_keys, by_hash=by_hash, first_pos=first_pos, last_pos=last_pos)
        result["checkpoint"].update(outcome)
    except _checkpoint.CheckpointError as exc:
        result["checkpoint"].update(status=exc.status, reason=exc.reason)
        if not (exc.status == "unverifiable" and allow_gaps):
            result.update(ok=False, broken={"line": cp_line, "id": None, "expected": None, "actual": None,
                                            "reason": "checkpoint: " + exc.reason})
    return result


def cmd_audit(args) -> None:
    from conduct_cli import audit_checkpoint as _checkpoint

    if getattr(args, "audit_command", None) == "feed":
        from conduct_cli.commands.audit_feed import cmd_audit_feed
        cmd_audit_feed(args)
        return
    if getattr(args, "audit_command", None) != "verify":
        print("Usage: conduct audit verify <export.ndjson> [--allow-gaps]\n"
              "       conduct audit feed [--since ISO] [--follow] [--output FILE]", file=sys.stderr)
        sys.exit(1)
    try:
        with Path(args.file).open(encoding="utf-8") as fh:
            keys, cp, bundled_keys = None, None, None
            if getattr(args, "keys", None):
                keys = _checkpoint.load_keys(args.keys)
            if getattr(args, "checkpoint", None):
                cp, bundled_keys = _checkpoint.load_bundle(args.checkpoint)
            result = verify_lines(fh, allow_gaps=args.allow_gaps, checkpoint=cp, keys=keys,
                                  bundled_keys=bundled_keys,
                                  require_checkpoint=getattr(args, "require_checkpoint", False))
    except OSError as exc:
        print(f"Cannot read {args.file}: {exc}", file=sys.stderr)
        sys.exit(1)
    except (_checkpoint.CheckpointError, ValueError) as exc:
        print(f"Cannot load checkpoint/keys: {getattr(exc, 'reason', exc)}", file=sys.stderr)
        sys.exit(1)
    if result["ok"]:
        start = "genesis" if result["anchor"] == "" else f"mid-chain (anchor {str(result['anchor'])[:12]}...)"
        mix = ", ".join(f"v{v}: {n}" for v, n in sorted(result["versions"].items())) or "none"
        print(f"OK: {result['rows']} rows, {result['chained']} chained ({mix}), chain verified from {start}")
        if result["linkage_only"]:
            print(f"Note: {result['linkage_only']} archived row(s) verified by linkage only "
                  "(payload fields were archived and cannot be rehashed offline).")
        _print_checkpoint(result["checkpoint"], bundled_only=not result["checkpoint"].get("trusted_keys"))
        if result["known_append_races"]:
            ids = ", ".join(str(r["id"]) for r in result["known_append_races"][:10])
            print(f"Note: {len(result['known_append_races'])} known append race fork(s) from before "
                  f"{APPEND_RACE_FIXED_AT[:10]} (concurrent writers linked to the same row; every entry "
                  f"hash is valid; not tampering): {ids}")
        return
    b = result["broken"]
    print(f"BROKEN at line {b['line']} (id {b['id']}): {b['reason']}", file=sys.stderr)
    if b["expected"] is not None:
        print(f"  expected: {b['expected']}\n  actual:   {b['actual']}", file=sys.stderr)
    sys.exit(1)


def _print_checkpoint(cp: dict, *, bundled_only: bool) -> None:
    status = cp.get("status")
    if status == "none":
        print("Note: no signed checkpoint in this export, so truncation of the chain tail cannot be "
              "detected. Pass --require-checkpoint to fail instead.")
    elif status == "not_covered":
        print(f"Note: checkpoint not applicable: {cp.get('reason')}")
    elif status == "valid":
        print(f"Checkpoint OK: signed {cp.get('alg')} head at row {cp.get('row_count')} "
              f"({cp.get('ts')}, key {cp.get('key_id')}) is reached by this export.")
    if status in ("valid", "not_covered") and bundled_only:
        print("Warning: verification keys came from the export itself. For independent trust pass "
              "--keys https://<api-host>/.well-known/conduct-audit-keys")


def register_audit(sub) -> None:
    audit_p = sub.add_parser("audit", help="Audit log tools (export verification, SIEM feed)")
    audit_sub = audit_p.add_subparsers(dest="audit_command")
    v = audit_sub.add_parser("verify", help="Verify the hash chain of an NDJSON audit export")
    v.add_argument("file", help="NDJSON file from `GET /guard/events/export` / Lens")
    v.add_argument("--allow-gaps", action="store_true",
                   help="Only recompute each row's hash; skip linkage (for decision/tool-filtered exports)")
    v.add_argument("--keys", help="Verification keys: file or https URL (the API's "
                   "/.well-known/conduct-audit-keys). Without it, keys bundled with the checkpoint are "
                   "used and reported as untrusted")
    v.add_argument("--checkpoint", help="JSON file holding a checkpoint (an audit feed page or "
                   "{checkpoint, keys}) to check instead of the export's trailer")
    v.add_argument("--require-checkpoint", action="store_true",
                   help="Fail when the export carries no signed checkpoint")
    from conduct_cli.commands.audit_feed import register_feed
    register_feed(audit_sub)
