"""
Fixture loader for the eval harness.

Every playbook YAML ships with a ``test_trigger`` section that provides a
realistic webhook payload.  This module reads that section and exposes it as
a typed :class:`PlaybookFixture`.

Additional fixture files (``eval/fixtures/<slug>.yaml``) can augment or
replace the embedded fixture when more detailed test scenarios are needed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Paths
PLAYBOOKS_DIR = Path(__file__).resolve().parent.parent / "playbooks"
FIXTURES_DIR  = Path(__file__).resolve().parent / "fixtures"


@dataclass
class PlaybookFixture:
    """One test case for a playbook."""

    slug: str
    """Snake-case identifier matching _OUTCOME_MAP keys (e.g. ``pr_reviewer``)."""

    playbook_path: Path
    """Absolute path to the source YAML file."""

    trigger_payload: dict[str, Any]
    """The simulated webhook / event payload."""

    initial_state: dict[str, Any] = field(default_factory=dict)
    """Pre-populated run state (inputs, environment overrides)."""

    expected_outcome_type: str | None = None
    """Expected ``outcome.type`` if run succeeds (from _OUTCOME_MAP)."""

    expected_artifact_keys: list[str] = field(default_factory=list)
    """Keys we expect to find in the final run state (e.g. ``pr_url``)."""

    extra_assertions: dict[str, Any] = field(default_factory=dict)
    """Playbook-specific assertions for the scorer rubric."""

    source: str = "embedded"
    """Where the fixture came from: ``embedded`` (test_trigger) or ``file``."""


def _slug_from_path(p: Path) -> str:
    """Convert ``pr-reviewer.yaml`` → ``pr_reviewer``."""
    return re.sub(r"[^a-z0-9]+", "_", p.stem.lower()).strip("_")


def load_fixtures(playbooks_dir: Path = PLAYBOOKS_DIR) -> list[PlaybookFixture]:
    """
    Load one fixture per playbook.

    Priority:
      1. ``eval/fixtures/<slug>.yaml`` (external override)
      2. ``test_trigger`` section embedded in the playbook YAML
    """
    fixtures: list[PlaybookFixture] = []

    for path in sorted(playbooks_dir.glob("*.yaml")):
        slug = _slug_from_path(path)
        raw = yaml.safe_load(path.read_text()) or {}

        # Attempt to load an external override fixture first
        ext_path = FIXTURES_DIR / f"{slug}.yaml"
        if ext_path.exists():
            ext = yaml.safe_load(ext_path.read_text()) or {}
            fixtures.append(_from_external(slug, path, ext))
            continue

        # Fall back to the embedded test_trigger section
        tt = raw.get("test_trigger") or {}
        payload = tt.get("payload") or {}

        # Pull expected assertions from the external fixtures directory if present
        assertions = tt.get("assertions") or {}

        # Derive expected outcome from the runtime's _OUTCOME_MAP at import time
        # so fixtures stay in sync with the executor automatically
        try:
            from app.runtime.executor import _OUTCOME_MAP
            entry = _OUTCOME_MAP.get(slug)
            outcome_type  = entry[0] if entry else None
            artifact_keys = list(entry[1]) if entry else []
        except ImportError:
            outcome_type  = None
            artifact_keys = []

        fixtures.append(PlaybookFixture(
            slug=slug,
            playbook_path=path,
            trigger_payload=payload,
            initial_state=tt.get("initial_state") or {},
            expected_outcome_type=outcome_type,
            expected_artifact_keys=artifact_keys,
            extra_assertions=assertions,
            source="embedded",
        ))

    return fixtures


def _from_external(slug: str, playbook_path: Path, data: dict) -> PlaybookFixture:
    """Build a PlaybookFixture from an external override YAML."""
    try:
        from app.runtime.executor import _OUTCOME_MAP
        entry = _OUTCOME_MAP.get(slug)
        outcome_type  = entry[0] if entry else None
        artifact_keys = list(entry[1]) if entry else []
    except ImportError:
        outcome_type  = data.get("expected_outcome_type")
        artifact_keys = data.get("expected_artifact_keys") or []

    return PlaybookFixture(
        slug=slug,
        playbook_path=playbook_path,
        trigger_payload=data.get("trigger_payload") or {},
        initial_state=data.get("initial_state") or {},
        expected_outcome_type=outcome_type,
        expected_artifact_keys=artifact_keys,
        extra_assertions=data.get("assertions") or {},
        source="file",
    )


def load_fixture(slug: str) -> PlaybookFixture | None:
    """Load the fixture for a single playbook by slug. Returns None if not found."""
    for f in load_fixtures():
        if f.slug == slug:
            return f
    return None
