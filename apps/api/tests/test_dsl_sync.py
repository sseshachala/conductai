"""
delegator.yml repo sync — verifies the validate-and-promote behaviour without
touching GitHub or the real database. We stub the two collaborators
(``_github_token`` and ``github.read_file``) and feed in a mock SQLAlchemy
Session so we can assert what got persisted.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.dsl import sync as sync_mod


GOOD_YAML = """
name: from-repo
on:
  manual:
    next: a
blocks:
  a:
    type: tool
    integration: slack
    action: post_message
    params: { channel: "#x", text: hi }
"""


def _make_workflow(*, source_repo: str | None = "owner/repo",
                   source_path: str | None = "delegator.yml",
                   current_yaml: str | None = None,
                   current_version_id="v1"):
    """Build a stand-in Workflow object with the few attrs sync needs."""
    current = SimpleNamespace(id=current_version_id, yaml_source=current_yaml) if current_yaml else None
    wf = SimpleNamespace(
        id="w1",
        workspace_id="ws1",
        source_repo=source_repo,
        source_path=source_path,
        current_version_id=current_version_id if current else None,
        _current=current,
    )
    return wf


def _make_db(workflow):
    """Mock Session — returns the embedded WorkflowVersion when asked, captures adds."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = workflow._current
    added: list = []
    db.add.side_effect = lambda obj: added.append(obj)
    db._added = added  # type: ignore[attr-defined]
    return db


def test_raises_when_workflow_has_no_source():
    wf = _make_workflow(source_repo=None, source_path=None)
    db = _make_db(wf)
    with pytest.raises(sync_mod.SyncError, match="no repo source"):
        sync_mod.sync_workflow_from_repo(db=db, workflow=wf)


def test_raises_on_malformed_source_repo():
    wf = _make_workflow(source_repo="not-a-slug")
    db = _make_db(wf)
    with patch.object(sync_mod, "_github_token", return_value="t"):
        with patch.object(sync_mod.github, "read_file"):
            with pytest.raises(sync_mod.SyncError):
                sync_mod.sync_workflow_from_repo(db=db, workflow=wf)


def test_no_op_when_yaml_unchanged():
    wf = _make_workflow(current_yaml=GOOD_YAML)
    db = _make_db(wf)
    with patch.object(sync_mod, "_github_token", return_value="t"):
        with patch.object(
            sync_mod.github,
            "read_file",
            return_value={"found": True, "content": GOOD_YAML, "sha": "sha-current"},
        ):
            result = sync_mod.sync_workflow_from_repo(db=db, workflow=wf)
    assert result["changed"] is False
    assert db._added == [], "no new WorkflowVersion should be persisted"


def test_creates_new_version_when_yaml_changes():
    wf = _make_workflow(current_yaml="name: old\nblocks: { a: { type: tool, integration: slack, action: post_message, params: {} } }")
    db = _make_db(wf)
    with patch.object(sync_mod, "_github_token", return_value="t"):
        with patch.object(
            sync_mod.github,
            "read_file",
            return_value={"found": True, "content": GOOD_YAML, "sha": "sha-new"},
        ):
            result = sync_mod.sync_workflow_from_repo(db=db, workflow=wf)
    assert result["changed"] is True
    assert result["sha"] == "sha-new"
    assert len(db._added) == 1


def test_raises_when_remote_yaml_invalid():
    wf = _make_workflow()
    db = _make_db(wf)
    with patch.object(sync_mod, "_github_token", return_value="t"):
        with patch.object(
            sync_mod.github,
            "read_file",
            return_value={"found": True, "content": "name: bad\nblocks: not-a-mapping\n"},
        ):
            with pytest.raises(sync_mod.SyncError, match="failed validation"):
                sync_mod.sync_workflow_from_repo(db=db, workflow=wf)


def test_raises_when_remote_file_missing():
    wf = _make_workflow()
    db = _make_db(wf)
    with patch.object(sync_mod, "_github_token", return_value="t"):
        with patch.object(
            sync_mod.github,
            "read_file",
            return_value={"found": False, "path": "delegator.yml"},
        ):
            with pytest.raises(sync_mod.SyncError, match="not found"):
                sync_mod.sync_workflow_from_repo(db=db, workflow=wf)
