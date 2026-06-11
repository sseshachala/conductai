"""
Playbook regression suite — loads every playbook YAML through the DSL loader
and asserts it parses without error.

Run before and after any schema or loader change to catch regressions.

Known failures (tracked in GH issues, not schema bugs):
  bughunter-active-scan.yaml — uses for_each, prompt:/system: fields, and
    slash-format actions not yet in the DSL. Unblocked by #564 + #565.
"""
from pathlib import Path
import pytest
from app.dsl import load_workflow_yaml

PLAYBOOKS_DIR = Path(__file__).resolve().parent.parent / "playbooks"
PLAYBOOK_FILES = sorted(PLAYBOOKS_DIR.glob("*.yaml"))

# Playbooks that use DSL features not yet implemented — tracked in GH issues
XFAIL_PLAYBOOKS = {
    "bughunter-active-scan.yaml": "requires for_each + prompt:/system: fields (#564, #565)",
}


def _ids(files):
    return [f.name for f in files]


@pytest.mark.parametrize("playbook_path", PLAYBOOK_FILES, ids=_ids(PLAYBOOK_FILES))
def test_playbook_loads_without_error(playbook_path):
    """Every playbook must load and validate cleanly through the DSL."""
    reason = XFAIL_PLAYBOOKS.get(playbook_path.name)
    if reason:
        pytest.xfail(reason)

    yaml_text = playbook_path.read_text()
    workflow = load_workflow_yaml(yaml_text)
    assert workflow is not None, f"{playbook_path.name} returned None"
    assert workflow.blocks, f"{playbook_path.name} produced no blocks"


def test_all_playbooks_discovered():
    """Sanity check — at least 20 playbooks must exist or something is wrong."""
    assert len(PLAYBOOK_FILES) >= 20, (
        f"Only {len(PLAYBOOK_FILES)} playbooks found — expected at least 20"
    )
