"""Audit chain v2 (#2421): canonical full-record hash. No database needed."""
from __future__ import annotations

import pytest

from app.modules.guard import audit_chain as ac
from app.modules.guard.models import GuardAuditEvent

# Pinned vector. packages/conduct-cli/tests/test_audit_verify.py pins the same
# value: if this changes, the offline verifier and every stored v2 hash break.
VECTOR = {
    "id": "00000000-0000-0000-0000-0000000003e8",
    "workspace_id": "00000000-0000-0000-0000-000000000001",
    "ai_tool": "claude_code", "tool_call": "Bash", "source": "hook", "decision": "allowed",
    "ts": "2026-09-01T12:00:00+00:00", "input_summary": 'café "q"', "cost_usd_after": 1,
    "evaluated_rules": [{"rule_id": "r1", "severity": 2}],
    "previous_hash": "abc", "hash_version": 2,
}
VECTOR_HASH = "8c7cf32855d805256308207bb259902eef36ebc6806c7a9cd634e4f2fa004b9d"


def test_pinned_vector():
    assert ac.compute_v2(VECTOR) == VECTOR_HASH


def test_hashed_fields_cover_every_stored_column():
    """A new audit column must be hashed (or consciously listed as unhashed)."""
    columns = {c.name for c in GuardAuditEvent.__table__.columns}
    classified = set(ac.HASHED_FIELDS) | set(ac.UNHASHED_FIELDS)
    assert columns <= classified, f"unclassified audit column(s): {columns - classified}"
    # usage_source/usage_status are pre-registered for #2545 (columns land with that PR).
    assert classified - columns <= {"usage_source", "usage_status"}
    assert not set(ac.HASHED_FIELDS) & set(ac.UNHASHED_FIELDS)


def test_representation_independent():
    """Same stored value, different Python representation -> same hash."""
    from datetime import datetime, timedelta, timezone
    from uuid import UUID
    other = {**VECTOR,
             "id": UUID(VECTOR["id"]), "workspace_id": UUID(VECTOR["workspace_id"]),
             "ts": datetime(2026, 9, 1, 14, 0, tzinfo=timezone(timedelta(hours=2))),
             "cost_usd_after": 1.0}
    assert ac.compute_v2(other) == VECTOR_HASH
    assert ac.compute_v2({**VECTOR, "ts": "2026-09-01T12:00:00Z"}) == VECTOR_HASH


@pytest.mark.parametrize("field", ac.HASHED_FIELDS)
def test_every_hashed_field_changes_the_hash(field):
    if field in ac.TS_FIELDS:
        value = "2030-01-01T00:00:00Z"
    elif field in ac.UUID_FIELDS:
        value = "00000000-0000-0000-0000-0000000000ff"
    elif field in ac.INT_FIELDS:
        value = 7
    elif field in ac.FLOAT_FIELDS:
        value = 0.25
    elif field in ac.JSON_FIELDS:
        value = {"k": "v"}
    else:
        value = "changed"
    assert ac.compute_v2({**VECTOR, field: value}) != ac.compute_v2(VECTOR)


def test_previous_hash_is_bound():
    assert ac.compute_v2({**VECTOR, "previous_hash": "abd"}) != VECTOR_HASH


def test_unhashed_fields_do_not_change_the_hash():
    assert ac.compute_v2({**VECTOR, "entry_hash": "x", "archive_segment_id": "y"}) == VECTOR_HASH


def test_expected_hash_dispatches_on_version():
    v1_row = {"ts": "2026-09-01T12:00:00+00:00", "tool_call": "Bash", "decision": "allowed"}
    assert ac.expected_hash(v1_row, "p") == ac.compute_v1(v1_row["ts"], "Bash", "allowed", "p")
    assert ac.expected_hash({**v1_row, "hash_version": 1}, "p") == ac.expected_hash(v1_row, "p")
    assert ac.expected_hash({**VECTOR, "previous_hash": "stale"}, "abc") == VECTOR_HASH
    with pytest.raises(ValueError):
        ac.expected_hash({**VECTOR, "hash_version": 3}, "abc")


def test_chain_seal_stamps_version_and_hash():
    import uuid
    from datetime import datetime, timezone
    from app.modules.guard.models import chain_seal
    ev = GuardAuditEvent(workspace_id=uuid.uuid4(), ai_tool="t", decision="allowed",
                         ts=datetime.now(timezone.utc), previous_hash="")
    chain_seal(ev)
    assert ev.hash_version == 2 and ev.source == "hook" and ev.id is not None
    assert ev.entry_hash == ac.compute_v2({n: getattr(ev, n, None) for n in ac.HASHED_FIELDS})


def test_cli_verifier_hashes_the_same_fields():
    """Drift guard: the offline verifier (packages/conduct-cli) lists the same fields and gets the same hash."""
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[4] / "packages/conduct-cli/src/conduct_cli/commands/audit.py"
    if not path.exists():
        pytest.skip("conduct-cli not in this checkout")
    spec = importlib.util.spec_from_file_location("_conduct_cli_audit", path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    assert cli.HASHED_FIELDS == ac.HASHED_FIELDS
    assert cli.APPEND_RACE_FIXED_AT == ac.format_ts(ac.APPEND_RACE_FIXED_AT)
    full = {n: None for n in ac.HASHED_FIELDS} | VECTOR
    assert cli.compute_entry_hash_v2(full, "abc") == VECTOR_HASH


# ── known append-race forks (#2524 item 1) ─────────────────────────────────────

from datetime import datetime, timedelta, timezone  # noqa: E402

PRE = ac.APPEND_RACE_FIXED_AT - timedelta(days=30)
POST = ac.APPEND_RACE_FIXED_AT + timedelta(days=1)


def _row(i, prev, ts, version=1):
    row = {"id": f"00000000-0000-0000-0000-{i:012d}", "workspace_id": "00000000-0000-0000-0000-000000000001",
           "ai_tool": "t", "tool_call": f"tool{i}", "decision": "allowed", "source": "hook",
           "ts": ts + timedelta(seconds=i), "previous_hash": prev, "hash_version": version}
    row["entry_hash"] = ac.expected_hash(row, prev)
    return row


def _walk(rows):
    w = ac.ChainWalker()
    for r in rows:
        w.feed(r)
    return w


def test_fork_before_cutoff_is_a_known_append_race_not_a_break():
    a = _row(1, "", PRE)
    b = _row(2, a["entry_hash"], PRE)
    c = _row(3, a["entry_hash"], PRE)           # forks off a: shares b's previous_hash
    d = _row(4, c["entry_hash"], PRE)           # the next writer linked to the later row
    w = _walk([a, b, c, d])
    assert w.chained == 4
    assert [r["id"] for r in w.known_append_races] == [c["id"]]
    assert w.known_append_races[0]["sibling_id"] == b["id"]


def test_three_way_fork_and_mixed_version_fork():
    a = _row(1, "", PRE)
    kids = [_row(i, a["entry_hash"], PRE, version=2 if i == 3 else 1) for i in (2, 3, 4)]
    w = _walk([a, *kids])
    assert len(w.known_append_races) == 2


def test_fork_after_cutoff_is_broken():
    a = _row(1, "", POST)
    b = _row(2, a["entry_hash"], POST)
    c = _row(3, a["entry_hash"], POST)
    with pytest.raises(ac.ChainBroken):
        _walk([a, b, c])


def test_fork_straddling_the_cutoff_is_broken():
    a = _row(1, "", ac.APPEND_RACE_FIXED_AT - timedelta(seconds=30))
    b = _row(2, a["entry_hash"], ac.APPEND_RACE_FIXED_AT - timedelta(seconds=20))
    c = _row(3, a["entry_hash"], ac.APPEND_RACE_FIXED_AT + timedelta(seconds=20))
    with pytest.raises(ac.ChainBroken):
        _walk([a, b, c])


def test_fork_with_a_wrong_entry_hash_is_broken():
    a = _row(1, "", PRE)
    b = _row(2, a["entry_hash"], PRE)
    c = {**_row(3, a["entry_hash"], PRE), "tool_call": "edited"}
    with pytest.raises(ac.ChainBroken):
        _walk([a, b, c])


def test_deleted_row_and_unknown_parent_are_still_broken_before_cutoff():
    a = _row(1, "", PRE)
    b = _row(2, a["entry_hash"], PRE)
    c = _row(3, b["entry_hash"], PRE)
    with pytest.raises(ac.ChainBroken):
        _walk([a, c])                              # b removed: c's parent was never walked
    with pytest.raises(ac.ChainBroken):
        _walk([a, _row(2, "f" * 64, PRE)])         # linked to a hash nobody holds


def test_v2_field_edit_on_a_forked_row_is_broken():
    a = _row(1, "", PRE, version=2)
    b = _row(2, a["entry_hash"], PRE, version=2)
    c = {**_row(3, a["entry_hash"], PRE, version=2), "ai_tool": "edited"}
    with pytest.raises(ac.ChainBroken):
        _walk([a, b, c])
