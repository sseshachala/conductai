import json
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from conduct_cli.hooks import fixture_approval as fixtures
from conduct_cli.guard_commands import fixture_review


def edit(text="synthetic material", path="tests/fixture.txt"):
    return {"file_path": path, "content": text}


def test_digest_binds_whole_edit_tool_target_and_working_directory(tmp_path):
    root = str(tmp_path)
    digest = fixtures.fingerprint("write", edit(), root)
    assert digest == fixtures.fingerprint(
        "write", dict(reversed(list(edit().items()))), root
    )
    for tool, payload, cwd in [
        ("edit", edit(), root),
        ("write", edit("changed"), root),
        ("write", edit(path="tests/another.txt"), root),
        ("write", edit(), root + "/other"),
        ("write", {**edit(), "extra": "changed"}, root),
    ]:
        assert fixtures.fingerprint(tool, payload, cwd) != digest


@pytest.mark.parametrize(
    "tool,payload,cwd,error",
    [
        ("bash", {"command": "anything"}, None, "Only structured single-file"),
        ("write", edit(path="src/main.py"), None, "restricted to test directories"),
        ("write", edit(), "relative", "absolute working directory"),
        ("apply_patch", {"command": "shell command"}, None, "complete patch"),
        ("write", edit("x" * 270000), None, "exceeds review limits"),
    ],
)
def test_unsupported_actions_cannot_request_exception(tmp_path, tool, payload, cwd, error):
    with pytest.raises(ValueError, match=error):
        fixtures.fingerprint(tool, payload, cwd or str(tmp_path))


def test_patch_restricted_to_single_add_or_update(tmp_path):
    patch = (
        "*** Begin Patch\n*** Add File: tests/fixture.txt\n+synthetic\n*** End Patch"
    )
    assert fixtures.fingerprint("functions.apply_patch", {"patch": patch}, str(tmp_path))
    for operation in [
        "*** Delete File: tests/fixture.txt",
        "*** Move to: tests/new.txt",
        "*** Add File: tests/other.txt",
    ]:
        changed = patch.replace("*** End Patch", operation + "\n*** End Patch")
        with pytest.raises(ValueError, match="Only one test file"):
            fixtures.fingerprint("apply_patch", {"patch": changed}, str(tmp_path))


@pytest.mark.parametrize(
    "outcome", ["approved", "denied", "outage", "mismatch", "malformed"]
)
def test_consume_fail_closed_without_uploading_content(monkeypatch, tmp_path, outcome):
    cfg = {
        "workspace_id": str(uuid4()),
        "agent_token": "fixture-token",
        "api_url": "https://local.example",
    }
    monkeypatch.setattr(fixtures, "load_config", lambda: cfg)
    digest = fixtures.fingerprint("write", edit(), str(tmp_path))
    payload = {
        "approved": outcome != "denied",
        "id": str(uuid4()),
        "rule_id": "no-private-key",
        "action_digest": "a" * 64 if outcome == "mismatch" else digest,
    }
    response = Mock(status=200)
    response.read.return_value = (
        b"not-json" if outcome == "malformed" else json.dumps(payload).encode()
    )
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    opener = Mock()
    opener.open.return_value = response
    if outcome == "outage":
        opener.open.side_effect = TimeoutError()
    monkeypatch.setattr(fixtures.urllib.request, "build_opener", lambda *_: opener)
    assert fixtures.consume("write", edit(), str(tmp_path)) == (outcome == "approved")
    request = opener.open.call_args.args[0]
    assert request.full_url.startswith(
        "https://local.example/guard/fixture-approvals/consume"
    )
    assert "synthetic material" not in request.data.decode()
    assert json.loads(request.data) == {"action_digest": digest}


def test_review_requires_explicit_human_acknowledgement(tmp_path, monkeypatch):
    path = tmp_path / "action.json"
    path.write_text(
        json.dumps({"tool_name": "write", "tool_input": edit(), "cwd": str(tmp_path)})
    )
    request = Mock()
    monkeypatch.setattr(fixture_review.shared, "_req", request)
    args = SimpleNamespace(
        action="approve",
        action_file=str(path),
        reviewed_synthetic=False,
        subject="member",
        reason="fixture",
    )
    with pytest.raises(SystemExit, match="--reviewed-synthetic"):
        fixture_review.run(args)
    request.assert_not_called()


def test_review_uploads_only_fingerprint_and_review_metadata(tmp_path, monkeypatch):
    path = tmp_path / "action.json"
    path.write_text(
        json.dumps({"tool_name": "write", "tool_input": edit(), "cwd": str(tmp_path)})
    )
    cfg = {
        "workspace_id": str(uuid4()),
        "api_url": "https://local.example",
        "agent_token": "fixture-token",
    }
    monkeypatch.setattr(fixture_review.shared, "_require_guard_config", lambda: cfg)
    request = Mock(return_value={"id": str(uuid4())})
    monkeypatch.setattr(fixture_review.shared, "_req", request)
    fixture_review.run(
        SimpleNamespace(
            action="approve",
            action_file=str(path),
            reviewed_synthetic=True,
            subject="member",
            reason="Reviewed locally",
            ttl_seconds=600,
        )
    )
    body = request.call_args.kwargs["body"]
    assert body["synthetic_reviewed"] is True
    assert body["subject_id"] == "member"
    assert "synthetic material" not in json.dumps(body)


def test_fixture_permission_does_not_skip_other_rules(monkeypatch, tmp_path):
    from conduct_cli.hooks import pretooluse

    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "rule_id": "no-private-key",
                        "action": "block",
                        "match_pattern": "synthetic",
                    },
                    {
                        "rule_id": "second-rule",
                        "action": "block",
                        "match_pattern": "synthetic",
                    },
                ]
            }
        )
    )
    monkeypatch.setattr(pretooluse, "active_policy_path", lambda: policy)
    monkeypatch.setattr(pretooluse, "_verify_policy_signature", lambda _: True)
    assert pretooluse.check_policy("write", edit())[2] == "no-private-key"
    assert (
        pretooluse.check_policy("write", edit(), fixture_approved=True)[2]
        == "second-rule"
    )


@pytest.mark.parametrize(
    "approved,second_block", [(False, False), (True, False), (True, True)]
)
def test_main_uses_online_approval_and_rechecks_remaining_rules(
    monkeypatch, approved, second_block
):
    from io import StringIO
    from conduct_cli.hooks import pretooluse as hook

    monkeypatch.setattr(hook, "_get_fail_mode", lambda: "fail_open")
    monkeypatch.setattr(hook, "_get_advisory_mode", lambda: False)
    monkeypatch.setattr(hook, "_load_budget_cache", lambda: (False, None))
    monkeypatch.setattr(hook, "_maybe_sync_policy", lambda: None)
    monkeypatch.setattr(hook, "_should_periodic_flush", lambda: False)
    monkeypatch.setattr(hook, "record_hook_heartbeat", lambda *_: None)
    checks = Mock(
        side_effect=[
            (None, "block", "no-private-key", "blocked"),
            (
                None,
                "block" if second_block else "allow",
                "other-rule" if second_block else None,
                "checked",
            ),
        ]
    )
    monkeypatch.setattr(hook, "check_policy", checks)
    consume = Mock(return_value=approved)
    monkeypatch.setattr(fixtures, "consume", consume)
    events = Mock()
    monkeypatch.setattr(hook, "post_event", events)
    monkeypatch.setattr(
        hook.sys,
        "stdin",
        StringIO(json.dumps({"tool_name": "write", "tool_input": edit()})),
    )
    with pytest.raises(SystemExit) as exc:
        hook.main()
    assert exc.value.code == (0 if approved and not second_block else 2)
    assert checks.call_count == (2 if approved else 1)
    if approved:
        assert checks.call_args.kwargs == {"fixture_approved": True}
