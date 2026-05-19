"""
Round-trip tests: yaml -> graph -> yaml should preserve workflow semantics,
even though whitespace and formatting may differ. Covers every block type.
"""
from app.dsl import (
    graph_to_workflow,
    load_workflow_yaml,
    workflow_to_yaml,
    yaml_to_graph,
)


def _normalise(wf):
    """Strip default/None fields so two Workflow instances can be compared cleanly."""
    return wf.model_dump(by_alias=True, exclude_none=True, exclude_defaults=False)


def test_round_trip_preserves_simple_workflow():
    yaml_in = """
    name: simple
    on:
      manual:
        next: a
    blocks:
      a:
        type: tool
        integration: github
        action: fetch_issue
        params: { owner: o, repo: r, issue_number: 1 }
        next: b
      b:
        type: output
        output:
          via: slack
          slack: { channel: "#eng" }
    """
    wf1 = load_workflow_yaml(yaml_in)
    graph = yaml_to_graph(wf1)

    wf2 = graph_to_workflow(graph, name=wf1.name, description=wf1.description)
    assert _normalise(wf1)["blocks"] == _normalise(wf2)["blocks"]
    # `on:` survives via the alias
    assert "on" in _normalise(wf2)


def test_round_trip_preserves_logic_branches():
    yaml_in = """
    name: branched
    on:
      manual:
        next: gate
    blocks:
      gate:
        type: logic
        condition: "{{x.passed}} == true"
        next:
          pass: good
          fail: bad
      good:
        type: output
        output: { via: slack, slack: { channel: "#g" } }
      bad:
        type: output
        output: { via: slack, slack: { channel: "#b" } }
    """
    wf1 = load_workflow_yaml(yaml_in)
    graph = yaml_to_graph(wf1)
    wf2 = graph_to_workflow(graph, name=wf1.name)
    assert wf2.blocks["gate"].next == {"pass": "good", "fail": "bad"}


def test_round_trip_preserves_brain_runs_on():
    yaml_in = """
    name: remote
    on:
      manual:
        next: b
    blocks:
      b:
        type: brain
        mode: agentic
        description: do
        runs_on:
          ip: "{{wait.ip_address}}"
          credentials_from: digitalocean
    """
    wf1 = load_workflow_yaml(yaml_in)
    wf2 = graph_to_workflow(yaml_to_graph(wf1), name="remote")
    rh = wf2.blocks["b"].runs_on
    assert rh is not None
    assert rh.ip == "{{wait.ip_address}}"
    assert rh.credentials_from == "digitalocean"
    assert wf2.blocks["b"].mode == "agentic"


def test_round_trip_preserves_output_both():
    yaml_in = """
    name: out
    on:
      manual:
        next: o
    blocks:
      o:
        type: output
        output:
          via: both
          slack: { channel: "#x" }
          email: { to: "a@b.com" }
    """
    wf1 = load_workflow_yaml(yaml_in)
    wf2 = graph_to_workflow(yaml_to_graph(wf1), name="out")
    out = wf2.blocks["o"].output
    assert out is not None
    assert out.via == "both"
    assert out.slack.channel == "#x"
    assert out.email.to == "a@b.com"


def test_round_trip_preserves_cleanup():
    yaml_in = """
    name: with-cleanup
    on:
      manual:
        next: a
    blocks:
      a:
        type: tool
        integration: slack
        action: post_message
        params: { channel: "#x", text: hi }
    cleanup:
      c:
        type: tool
        integration: digitalocean
        action: destroy_droplet
        params: { droplet_id: 1 }
    """
    wf1 = load_workflow_yaml(yaml_in)
    wf2 = graph_to_workflow(yaml_to_graph(wf1), name="with-cleanup")
    assert "c" in wf2.cleanup
    assert wf2.cleanup["c"].action == "destroy_droplet"


def test_graph_to_workflow_then_emit_yaml_is_loadable():
    """End-to-end: graph -> workflow -> yaml string -> workflow again."""
    yaml_in = """
    name: e2e
    on:
      manual:
        next: a
    blocks:
      a:
        type: brain
        mode: single
        description: think
    """
    wf1 = load_workflow_yaml(yaml_in)
    graph = yaml_to_graph(wf1)
    wf2 = graph_to_workflow(graph, name="e2e")
    emitted = workflow_to_yaml(wf2)
    wf3 = load_workflow_yaml(emitted)
    assert wf3.name == "e2e"
    assert "a" in wf3.blocks
    assert wf3.blocks["a"].mode == "single"
