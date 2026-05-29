"""
Ensure the autopilot YAML playbook (the port of seed_autopilot.py) parses,
validates, and produces the expected DAG topology.
"""
from pathlib import Path

from app.dsl import load_workflow_yaml, yaml_to_graph
from app.dsl.loader import TRIGGER_NODE_ID

PLAYBOOK = (
    Path(__file__).resolve().parent.parent / "playbooks" / "autopilot.yaml"
)


def test_autopilot_parses():
    wf = load_workflow_yaml(PLAYBOOK.read_text())
    assert wf.name.lower().startswith("autopilot")
    # These are the core required blocks; the playbook may add more (memory, output, etc.)
    required = {"fetch_issue", "implement_fix", "run_tests", "tests_pass", "push_pr"}
    assert required.issubset(set(wf.blocks.keys())), (
        f"Missing blocks: {required - set(wf.blocks.keys())}"
    )


def test_autopilot_branches_on_test_result():
    wf = load_workflow_yaml(PLAYBOOK.read_text())
    g = yaml_to_graph(wf)
    handle_edges = [e for e in g["edges"] if "sourceHandle" in e]
    handles = {e["sourceHandle"]: e["target"] for e in handle_edges}
    assert handles == {"pass": "push_pr", "fail": "notify_failure"}


def test_autopilot_trigger_feeds_first_block():
    wf = load_workflow_yaml(PLAYBOOK.read_text())
    g = yaml_to_graph(wf)
    # The trigger must connect to the first block (may be recall_context or fetch_issue)
    trigger_targets = {e["target"] for e in g["edges"] if e["source"] == TRIGGER_NODE_ID}
    assert trigger_targets, "Trigger has no outgoing edges"
    # The first block should eventually reach fetch_issue
    pairs = {(e["source"], e["target"]) for e in g["edges"]}
    reachable_from_trigger = set()
    queue = list(trigger_targets)
    while queue:
        node = queue.pop()
        if node in reachable_from_trigger:
            continue
        reachable_from_trigger.add(node)
        queue.extend(t for s, t in pairs if s == node)
    assert "fetch_issue" in reachable_from_trigger
