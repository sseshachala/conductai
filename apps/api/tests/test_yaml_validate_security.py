"""Auth on POST /workflows/yaml/validate and containment of ``extends:``."""
from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from app.dsl.loader import load_workflow_yaml
from app.dsl.schema import WorkflowValidationError
from app.main import app

PLAYBOOKS = pathlib.Path(__file__).resolve().parent.parent / "playbooks"

_CHILD = """\
name: child
extends: {ref}
trigger: {{type: manual}}
blocks:
  a:
    type: brain
    mode: single
    description: hi
"""


def test_yaml_validate_requires_auth():
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/workflows/yaml/validate", json={"yaml": "name: x"})
    assert resp.status_code in (401, 403)


@pytest.mark.parametrize(
    "ref",
    ["../base-autopilot", "..", "/abs/base-autopilot", "sub/base-autopilot", "'a\\\\b'"],
)
def test_extends_rejects_unsafe_names(tmp_path, ref):
    with pytest.raises(WorkflowValidationError):
        load_workflow_yaml(_CHILD.format(ref=ref), base_dir=tmp_path)


def test_extends_rejects_non_string(tmp_path):
    with pytest.raises(WorkflowValidationError):
        load_workflow_yaml(_CHILD.format(ref="[a, b]"), base_dir=tmp_path)


def test_extends_symlink_escape_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "evil.yaml").write_text("kind: base\nname: evil\n")
    base = tmp_path / "base"
    base.mkdir()
    (base / "evil.yaml").symlink_to(outside / "evil.yaml")
    with pytest.raises(WorkflowValidationError, match="inside the base directory"):
        load_workflow_yaml(_CHILD.format(ref="evil"), base_dir=base)


def test_extends_existing_base_still_works():
    wf = load_workflow_yaml(_CHILD.format(ref="base-autopilot"), base_dir=PLAYBOOKS)
    assert wf.name == "child"
