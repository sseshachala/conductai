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
