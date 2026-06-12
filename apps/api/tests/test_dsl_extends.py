"""
Tests for the compile-time ``extends:`` system in the playbook DSL.

The extends system is resolved inside ``load_workflow_yaml`` before Pydantic
validation, so the runtime never sees ``$use``, ``{{$snippet:...}}``, or the
``extends`` key itself.
"""
from __future__ import annotations

import pathlib
import textwrap

import pytest

from app.dsl.loader import load_workflow_yaml
from app.dsl.schema import WorkflowValidationError

# ---------------------------------------------------------------------------
# Helpers — build minimal in-memory base + child YAML for unit tests
# ---------------------------------------------------------------------------

def _base_yaml(snippets: dict[str, str] = None, blocks: dict = None) -> str:
    """Return a well-formed base YAML string."""
    parts = ["kind: base", "name: test-base"]

    if snippets:
        parts.append("snippets:")
        for name, text in snippets.items():
            # Use block scalar so multi-line text is safe
            indented = textwrap.indent(text, "    ")
            parts.append(f"  {name}: |")
            parts.append(indented)

    if blocks:
        parts.append("blocks:")
        for block_id, fields in blocks.items():
            parts.append(f"  {block_id}:")
            for k, v in fields.items():
                parts.append(f"    {k}: {v}")

    return "\n".join(parts) + "\n"


def _write_base(tmp_path: pathlib.Path, content: str, name: str = "test-base") -> pathlib.Path:
    p = tmp_path / f"{name}.yaml"
    p.write_text(content)
    return tmp_path


def _minimal_workflow(blocks_yaml: str, extends: str = "test-base") -> str:
    return textwrap.dedent(f"""\
        extends: {extends}
        name: Test Workflow
        version: 1
        on:
          manual:
            next: step_a
        blocks:
        {textwrap.indent(blocks_yaml.strip(), "  ")}
    """)


# ---------------------------------------------------------------------------
# 1. Snippet injection
# ---------------------------------------------------------------------------

def test_snippet_injection(tmp_path):
    base = _base_yaml(snippets={"lint": "run linter\n"})
    _write_base(tmp_path, base)

    child_yaml = _minimal_workflow("""\
        step_a:
          type: brain
          mode: single
          description: "before {{$snippet: lint}} after"
    """)

    wf = load_workflow_yaml(child_yaml, base_dir=tmp_path)
    desc = wf.blocks["step_a"].description
    assert "run linter" in desc
    assert "{{$snippet:" not in desc


# ---------------------------------------------------------------------------
# 2. $use block merge — base fields as defaults, child fields win on conflict
# ---------------------------------------------------------------------------

def test_use_block_merge(tmp_path):
    base = _base_yaml(blocks={
        "recall_context": {
            "type": "memory",
            "label": "Recall prior context",
            "action": "read",
            "scope": "repo",
            "limit": "5",
        }
    })
    _write_base(tmp_path, base)

    # Trigger must route to the first declared block.
    child_yaml = textwrap.dedent("""\
        extends: test-base
        name: Test Workflow
        version: 1
        on:
          manual:
            next: recall_context
        blocks:
          recall_context:
            $use: test-base.recall_context
            key: "my-key"
            next: step_b
          step_b:
            type: output
            label: Done
            output:
              via: slack
              slack:
                channel: "#eng"
    """)

    wf = load_workflow_yaml(child_yaml, base_dir=tmp_path)
    block = wf.blocks["recall_context"]

    # Base fields carried over
    assert block.type == "memory"
    assert block.label == "Recall prior context"
    assert block.action == "read"
    assert block.scope == "repo"
    assert block.limit == 5

    # Child-supplied fields present
    assert block.key == "my-key"
    assert block.next == "step_b"

    # $use key removed
    assert not hasattr(block, "$use")


# ---------------------------------------------------------------------------
# 3. Child block fields override base block fields
# ---------------------------------------------------------------------------

def test_child_overrides_base(tmp_path):
    base = _base_yaml(blocks={
        "recall_context": {
            "type": "memory",
            "label": "Base Label",
            "action": "read",
            "scope": "repo",
        }
    })
    _write_base(tmp_path, base)

    child_yaml = textwrap.dedent("""\
        extends: test-base
        name: Test Workflow
        version: 1
        on:
          manual:
            next: recall_context
        blocks:
          recall_context:
            $use: test-base.recall_context
            label: "Child Label"
            key: "k"
            next: done
          done:
            type: output
            label: Done
            output:
              via: slack
              slack:
                channel: "#eng"
    """)

    wf = load_workflow_yaml(child_yaml, base_dir=tmp_path)
    assert wf.blocks["recall_context"].label == "Child Label"


# ---------------------------------------------------------------------------
# 4. Unknown snippet → WorkflowValidationError
# ---------------------------------------------------------------------------

def test_unknown_snippet_raises(tmp_path):
    base = _base_yaml(snippets={"lint": "run linter\n"})
    _write_base(tmp_path, base)

    child_yaml = _minimal_workflow("""\
        step_a:
          type: brain
          mode: single
          description: "{{$snippet: nonexistent}}"
    """)

    with pytest.raises(WorkflowValidationError, match="unknown snippet"):
        load_workflow_yaml(child_yaml, base_dir=tmp_path)


# ---------------------------------------------------------------------------
# 5. Missing base file → WorkflowValidationError
# ---------------------------------------------------------------------------

def test_missing_base_file_raises(tmp_path):
    child_yaml = textwrap.dedent("""\
        extends: nonexistent-base
        name: Test
        version: 1
        on:
          manual:
            next: step_a
        blocks:
          step_a:
            type: output
            label: Done
            output:
              via: slack
              slack:
                channel: "#eng"
    """)

    with pytest.raises(WorkflowValidationError, match="base file not found"):
        load_workflow_yaml(child_yaml, base_dir=tmp_path)


# ---------------------------------------------------------------------------
# 6. Extends file with wrong kind → WorkflowValidationError
# ---------------------------------------------------------------------------

def test_wrong_kind_raises(tmp_path):
    wrong = "kind: workflow\nname: not-a-base\n"
    (tmp_path / "wrong-base.yaml").write_text(wrong)

    child_yaml = textwrap.dedent("""\
        extends: wrong-base
        name: Test
        version: 1
        on:
          manual:
            next: step_a
        blocks:
          step_a:
            type: output
            label: Done
            output:
              via: slack
              slack:
                channel: "#eng"
    """)

    with pytest.raises(WorkflowValidationError, match="not a base file"):
        load_workflow_yaml(child_yaml, base_dir=tmp_path)


# ---------------------------------------------------------------------------
# 7. Community submission with extends → WorkflowValidationError
# ---------------------------------------------------------------------------

def test_extends_rejected_without_base_dir():
    child_yaml = textwrap.dedent("""\
        extends: base-autopilot
        name: Test
        version: 1
        on:
          manual:
            next: step_a
        blocks:
          step_a:
            type: output
            label: Done
            output:
              via: slack
              slack:
                channel: "#eng"
    """)

    with pytest.raises(WorkflowValidationError, match="not supported for community submissions"):
        load_workflow_yaml(child_yaml, base_dir=None)


# ---------------------------------------------------------------------------
# 8. All five autopilot-family playbooks expand without error
# ---------------------------------------------------------------------------

def test_all_five_playbooks_expand():
    base_dir = pathlib.Path(__file__).parent.parent / "playbooks"
    playbooks = [
        "autopilot.yaml",
        "autopilot-approved.yaml",
        "dependency-updater.yaml",
        "security-patch-updater.yaml",
        "thirdparty-autopilot-fix.yaml",
    ]
    for name in playbooks:
        text = (base_dir / name).read_text()
        wf = load_workflow_yaml(text, base_dir=base_dir)
        assert wf is not None, f"load_workflow_yaml returned None for {name}"
        assert wf.name, f"Workflow name empty for {name}"


# ---------------------------------------------------------------------------
# 9. extends key is stripped from the final model
# ---------------------------------------------------------------------------

def test_extends_stripped_from_model(tmp_path):
    base = _base_yaml()
    _write_base(tmp_path, base)

    child_yaml = _minimal_workflow("""\
        step_a:
          type: output
          label: Done
          output:
            via: slack
            slack:
              channel: "#eng"
    """)

    wf = load_workflow_yaml(child_yaml, base_dir=tmp_path)
    # Workflow.model_config has extra="ignore", so an 'extends' field would
    # silently be discarded. Verify it's not present on the dumped model either.
    dumped = wf.model_dump()
    assert "extends" not in dumped
