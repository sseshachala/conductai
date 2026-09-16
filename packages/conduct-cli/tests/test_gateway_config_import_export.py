"""Tests for gateway-config import/export CLI commands.

Scope: argparse wiring + happy path + error paths. HTTP layer stubbed
via ``urllib.request.urlopen`` so no real API calls.

Invariants locked:
- Import posts to the design-locked URL.
- ``--name`` translates to ``name_override``.
- Non-existent file → readable error, no HTTP call.
- Non-JSON file → readable error, no HTTP call.
- Structured backend errors (PR #2033) render per-line.
- Export resolves cond_code via the list endpoint first.
"""
from __future__ import annotations

import io
import json
from unittest.mock import MagicMock

import pytest

from conduct_cli import main as cli


UUID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(autouse=True)
def _stub_auth(monkeypatch):
    monkeypatch.setattr(
        cli, "_require_auth",
        lambda args: ("https://api.example.com", "ws-1", "guard-mt-fake"),
    )


def _mk_response(payload, status=200):
    class _CM:
        def __enter__(self):
            fake = MagicMock()
            fake.read.return_value = json.dumps(payload).encode("utf-8")
            fake.status = status
            return fake
        def __exit__(self, *a): return False
    return _CM()


# ─── import ──────────────────────────────────────────────────────────


def test_import_posts_to_correct_url(tmp_path, monkeypatch):
    src = tmp_path / "profile.json"
    src.write_text(json.dumps({"name": "x", "targets": []}))
    captured = {}
    def _fake(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        return _mk_response({
            "profile": {"id": UUID, "name": "x", "cond_code": "aa"},
            "credential_gaps": [], "next_url": "",
        })
    monkeypatch.setattr(cli.urllib.request, "urlopen", _fake)

    args = MagicMock(); args.file = str(src); args.name = None
    cli.cmd_import_gateway_config(args)

    assert captured["url"].endswith("/workspaces/ws-1/gateway-profiles-v2/import")
    assert captured["method"] == "POST"


def test_import_body_wraps_json_in_working_copy(tmp_path, monkeypatch):
    src = tmp_path / "p.json"
    payload = {"name": "x", "targets": [{"id": "a"}]}
    src.write_text(json.dumps(payload))
    captured = {}
    def _fake(req, timeout=None):
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _mk_response({
            "profile": {"id": UUID, "name": "x", "cond_code": "aa"},
            "credential_gaps": [], "next_url": "",
        })
    monkeypatch.setattr(cli.urllib.request, "urlopen", _fake)

    args = MagicMock(); args.file = str(src); args.name = None
    cli.cmd_import_gateway_config(args)

    assert captured["body"]["working_copy"] == payload


def test_import_name_flag_becomes_override(tmp_path, monkeypatch):
    src = tmp_path / "p.json"
    src.write_text(json.dumps({"name": "orig"}))
    captured = {}
    def _fake(req, timeout=None):
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _mk_response({
            "profile": {"id": UUID, "name": "renamed", "cond_code": "aa"},
            "credential_gaps": [], "next_url": "",
        })
    monkeypatch.setattr(cli.urllib.request, "urlopen", _fake)

    args = MagicMock(); args.file = str(src); args.name = "renamed"
    cli.cmd_import_gateway_config(args)

    assert captured["body"].get("name_override") == "renamed"


def test_import_missing_file_no_http(tmp_path, monkeypatch, capsys):
    called = []
    monkeypatch.setattr(
        cli.urllib.request, "urlopen",
        lambda req, timeout=None: (called.append(True), _mk_response({}))[1],
    )
    args = MagicMock()
    args.file = str(tmp_path / "nope.json"); args.name = None
    cli.cmd_import_gateway_config(args)
    assert called == []
    assert "File not found" in capsys.readouterr().out


def test_import_invalid_json_no_http(tmp_path, monkeypatch, capsys):
    src = tmp_path / "bad.json"; src.write_text("{ not valid")
    called = []
    monkeypatch.setattr(
        cli.urllib.request, "urlopen",
        lambda req, timeout=None: (called.append(True), _mk_response({}))[1],
    )
    args = MagicMock(); args.file = str(src); args.name = None
    cli.cmd_import_gateway_config(args)
    assert called == []
    assert "Invalid JSON" in capsys.readouterr().out


def test_import_renders_structured_error_per_line(tmp_path, monkeypatch, capsys):
    import urllib.error
    src = tmp_path / "p.json"
    src.write_text(json.dumps({"name": "x"}))
    payload = {
        "detail": {
            "summary": "schema invalid",
            "errors": [
                {"path": "targets.0.credential_ref",
                 "message": "must not be empty",
                 "target_index": 0, "type": "value_error"},
                {"path": "accepts", "message": "field required",
                 "target_index": None, "type": "missing"},
            ],
        }
    }
    err = urllib.error.HTTPError(
        "http://x", 400, "Bad Request", {},
        io.BytesIO(json.dumps(payload).encode("utf-8")),
    )
    monkeypatch.setattr(
        cli.urllib.request, "urlopen",
        lambda req, timeout=None: (_ for _ in ()).throw(err),
    )
    args = MagicMock(); args.file = str(src); args.name = None
    cli.cmd_import_gateway_config(args)
    out = capsys.readouterr().out
    assert "schema invalid" in out
    assert "targets.0.credential_ref" in out
    assert "must not be empty" in out


def test_import_prints_credential_gaps(tmp_path, monkeypatch, capsys):
    src = tmp_path / "p.json"; src.write_text(json.dumps({"name": "x"}))
    monkeypatch.setattr(cli.urllib.request, "urlopen", lambda req, timeout=None: _mk_response({
        "profile": {"id": UUID, "name": "x", "cond_code": "aa"},
        "credential_gaps": [
            {"target_index": 0, "target_id": "primary", "transport": "native_http",
             "reason": "credential_ref stripped on import"},
            {"target_index": 1, "target_id": "fallback", "transport": "native_http",
             "reason": "credential_ref stripped on import"},
        ],
        "next_url": "https://api.example.com/proxy/gateway-profiles",
    }))
    args = MagicMock(); args.file = str(src); args.name = None
    cli.cmd_import_gateway_config(args)
    out = capsys.readouterr().out
    assert "2 target(s) need credentials" in out
    assert "primary" in out and "fallback" in out
    assert "/proxy/gateway-profiles" in out


# ─── export ──────────────────────────────────────────────────────────


def test_export_by_uuid_direct(monkeypatch, capsys):
    calls = []
    def _fake(req, timeout=None):
        calls.append(req.full_url)
        return _mk_response({"name": "claude", "targets": []})
    monkeypatch.setattr(cli.urllib.request, "urlopen", _fake)
    args = MagicMock(); args.target = UUID; args.out = None
    cli.cmd_export_gateway_config(args)
    assert calls == [f"https://api.example.com/workspaces/ws-1/gateway-profiles-v2/{UUID}/export"]
    assert '"name": "claude"' in capsys.readouterr().out


def test_export_by_cond_code_resolves_via_list(monkeypatch, capsys):
    calls = []
    def _fake(req, timeout=None):
        calls.append(req.full_url)
        if req.full_url.endswith("/gateway-profiles-v2"):
            return _mk_response([
                {"id": UUID, "cond_code": "abc12345", "model_alias": "claude"},
            ])
        return _mk_response({"name": "resolved", "targets": []})
    monkeypatch.setattr(cli.urllib.request, "urlopen", _fake)
    args = MagicMock(); args.target = "abc12345"; args.out = None
    cli.cmd_export_gateway_config(args)
    assert len(calls) == 2
    assert calls[0].endswith("/gateway-profiles-v2")
    assert calls[1].endswith(f"/gateway-profiles-v2/{UUID}/export")


def test_export_unknown_cond_code_no_export_call(monkeypatch, capsys):
    def _fake(req, timeout=None):
        return _mk_response([{"id": UUID, "cond_code": "other"}])
    monkeypatch.setattr(cli.urllib.request, "urlopen", _fake)
    args = MagicMock(); args.target = "unknown"; args.out = None
    cli.cmd_export_gateway_config(args)
    assert "No profile matched" in capsys.readouterr().out


def test_export_out_writes_file(tmp_path, monkeypatch):
    dest = tmp_path / "out.json"
    monkeypatch.setattr(cli.urllib.request, "urlopen",
                        lambda req, timeout=None: _mk_response({"name": "x", "targets": []}))
    args = MagicMock(); args.target = UUID; args.out = str(dest)
    cli.cmd_export_gateway_config(args)
    assert json.loads(dest.read_text()) == {"name": "x", "targets": []}
