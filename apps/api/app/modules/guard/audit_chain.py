"""Guard audit hash chain: the single hashing implementation (pure, no DB).

Versions
--------
v1 (legacy, never written any more)::

    sha256(f"{ts.isoformat()}|{tool_call or ''}|{decision}|{previous_hash}")

v2 (every new row, ``hash_version = 2``)::

    entry_hash = sha256(canonical_json(record) + previous_hash)

``record`` holds every stored audit column except ``entry_hash`` and
``archive_segment_id`` (a retention pointer set after the fact, when the
payload is archived). Canonical JSON is sorted keys, no whitespace, UTF-8, with
every timestamp as ``YYYY-MM-DDTHH:MM:SS.ffffffZ`` (UTC). Values are
normalised by column type so the hash is identical whether it is computed from
an ORM object, a raw INSERT, a database row or an exported NDJSON record.

v1 rows are never rehashed. The first v2 row links to the last v1
``entry_hash`` like any other row.

``conduct audit verify`` (packages/conduct-cli) re-implements ``compute_v2``;
``tests/guard/test_audit_chain_v2.py`` pins both to the same vectors.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import UUID

HASH_VERSION = 2

TS_FIELDS = ("ts", "accepted_at", "finalized_at", "lease_expires_at")
UUID_FIELDS = ("id", "workspace_id", "session_id", "request_id", "agent_identity_id")
INT_FIELDS = ("tokens_before", "tokens_after", "tokens_saved", "duration_ms",
              "defense_score", "hash_version")
FLOAT_FIELDS = ("cost_usd_before", "cost_usd_after")
JSON_FIELDS = ("blast_radius", "evaluated_rules", "routing_meta")
TEXT_FIELDS = (
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
    TS_FIELDS + UUID_FIELDS + INT_FIELDS + FLOAT_FIELDS + JSON_FIELDS + TEXT_FIELDS))
# Stored columns deliberately outside the hash.
UNHASHED_FIELDS = ("entry_hash", "archive_segment_id")


def format_ts(value: datetime | str) -> str:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _uuid(value: Any) -> str:
    try:
        return str(UUID(str(value)))
    except ValueError:
        return str(value)  # agent_identity_id is free-form text on some rows


def _normalise(name: str, value: Any) -> Any:
    if value is None:
        return None
    if name in TS_FIELDS:
        return format_ts(value)
    if name in UUID_FIELDS:
        return _uuid(value)
    if name in INT_FIELDS:
        return int(value)
    if name in FLOAT_FIELDS:
        return float(value)
    if name in JSON_FIELDS:
        return json.loads(json.dumps(value))  # strict: unserialisable values must fail loudly
    return str(value) if not isinstance(value, str) else value


def canonical_record(values: Mapping[str, Any]) -> dict:
    """The exact mapping that is hashed. Absent keys count as NULL."""
    record = {name: _normalise(name, values.get(name)) for name in HASHED_FIELDS}
    record["previous_hash"] = record["previous_hash"] or ""
    return record


def canonical_json(values: Mapping[str, Any]) -> str:
    return json.dumps(canonical_record(values), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def compute_v2(values: Mapping[str, Any]) -> str:
    """v2 entry hash. ``values`` must carry ``previous_hash`` and ``hash_version``."""
    previous = values.get("previous_hash") or ""
    return hashlib.sha256((canonical_json(values) + previous).encode("utf-8")).hexdigest()


def compute_v1(ts: datetime | str, tool_call, decision: str, previous_hash: str | None) -> str:
    """Legacy hash. Verification only: nothing writes v1 any more."""
    ts_text = ts if isinstance(ts, str) else ts.isoformat()
    return hashlib.sha256(
        f"{ts_text}|{tool_call or ''}|{decision}|{previous_hash or ''}".encode()).hexdigest()


def hash_version_of(row: Mapping[str, Any]) -> int:
    return int(row.get("hash_version") or 1)


def expected_hash(row: Mapping[str, Any], previous: str) -> str:
    """Recompute ``row``'s entry hash under its own hash_version.

    Raises ValueError for an unknown version (treated as a broken chain).
    """
    version = hash_version_of(row)
    if version == 1:
        return compute_v1(row["ts"], row.get("tool_call"), row["decision"], previous)
    if version == 2:
        return compute_v2({**row, "previous_hash": previous})
    raise ValueError(f"unknown audit hash_version {version}")


# ── Walking a chain ────────────────────────────────────────────────────────────
#
# Before #2518 (merged 2026-11-04T01:10:20Z, d175b172) appends were not
# serialised, so two concurrent writers could read the same tail and both link
# to it: two rows share one ``previous_hash`` (a fork) while every entry_hash is
# individually correct. That is a known append race, not tampering. The cutoff
# is a constant, not derived from data, so the API and the offline CLI
# classify the same fork the same way (an export has no database to ask). A
# fork at or after the cutoff is never classified: the lock prevents it, so it
# is reported as broken. Rows between the merge and the production rollout are
# the conservative side: they alarm rather than pass.
APPEND_RACE_FIXED_AT = datetime(2026, 11, 4, 1, 10, 20, tzinfo=timezone.utc)
_APPEND_RACE_FIXED_AT_TS = format_ts(APPEND_RACE_FIXED_AT)
_FORK_WINDOW = 256  # forks are between concurrent (adjacent) writers; keep memory bounded


class ChainBroken(ValueError):
    """The chain is not intact at ``row``."""

    def __init__(self, reason: str, row: Mapping[str, Any] | None = None):
        super().__init__(reason)
        self.reason = reason
        self.row = row


class ChainWalker:
    """Verify rows fed in (ts, id) order; classify pre-#2518 forks as known append races.

    ``feed`` raises ``ChainBroken`` on the first row that is neither valid nor a
    known race. A row is a known append race when its own entry_hash is valid
    under its own ``previous_hash``, that ``previous_hash`` was already claimed by
    an earlier walked row (its sibling), and both rows predate #2518. The chain
    then continues from the later row, which is what the next writer linked to.
    """

    def __init__(self, previous: str = ""):
        self.previous = previous or ""
        self.chained = 0
        self.known_append_races: list[dict] = []
        self._children: dict[str, tuple[str, str]] = {}  # previous_hash -> (id, ts) of first child

    def feed(self, row: Mapping[str, Any]) -> None:
        if not row.get("entry_hash"):
            return  # not part of the chain
        stored_prev = row.get("previous_hash") or ""
        try:
            expected = expected_hash(row, stored_prev)
            ts = format_ts(row["ts"])
        except (ValueError, TypeError, KeyError) as exc:
            raise ChainBroken(f"unverifiable row: {exc}", row) from exc
        if row["entry_hash"] != expected:
            raise ChainBroken("entry_hash does not match recomputed hash", row)
        if stored_prev != self.previous:
            sibling = self._children.get(stored_prev)
            if sibling is None or ts >= _APPEND_RACE_FIXED_AT_TS or sibling[1] >= _APPEND_RACE_FIXED_AT_TS:
                raise ChainBroken("previous_hash does not match prior row's entry_hash", row)
            self.known_append_races.append({
                "id": str(row.get("id")), "ts": ts, "sibling_id": sibling[0],
                "previous_hash": stored_prev,
            })
        self._children.setdefault(stored_prev, (str(row.get("id")), ts))
        if len(self._children) > _FORK_WINDOW:
            del self._children[next(iter(self._children))]
        self.previous = row["entry_hash"]
        self.chained += 1
