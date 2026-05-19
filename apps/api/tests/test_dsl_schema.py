"""
Schema validation tests for the YAML DSL. These are pure Python — no DB, no
network — and cover the structural rules that we want to fail loudly at load
time rather than at run time.
"""
import pytest

from app.dsl import Workflow, WorkflowValidationError, load_workflow_yaml


# ---------------------------------------------------------------------------
# Happy-path: minimal valid workflow
# ---------------------------------------------------------------------------
MINIMAL_YAML = """
name: hello
on:
  manual:
    next: greet
blocks:
  greet:
    type: output
    output:
      via: slack
      slack:
        channel: "#general"
"""


def test_minimal_workflow_parses():
    wf = load_workflow_yaml(MINIMAL_YAML)
    assert isinstance(wf, Workflow)
    assert wf.name == "hello"
    assert wf.entry_block_id() == "greet"


# ---------------------------------------------------------------------------
# Structural errors
# ---------------------------------------------------------------------------
def test_invalid_yaml_raises_workflow_validation_error():
    with pytest.raises(WorkflowValidationError):
        load_workflow_yaml(":\n  : not yaml :")


def test_top_level_must_be_mapping():
    with pytest.raises(WorkflowValidationError):
        load_workflow_yaml("- just a list\n- of strings\n")


def test_missing_name_is_rejected():
    with pytest.raises(WorkflowValidationError):
        load_workflow_yaml(
            """
            blocks:
              x:
                type: output
                output:
                  via: slack
                  slack: { channel: "#x" }
            """
        )


def test_unknown_block_type_is_rejected():
    yaml = """
    name: bad
    blocks:
      x:
        type: not-a-real-type
    """
    with pytest.raises(WorkflowValidationError):
        load_workflow_yaml(yaml)


def test_next_pointing_to_unknown_block_is_rejected():
    yaml = """
    name: bad-route
    blocks:
      a:
        type: tool
        integration: slack
        action: post_message
        params: { channel: "#x", text: hi }
        next: nowhere
    """
    with pytest.raises(WorkflowValidationError):
        load_workflow_yaml(yaml)


# ---------------------------------------------------------------------------
# Per-block-type rules
# ---------------------------------------------------------------------------
def test_tool_block_requires_integration_and_action():
    yaml = """
    name: t
    blocks:
      a:
        type: tool
        params: {}
    """
    with pytest.raises(WorkflowValidationError):
        load_workflow_yaml(yaml)


def test_brain_block_requires_description():
    yaml = """
    name: t
    blocks:
      a:
        type: brain
        mode: agentic
    """
    with pytest.raises(WorkflowValidationError):
        load_workflow_yaml(yaml)


def test_logic_block_requires_pass_fail_routing():
    yaml = """
    name: t
    blocks:
      a:
        type: logic
        condition: "{{x.passed}} == true"
        next: only_one
      only_one:
        type: output
        output: { via: slack, slack: { channel: "#x" } }
    """
    with pytest.raises(WorkflowValidationError):
        load_workflow_yaml(yaml)


def test_logic_block_with_pass_fail_passes():
    yaml = """
    name: t
    blocks:
      a:
        type: logic
        condition: "{{x.passed}} == true"
        next:
          pass: ok
          fail: notok
      ok:
        type: output
        output: { via: slack, slack: { channel: "#x" } }
      notok:
        type: output
        output: { via: slack, slack: { channel: "#x" } }
    """
    wf = load_workflow_yaml(yaml)
    assert wf.blocks["a"].next == {"pass": "ok", "fail": "notok"}


def test_output_block_requires_channels_for_via_both():
    yaml = """
    name: t
    blocks:
      a:
        type: output
        output:
          via: both
          slack: { channel: "#x" }
          # missing email
    """
    with pytest.raises(WorkflowValidationError):
        load_workflow_yaml(yaml)


def test_approval_block_requires_destination():
    yaml = """
    name: t
    blocks:
      a:
        type: approval
        message: "approve?"
    """
    with pytest.raises(WorkflowValidationError):
        load_workflow_yaml(yaml)


# ---------------------------------------------------------------------------
# Brain + runs_on (remote host) parses cleanly
# ---------------------------------------------------------------------------
def test_brain_with_runs_on():
    yaml = """
    name: remote-demo
    on:
      manual:
        next: b
    blocks:
      b:
        type: brain
        mode: agentic
        description: "do the thing"
        runs_on:
          ip: "{{wait.ip_address}}"
          credentials_from: digitalocean
    """
    wf = load_workflow_yaml(yaml)
    rh = wf.blocks["b"].runs_on
    assert rh is not None
    assert rh.ip == "{{wait.ip_address}}"
    assert rh.credentials_from == "digitalocean"
