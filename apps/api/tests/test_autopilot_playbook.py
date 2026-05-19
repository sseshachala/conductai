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
    assert set(wf.blocks.keys()) == {
        "fetch_issue",
        "implement_fix",
        "run_tests",
        "tests_pass",
        "push_pr",
        "notify_success",
        "notify_failure",
    }


def test_autopilot_branches_on_test_result():
    wf = load_workflow_yaml(PLAYBOOK.read_text())
    g = yaml_to_graph(wf)
    handle_edges = [e for e in g["edges"] if "sourceHandle" in e]
    handles = {e["sourceHandle"]: e["target"] for e in handle_edges}
    assert handles == {"pass": "push_pr", "fail": "notify_failure"}


def test_autopilot_trigger_feeds_fetch_issue():
    wf = load_workflow_yaml(PLAYBOOK.read_text())
    g = yaml_to_graph(wf)
    pairs = {(e["source"], e["target"]) for e in g["edges"]}
    assert (TRIGGER_NODE_ID, "fetch_issue") in pairs
