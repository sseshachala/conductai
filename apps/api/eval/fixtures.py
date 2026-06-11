"""
Fixture loader for the eval harness.

Every playbook YAML ships with a ``test_trigger`` section that provides a
realistic webhook payload.  This module reads that section and exposes it as
a typed :class:`PlaybookFixture`.

Additional fixture files (``eval/fixtures/<slug>.yaml``) can augment or
replace the embedded fixture when more detailed test scenarios are needed.
Two YAML formats are supported:

Single-scenario (legacy / simple):
  trigger_payload: {...}
  initial_state: {...}
  expected_outcome_type: reviewed
  expected_artifact_keys: [review_url]
  assertions: {...}

Multi-scenario (preferred for priority playbooks):
  slug: pr_reviewer
  description: "..."
  scenarios:
    - id: clean_pr
      label: "Clean PR"
      tags: [positive]
      trigger_payload: {...}
      initial_state: {}
      expected_outcome_type: reviewed
      expected_artifact_keys: [review_url]
      extra_assertions: {}
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
    """One test case for a playbook (primary / representative scenario)."""

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

    scenario_count: int = 1
    """Total number of scenarios available (1 for embedded, N for multi-scenario files)."""

    scenario_tags: list[str] = field(default_factory=list)
    """Aggregated tags from all scenarios (e.g. [positive, negative, security])."""


@dataclass
class FixtureScenario:
    """A single named scenario within a multi-scenario fixture set."""

    id: str
    """Short slug for the scenario (e.g. ``clean_pr``, ``draft_pr``)."""

    label: str
    """Human-readable description of the scenario."""

    playbook_slug: str
    """Parent playbook slug."""

    playbook_path: Path
    """Absolute path to the source playbook YAML."""

    trigger_payload: dict[str, Any]
    """The simulated webhook / event payload for this scenario."""

    initial_state: dict[str, Any] = field(default_factory=dict)
    """Pre-populated run state."""

    expected_outcome_type: str | None = None
    """Expected outcome type (from _OUTCOME_MAP), or None for negative cases."""

    expected_artifact_keys: list[str] = field(default_factory=list)
    """Keys expected in final state."""

    extra_assertions: dict[str, Any] = field(default_factory=dict)
    """Scenario-specific assertions for the scorer."""

    tags: list[str] = field(default_factory=list)
    """Classification tags: positive, negative, security, scale, etc."""

    expected_should_review: bool | None = None
    """For reviewer playbooks: whether the playbook should post a review."""

    expected_should_scan: bool | None = None
    """For scanner playbooks: whether the playbook should perform a scan."""


@dataclass
class ScenarioSet:
    """All scenarios for a single playbook, loaded from an external fixture file."""

    slug: str
    """Playbook slug."""

    playbook_path: Path
    """Absolute path to source YAML."""

    description: str
    """Human-readable description of the fixture set."""

    scenarios: list[FixtureScenario]
    """All named scenarios — order matches the file."""

    @property
    def positive_scenarios(self) -> list[FixtureScenario]:
        return [s for s in self.scenarios if "negative" not in s.tags]

    @property
    def negative_scenarios(self) -> list[FixtureScenario]:
        return [s for s in self.scenarios if "negative" in s.tags]

    @property
    def primary(self) -> FixtureScenario | None:
        """Return the first positive scenario as the representative case."""
        pos = self.positive_scenarios
        return pos[0] if pos else (self.scenarios[0] if self.scenarios else None)

    def to_fixture(self) -> PlaybookFixture | None:
        """Convert to a PlaybookFixture for use with the existing runner."""
        primary = self.primary
        if primary is None:
            return None

        all_tags: list[str] = []
        for s in self.scenarios:
            for t in s.tags:
                if t not in all_tags:
                    all_tags.append(t)

        return PlaybookFixture(
            slug=self.slug,
            playbook_path=self.playbook_path,
            trigger_payload=primary.trigger_payload,
            initial_state=primary.initial_state,
            expected_outcome_type=primary.expected_outcome_type,
            expected_artifact_keys=primary.expected_artifact_keys,
            extra_assertions=primary.extra_assertions,
            source="file",
            scenario_count=len(self.scenarios),
            scenario_tags=all_tags,
        )


# ── slug helpers ──────────────────────────────────────────────────────────────

def _slug_from_path(p: Path) -> str:
    """Convert ``pr-reviewer.yaml`` to ``pr_reviewer``."""
    return re.sub(r"[^a-z0-9]+", "_", p.stem.lower()).strip("_")


# ── outcome map helper ────────────────────────────────────────────────────────

def _outcome_for_slug(slug: str) -> tuple[str | None, list[str]]:
    """Return (outcome_type, artifact_keys) from _OUTCOME_MAP, or (None, [])."""
    try:
        from app.runtime.executor import _OUTCOME_MAP
        entry = _OUTCOME_MAP.get(slug)
        if entry:
            return entry[0], list(entry[1])
    except ImportError:
        pass
    return None, []


# ── public loaders ────────────────────────────────────────────────────────────

def load_fixtures(playbooks_dir: Path = PLAYBOOKS_DIR) -> list[PlaybookFixture]:
    """
    Load one fixture per playbook.

    Priority:
      1. ``eval/fixtures/<slug>.yaml`` (external override, single- or multi-scenario)
      2. ``test_trigger`` section embedded in the playbook YAML
    """
    fixtures: list[PlaybookFixture] = []

    for path in sorted(p for p in playbooks_dir.glob("*.yaml") if p.name != "registry.yaml"):
        slug = _slug_from_path(path)
        raw = yaml.safe_load(path.read_text()) or {}

        # Attempt to load an external override fixture first
        ext_path = FIXTURES_DIR / f"{slug}.yaml"
        if ext_path.exists():
            ext = yaml.safe_load(ext_path.read_text()) or {}
            if "scenarios" in ext:
                # Multi-scenario format: extract primary scenario as PlaybookFixture
                scenario_set = _scenario_set_from_yaml(slug, path, ext)
                fixture = scenario_set.to_fixture()
                if fixture:
                    fixtures.append(fixture)
            else:
                # Legacy single-scenario override
                fixtures.append(_from_external(slug, path, ext))
            continue

        # Fall back to the embedded test_trigger section
        tt = raw.get("test_trigger") or {}
        payload = tt.get("payload") or {}
        assertions = tt.get("assertions") or {}

        outcome_type, artifact_keys = _outcome_for_slug(slug)

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


def load_fixture(slug: str) -> PlaybookFixture | None:
    """Load the primary fixture for a single playbook by slug. Returns None if not found."""
    for f in load_fixtures():
        if f.slug == slug:
            return f
    return None


def load_scenario_set(slug: str) -> ScenarioSet | None:
    """
    Load the full scenario set for a playbook.

    Returns a :class:`ScenarioSet` if the playbook has a multi-scenario fixture
    file in ``eval/fixtures/<slug>.yaml``, otherwise returns None.
    """
    ext_path = FIXTURES_DIR / f"{slug}.yaml"
    if not ext_path.exists():
        return None

    ext = yaml.safe_load(ext_path.read_text()) or {}
    if "scenarios" not in ext:
        return None

    # Find the playbook path
    playbook_path: Path | None = None
    for path in sorted(PLAYBOOKS_DIR.glob("*.yaml")):
        if _slug_from_path(path) == slug:
            playbook_path = path
            break

    if playbook_path is None:
        return None

    return _scenario_set_from_yaml(slug, playbook_path, ext)


def list_scenario_sets() -> list[ScenarioSet]:
    """Return all playbooks that have multi-scenario fixture files."""
    sets: list[ScenarioSet] = []
    for path in sorted(FIXTURES_DIR.glob("*.yaml")):
        slug = _slug_from_path(path)
        scenario_set = load_scenario_set(slug)
        if scenario_set:
            sets.append(scenario_set)
    return sets


# ── internal builders ─────────────────────────────────────────────────────────

def _scenario_set_from_yaml(
    slug: str,
    playbook_path: Path,
    data: dict,
) -> ScenarioSet:
    """Build a ScenarioSet from the multi-scenario YAML format."""
    outcome_type, artifact_keys = _outcome_for_slug(slug)
    scenarios: list[FixtureScenario] = []

    for raw_s in data.get("scenarios", []):
        # Per-scenario outcome override (negative cases may be None)
        s_outcome = raw_s.get("expected_outcome_type", outcome_type)
        s_artifacts = raw_s.get("expected_artifact_keys") or artifact_keys

        scenarios.append(FixtureScenario(
            id=raw_s.get("id", f"scenario_{len(scenarios) + 1}"),
            label=raw_s.get("label", ""),
            playbook_slug=slug,
            playbook_path=playbook_path,
            trigger_payload=raw_s.get("trigger_payload") or {},
            initial_state=raw_s.get("initial_state") or {},
            expected_outcome_type=s_outcome,
            expected_artifact_keys=list(s_artifacts) if s_artifacts else [],
            extra_assertions=raw_s.get("extra_assertions") or {},
            tags=raw_s.get("tags") or [],
            expected_should_review=raw_s.get("expected_should_review"),
            expected_should_scan=raw_s.get("expected_should_scan"),
        ))

    return ScenarioSet(
        slug=slug,
        playbook_path=playbook_path,
        description=data.get("description", ""),
        scenarios=scenarios,
    )


def _from_external(slug: str, playbook_path: Path, data: dict) -> PlaybookFixture:
    """Build a PlaybookFixture from a legacy single-scenario external YAML."""
    outcome_type, artifact_keys = _outcome_for_slug(slug)
    if not outcome_type:
        outcome_type = data.get("expected_outcome_type")
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
