import io
import json
from datetime import datetime
from pathlib import Path

import pytest

from conduct_cli import audit_formats as af
from conduct_cli.commands import audit_feed

FIXTURE = Path(__file__).parent / "fixtures" / "audit_export_chain.ndjson"
EVENTS = [json.loads(line) for line in FIXTURE.read_text().splitlines()]
BLOCKED = next(e for e in EVENTS if e["decision"] == "blocked")
FIRST = EVENTS[0]


def _with_extras(event):
    # Fields Track A adds later must be carried, never dropped or crash a formatter.
    return dict(event, hash_version=2, checkpoint={"sig": "abc", "head": "h"})


def test_json_is_the_native_line():
    assert json.loads(af.format_json(FIRST)) == FIRST
    assert " " not in af.format_json({"a": 1, "b": 2})


def test_ocsf_api_activity_shape_and_chain():
    rec = json.loads(af.format_ocsf(_with_extras(BLOCKED)))
    assert (rec["class_uid"], rec["category_uid"], rec["type_uid"]) == (6003, 6, 600399)
    assert rec["action_id"] == 2 and rec["disposition_id"] == 2 and rec["severity_id"] == 4
    assert rec["status_id"] == 2
    assert rec["time"] == int(datetime.fromisoformat(BLOCKED["ts"]).timestamp() * 1000)
    assert rec["metadata"]["uid"] == BLOCKED["id"] and rec["metadata"]["sequence"] == BLOCKED["chain_position"]
    assert rec["api"]["operation"]
    for k in ("previous_hash", "entry_hash", "chain_position"):
        assert rec["unmapped"][k] == BLOCKED[k]
    assert rec["unmapped"]["hash_version"] == 2 and rec["unmapped"]["checkpoint"]["sig"] == "abc"


def test_ocsf_keeps_empty_previous_hash_on_first_row():
    rec = json.loads(af.format_ocsf(FIRST))
    assert rec["unmapped"]["previous_hash"] == ""
    assert rec["action_id"] == 1 and rec["severity_id"] == 1


def test_ocsf_warned_is_allowed_with_alert_disposition():
    rec = json.loads(af.format_ocsf(next(e for e in EVENTS if e["decision"] == "warned")))
    assert rec["action_id"] == 1 and rec["disposition_id"] == 19 and rec["severity_id"] == 3


def test_ecs_shape_and_chain():
    rec = json.loads(af.format_ecs(_with_extras(BLOCKED)))
    assert rec["@timestamp"] == BLOCKED["ts"]
    assert rec["event"]["outcome"] == "failure" and rec["event"]["type"] == ["denied"]
    assert rec["event"]["category"] == ["intrusion_detection"] and rec["event"]["dataset"] == "conduct.guard.audit"
    assert rec["event"]["hash"] == BLOCKED["entry_hash"]
    chain = rec["conduct"]["chain"]
    assert chain == {"previous_hash": BLOCKED["previous_hash"], "entry_hash": BLOCKED["entry_hash"],
                     "position": BLOCKED["chain_position"]}
    assert rec["conduct"]["extra"]["hash_version"] == 2


def test_ecs_keeps_empty_previous_hash_on_first_row():
    assert json.loads(af.format_ecs(FIRST))["conduct"]["chain"]["previous_hash"] == ""


def test_cef_header_and_chain_extensions():
    line = af.format_cef(_with_extras(BLOCKED))
    assert line.startswith("CEF:0|Conduct|Guard|1|guard.blocked|") and "\n" not in line
    header, ext = line.split("|", 7)[6], line.split("|", 7)[7]
    assert header == "8"
    assert "cs4Label=entryHash cs4=" + BLOCKED["entry_hash"] in ext
    assert "cs5Label=previousHash cs5=" + BLOCKED["previous_hash"] in ext
    assert "cn1Label=chainPosition cn1=%d" % BLOCKED["chain_position"] in ext
    assert "conductHashVersion=2" in ext


def test_cef_empty_previous_hash_still_emitted_on_first_row():
    assert "cs5=" in af.format_cef(FIRST)


def test_cef_escaping():
    ev = dict(FIRST, tool_call="a|b\\c", input_summary="x=1\nline2", rule_message=None)
    line = af.format_cef(ev)
    assert "a\\|b\\\\c" in line
    assert "msg=x\\=1\\nline2" in line
    assert "\n" not in line


@pytest.mark.parametrize("fmt", af.FORMATS)
def test_tolerates_sparse_and_unknown_events(fmt):
    out = af.FORMATTERS[fmt]({"id": "1", "decision": "weird", "novel_field": {"a": 1}})
    assert out


def test_approval_decision_maps_to_medium_severity():
    ev = dict(FIRST, decision="approval_required")
    assert json.loads(af.format_ocsf(ev))["severity_id"] == 3
    assert "|6|" in af.format_cef(ev)


def test_run_feed_applies_format(monkeypatch, tmp_path):
    page = {"events": [BLOCKED], "next_cursor": "c1", "has_more": False}
    monkeypatch.setattr(audit_feed, "_call_tool", lambda *a, **k: page)
    out = io.StringIO()
    audit_feed.run_feed(since=None, limit=5, follow=False, interval=0, state=tmp_path / "c", out=out, fmt="cef")
    assert out.getvalue().startswith("CEF:0|") and out.getvalue().endswith("\n")
    out = io.StringIO()
    audit_feed.run_feed(since=None, limit=5, follow=False, interval=0, state=tmp_path / "d", out=out)
    assert json.loads(out.getvalue()) == BLOCKED
