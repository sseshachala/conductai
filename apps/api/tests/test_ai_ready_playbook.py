"""
Loads the shipped playbook and confirms it parses, validates, and produces
a runtime-shaped graph with all the pieces the executor expects. Catches
regressions where a code change to the DSL silently breaks the demo workflow.
"""
from pathlib import Path

from app.dsl import load_workflow_yaml, yaml_to_graph
from app.dsl.loader import TRIGGER_NODE_ID

PLAYBOOK_PATH = (
    Path(__file__).resolve().parent.parent / "playbooks" / "ai_ready.yaml"
)


def test_ai_ready_playbook_parses():
    yaml_text = PLAYBOOK_PATH.read_text()
    wf = load_workflow_yaml(yaml_text)

    # Expected block ids — kept here intentionally so the playbook can't be
    # silently renamed without updating the test.
    assert set(wf.blocks.keys()) == {
        "fetch_issue",
        "create_droplet",
        "wait_droplet",
        "implement",
        "notify",
    }
    assert set(wf.cleanup.keys()) == {"destroy_droplet"}

    # The agentic Brain block must declare a remote host so it dispatches
    # over SSH instead of running locally.
    assert wf.blocks["implement"].mode == "agentic"
    assert wf.blocks["implement"].runs_on is not None


def test_ai_ready_playbook_graph_topology():
    yaml_text = PLAYBOOK_PATH.read_text()
    wf = load_workflow_yaml(yaml_text)
    g = yaml_to_graph(wf)

    edge_pairs = {(e["source"], e["target"]) for e in g["edges"]}
    # Trigger feeds the entry block
    assert (TRIGGER_NODE_ID, "fetch_issue") in edge_pairs
    # Linear chain through to notify
    chain = [
        ("fetch_issue", "create_droplet"),
        ("create_droplet", "wait_droplet"),
        ("wait_droplet", "implement"),
        ("implement", "notify"),
    ]
    for pair in chain:
        assert pair in edge_pairs, f"missing edge {pair}"

    # The cleanup block must not have inbound or outbound edges in the main DAG
    for src, tgt in edge_pairs:
        assert src != "destroy_droplet"
        assert tgt != "destroy_droplet"


def test_ai_ready_brain_block_remote_host_in_graph():
    """The graph projection must put runs_on under data.config.remote_host."""
    yaml_text = PLAYBOOK_PATH.read_text()
    wf = load_workflow_yaml(yaml_text)
    g = yaml_to_graph(wf)
    brain = next(n for n in g["nodes"] if n["id"] == "implement")
    cfg = brain["data"]["config"]
    assert "remote_host" in cfg
    assert cfg["remote_host"]["ip_ref"].startswith("{{wait_droplet")
    assert cfg["remote_host"]["credentials_from"] == "digitalocean"
