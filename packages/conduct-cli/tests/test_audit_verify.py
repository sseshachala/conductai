"""`conduct audit verify` — fixture is produced by the API's real hash fn + export serializer
(apps/api/tests/test_audit_export.py::test_cli_fixture_matches_current_hash_function)."""
import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from conduct_cli.commands.audit import cmd_audit, verify_lines

FIXTURE = Path(__file__).parent / "fixtures" / "audit_export_chain.ndjson"


def _args(file, allow_gaps=False):
    return argparse.Namespace(audit_command="verify", file=str(file), allow_gaps=allow_gaps)


def _lines():
    return FIXTURE.read_text().splitlines()


def test_fixture_verifies(capsys):
    cmd_audit(_args(FIXTURE))
    out = capsys.readouterr().out
    assert out.startswith("OK: 5 rows, 5 chained") and "genesis" in out


@pytest.mark.parametrize("field,value", [("decision", "allowed"), ("tool_call", "Evil"), ("ts", "2026-01-01T00:00:00+00:00")])
def test_tampered_hashed_field_fails_at_that_row(tmp_path, capsys, field, value):
    lines = _lines()
    rec = json.loads(lines[2])
    rec[field] = value
    lines[2] = json.dumps(rec)
    bad = tmp_path / "bad.ndjson"
    bad.write_text("\n".join(lines) + "\n")
    with pytest.raises(SystemExit) as exc:
        cmd_audit(_args(bad))
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "BROKEN at line 3" in err and rec["id"] in err and "expected:" in err and "actual:" in err


def test_deleted_row_breaks_linkage_at_next_row():
    lines = _lines()
    res = verify_lines(lines[:1] + lines[2:])
    assert not res["ok"] and res["broken"]["line"] == 2 and "previous_hash" in res["broken"]["reason"]
    assert verify_lines(lines[:1] + lines[2:], allow_gaps=True)["ok"]


def test_mid_chain_export_is_anchored_on_first_row():
    res = verify_lines(_lines()[2:])
    assert res["ok"] and res["chained"] == 3 and res["anchor"] != ""


def test_unchained_rows_are_skipped_and_garbage_fails():
    lines = _lines()
    legacy = json.dumps({"id": "x", "ts": "t", "decision": "allowed", "entry_hash": None})
    assert verify_lines(lines[:2] + [legacy] + lines[2:])["chained"] == 5
    assert verify_lines(["{not json"])["broken"]["line"] == 1


def test_missing_file_exits_1(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        cmd_audit(_args(tmp_path / "nope.ndjson"))
    assert exc.value.code == 1


# ── chain v2 (#2421) ──────────────────────────────────────────────────────────

def test_fixture_is_mixed_v1_v2():
    res = verify_lines(_lines())
    assert res["ok"] and res["versions"] == {1: 2, 2: 3}


def test_pinned_vector_matches_api():
    """Same vector as apps/api/tests/guard/test_audit_chain_v2.py."""
    from conduct_cli.commands.audit import compute_entry_hash_v2
    rec = {
        "id": "00000000-0000-0000-0000-0000000003e8",
        "workspace_id": "00000000-0000-0000-0000-000000000001",
        "ai_tool": "claude_code", "tool_call": "Bash", "source": "hook", "decision": "allowed",
        "ts": "2026-09-01T12:00:00+00:00", "input_summary": 'café "q"', "cost_usd_after": 1,
        "evaluated_rules": [{"rule_id": "r1", "severity": 2}], "hash_version": 2,
    }
    from conduct_cli.commands.audit import HASHED_FIELDS
    full = {n: None for n in HASHED_FIELDS} | rec
    assert compute_entry_hash_v2(full, "abc") == "8c7cf32855d805256308207bb259902eef36ebc6806c7a9cd634e4f2fa004b9d"


@pytest.mark.parametrize("field,value", [
    ("input_summary", "tampered"), ("rule_id", "other"), ("user_email", "a@b.c"),
    ("policy_hash", "ff"), ("hostname", "h"), ("tokens_before", 9), ("routing_meta", {"a": 1}),
])
def test_tampering_any_v2_field_fails_at_that_row(field, value):
    lines = _lines()
    rec = json.loads(lines[3])  # a v2 row
    assert rec["hash_version"] == 2 and rec[field] != value
    rec[field] = value
    lines[3] = json.dumps(rec)
    res = verify_lines(lines)
    assert not res["ok"] and res["broken"]["line"] == 4


def test_v2_row_cannot_be_downgraded_to_v1():
    lines = _lines()
    rec = json.loads(lines[3])
    rec["hash_version"] = 1
    lines[3] = json.dumps(rec)
    assert verify_lines(lines)["broken"]["line"] == 4


def test_v1_row_tamper_still_detected_and_unknown_version_fails():
    lines = _lines()
    rec = json.loads(lines[0])
    rec["decision"] = "blocked"
    assert verify_lines([json.dumps(rec)] + lines[1:])["broken"]["line"] == 1
    rec = json.loads(lines[3])
    rec["hash_version"] = 9
    lines[3] = json.dumps(rec)
    assert "unknown hash_version" in verify_lines(lines)["broken"]["reason"]


def test_export_missing_a_hashed_field_is_reported():
    lines = _lines()
    rec = json.loads(lines[3])
    del rec["hostname"]
    lines[3] = json.dumps(rec)
    assert "lacks hashed field" in verify_lines(lines)["broken"]["reason"]


def test_archived_row_is_linkage_only_only_when_payload_is_gone():
    lines = _lines()
    rec = json.loads(lines[3])
    rec.update(archive_segment_id="00000000-0000-0000-0000-0000000000aa",
               input_summary=None, result_summary=None, blast_radius=None)
    lines[3] = json.dumps(rec)
    res = verify_lines(lines)
    assert res["ok"] and res["linkage_only"] == 1  # real archival nulls all payload fields
    # A row that still carries its payload is fully rehashed even if marked archived.
    rec = json.loads(_lines()[3])
    rec.update(archive_segment_id="00000000-0000-0000-0000-0000000000aa", input_summary="edited")
    lines[3] = json.dumps(rec)
    assert not verify_lines(lines)["ok"]


# ── known append-race forks (#2524 item 1) ─────────────────────────────────────

def _v1(i, prev, ts):
    from conduct_cli.commands.audit import compute_entry_hash
    return json.dumps({"id": f"id{i}", "ts": ts, "tool_call": f"t{i}", "decision": "allowed",
                       "previous_hash": prev,
                       "entry_hash": compute_entry_hash(ts, f"t{i}", "allowed", prev)})


def _fork(day):
    """a -> b, a -> c (fork), c -> d. Every entry_hash is individually correct."""
    ts = lambda s: f"{day}T00:00:0{s}+00:00"  # noqa: E731
    a = _v1(1, "", ts(1))
    ha = json.loads(a)["entry_hash"]
    b = _v1(2, ha, ts(2))
    c = _v1(3, ha, ts(3))
    d = _v1(4, json.loads(c)["entry_hash"], ts(4))
    return [a, b, c, d]


def test_pre_fix_fork_is_a_known_append_race(capsys, tmp_path):
    lines = _fork("2026-10-01")
    res = verify_lines(lines)
    assert res["ok"] and res["chained"] == 4
    assert [r["id"] for r in res["known_append_races"]] == ["id3"]
    f = tmp_path / "fork.ndjson"
    f.write_text("\n".join(lines) + "\n")
    cmd_audit(_args(f))
    out = capsys.readouterr().out
    assert out.startswith("OK:") and "1 known append race" in out and "id3" in out


def test_fork_from_after_the_fix_is_broken():
    res = verify_lines(_fork("2026-11-10"))
    assert not res["ok"] and res["broken"]["id"] == "id3"


def test_fork_with_edited_row_is_broken_and_deleted_parent_is_broken():
    lines = _fork("2026-10-01")
    rec = json.loads(lines[2])
    rec["decision"] = "blocked"
    lines[2] = json.dumps(rec)
    assert verify_lines(lines)["broken"]["line"] == 3
    # row removed so its child links to a hash never seen
    assert not verify_lines(_fork("2026-10-01")[:1] + _fork("2026-10-01")[3:])["ok"]
