import importlib.util
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("phase2_revision_test", ROOT / "tools/federation/phase2_harness.py")
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


@pytest.mark.parametrize("revision", ["0154", "0158", "0159"])
def test_federation_revision_and_descendants_are_accepted(revision):
    harness.require_federation_schema(revision)


def test_current_head_remains_compatible():
    scripts = ScriptDirectory(str(ROOT / "apps/api/alembic"))
    harness.require_federation_schema(scripts.get_current_head())


@pytest.mark.parametrize("revision", ["0153", "0001", None, ""])
def test_old_or_unmigrated_schema_is_rejected(revision):
    with pytest.raises(AssertionError):
        harness.require_federation_schema(revision)
