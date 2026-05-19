"""
Tests for the YAML filename convention. The same logic is mirrored in
apps/web/src/lib/yaml-filename.ts; the table here is the spec for both.
"""
import pytest

from app.dsl import slugify_workflow_name, yaml_filename_for


@pytest.mark.parametrize(
    ("name", "expected_slug"),
    [
        ("AI-Ready Autopilot", "ai-ready-autopilot"),
        ("Marshal", "marshal"),
        ("  Deploy delegator   ", "deploy-delegator"),
        ("release_notes!!!", "release-notes"),
        ("Émile's repo", "mile-s-repo"),  # normalized basic ascii lowercase
        ("", "workflow"),
        (None, "workflow"),
        ("---", "workflow"),
    ],
)
def test_slugify_workflow_name(name, expected_slug):
    assert slugify_workflow_name(name) == expected_slug


def test_filename_appends_delegator_yml():
    assert yaml_filename_for("Autopilot") == "autopilot-delegator.yml"
    assert yaml_filename_for("") == "workflow-delegator.yml"


def test_filename_cap_at_80_chars():
    long_name = "x" * 200
    out = yaml_filename_for(long_name)
    # Slug capped at 80, plus "-delegator.yml" suffix.
    assert out.endswith("-delegator.yml")
    assert len(out.split("-delegator.yml")[0]) <= 80
