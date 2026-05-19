"""
Loader tests — verifies the YAML → graph translation produces nodes/edges in
the exact shape the executor consumes today.
"""
from app.dsl import load_workflow_yaml, workflow_to_yaml, yaml_to_graph
from app.dsl.loader import TRIGGER_NODE_ID


SIMPLE_YAML = """
name: simple
on:
  manual:
    integration: github
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
      slack: { channel: "#engineering" }
cleanup:
  c:
    type: tool
    integration: digitalocean
    action: destroy_droplet
    params: { droplet_id: 1 }
"""


def test_yaml_to_graph_shape():
    wf = load_workflow_yaml(SIMPLE_YAML)
    g = yaml_to_graph(wf)

    assert set(g.keys()) == {"nodes", "edges"}
    nodes_by_id = {n["id"]: n for n in g["nodes"]}

    # Trigger is materialised as a synthetic node
    assert TRIGGER_NODE_ID in nodes_by_id
    assert nodes_by_id[TRIGGER_NODE_ID]["data"]["type"] == "trigger"

    # Cleanup block is tagged as cleanup, not as its underlying tool type
    assert "c" in nodes_by_id
    assert nodes_by_id["c"]["data"]["type"] == "cleanup"

    # Edges are produced for trigger -> entry and explicit next:
    edge_pairs = {(e["source"], e["target"]) for e in g["edges"]}
    assert (TRIGGER_NODE_ID, "a") in edge_pairs
    assert ("a", "b") in edge_pairs

    # Cleanup blocks should not produce edges into the main DAG
    for src, tgt in edge_pairs:
        assert tgt != "c", "cleanup should not be a routing target"


def test_logic_routing_produces_handles():
    yaml = """
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
    wf = load_workflow_yaml(yaml)
    g = yaml_to_graph(wf)
    handle_edges = [e for e in g["edges"] if "sourceHandle" in e]
    assert len(handle_edges) == 2
    handles = {e["sourceHandle"]: e["target"] for e in handle_edges}
    assert handles == {"pass": "good", "fail": "bad"}


def test_brain_runs_on_maps_to_remote_host_config():
    """
    The runtime's executor reads remote_host from block.data.config; verify the
    loader writes it there using the ip_ref / credentials_from contract.
    """
    yaml = """
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
    wf = load_workflow_yaml(yaml)
    g = yaml_to_graph(wf)
    brain = next(n for n in g["nodes"] if n["id"] == "b")
    rh = brain["data"]["config"]["remote_host"]
    assert rh["ip_ref"] == "{{wait.ip_address}}"
    assert rh["credentials_from"] == "digitalocean"
    assert brain["data"]["isAgentic"] is True


def test_output_via_both_writes_channel_and_to():
    """The runtime reads channel + to from config; loader must populate both."""
    yaml = """
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
    wf = load_workflow_yaml(yaml)
    g = yaml_to_graph(wf)
    out = next(n for n in g["nodes"] if n["id"] == "o")
    cfg = out["data"]["config"]
    assert cfg["channel"] == "#x"
    assert cfg["to"] == "a@b.com"
    assert cfg["integration"] == "both"
    assert out["data"]["integration"] == "both"


def test_round_trip_via_workflow_to_yaml_is_valid_yaml():
    """A parsed workflow should serialise back to YAML that re-parses cleanly."""
    wf = load_workflow_yaml(SIMPLE_YAML)
    yaml_out = workflow_to_yaml(wf)
    wf2 = load_workflow_yaml(yaml_out)
    assert wf2.name == wf.name
    assert set(wf2.blocks) == set(wf.blocks)
