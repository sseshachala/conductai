"""
Scoring rubrics for the Conduct eval harness.

Each playbook is scored against a set of weighted criteria.  The maximum
possible score is 100.  Criteria are divided into two tiers:

Structural (offline, ~0ms)
  Applied to the raw YAML without executing any blocks.  Safe to run in CI.

Quality (live, requires LLM)
  Applied after a real execution run.  Only evaluated when live mode is on.

Score breakdown
---------------
  DSL validation             20 pts  — YAML parses; Pydantic schema passes
  Trigger wired              10 pts  — trigger.next points to a real block
  All blocks reachable        8 pts  — no orphan blocks in the DAG
  Brain descriptions present  7 pts  — every brain block has non-empty description
  Output contract: JSON       8 pts  — brain blocks end with a JSON line contract
  Output block present        5 pts  — at least one output/notify block
  Logic branches complete     7 pts  — every logic block has both pass + fail
  Test fixture present       10 pts  — test_trigger section embedded in YAML
  Outcome map entry           8 pts  — slug appears in _OUTCOME_MAP
  Model input declared        5 pts  — model input configured for LLM blocks
  No empty block labels       4 pts  — every block has a human-readable label
  Memory write after brain    4 pts  — important results written to memory
  No dead-end blocks          4 pts  — every non-terminal block has next:
  ─────────────────────────────────
  Structural subtotal       100 pts

Quality criteria (only when live=True)
  Run succeeded               15 pts  — run.status == "succeeded"
  Outcome detected            10 pts  — _detect_outcome returned non-None
  Artifact produced           10 pts  — artifact URL found in state (if required)
  Brain output parseable      10 pts  — last-line JSON parsed successfully
  Token budget respected       5 pts  — total tokens < 50 000 per run
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import yaml


# ── data classes ──────────────────────────────────────────────────────────────

@dataclass
class CriterionResult:
    name: str
    passed: bool
    points_earned: int
    points_possible: int
    detail: str = ""


@dataclass
class PlaybookScore:
    slug: str
    structural_score: int       = 0
    structural_max: int         = 100      # recomputed dynamically at end of score_structural
    quality_score: int          = 0
    quality_max: int            = 0        # 0 unless live mode was run
    criteria: list[CriterionResult] = field(default_factory=list)

    @property
    def total_score(self) -> int:
        return self.structural_score + self.quality_score

    @property
    def total_max(self) -> int:
        return self.structural_max + self.quality_max

    @property
    def grade(self) -> str:
        pct = (self.total_score / self.total_max * 100) if self.total_max else 0
        if pct >= 90: return "A"
        if pct >= 80: return "B"
        if pct >= 70: return "C"
        if pct >= 60: return "D"
        return "F"

    @property
    def pct(self) -> float:
        return (self.total_score / self.total_max * 100) if self.total_max else 0.0

    def failing_criteria(self) -> list[CriterionResult]:
        return [c for c in self.criteria if not c.passed]


# ── helpers ───────────────────────────────────────────────────────────────────

_JSON_LAST_LINE = re.compile(
    r'\{[^}]+\}\s*$',
    re.MULTILINE | re.DOTALL,
)


def _block_ids_reachable(graph: dict) -> set[str]:
    """BFS from _trigger to find all reachable block IDs."""
    adj: dict[str, set[str]] = {}
    for edge in graph.get("edges", []):
        adj.setdefault(edge["source"], set()).add(edge["target"])
    visited: set[str] = set()
    queue = ["_trigger"]
    while queue:
        node = queue.pop()
        if node in visited:
            continue
        visited.add(node)
        queue.extend(adj.get(node, set()))
    return visited


# ── slug-specific rubrics ─────────────────────────────────────────────────────
#
# Each entry is a list of check dicts with keys:
#   name        — criterion key
#   check       — callable(wf, blocks) -> bool
#   detail_pass — message when check passes
#   detail_fail — message when check fails
#   points      — bonus points (5 each)
#
# These are appended to the universal criteria list only when the playbook
# slug matches.  structural_max is recomputed after they are applied.

def _brain_desc_contains(blocks: dict, keyword: str) -> bool:
    """True if any brain block description contains *keyword*."""
    for v in blocks.values():
        if v.get("type") == "brain":
            if keyword in (v.get("description") or ""):
                return True
    return False


def _brain_output_has_key(blocks: dict, *keys: str) -> bool:
    """True if any brain block description mentions all *keys* in a JSON-like contract."""
    for v in blocks.values():
        if v.get("type") == "brain":
            desc = v.get("description") or ""
            if all(f'"{k}"' in desc for k in keys):
                return True
    return False


def _logic_condition_contains(blocks: dict, keyword: str) -> bool:
    """True if any logic block condition string contains *keyword*."""
    for v in blocks.values():
        if v.get("type") == "logic":
            cond = str(v.get("condition") or v.get("expression") or "")
            if keyword in cond:
                return True
    return False


_AUTOPILOT_SLUGS = {"autopilot", "autopilot_quick", "autopilot_approved", "autopilot_full", "ai_ready"}
_AUTOPILOT_TEST_SLUGS = {"autopilot", "autopilot_approved", "autopilot_full"}  # quick intentionally skips tests
_REVIEWER_SLUGS = {"pr_reviewer", "copilot_reviewer"}

_SLUG_RUBRICS: dict[str, list[dict]] = {
    slug: [
        {
            "name": "autopilot_outputs_pr_url",
            "check": lambda _wf, blocks: _brain_desc_contains(blocks, '"pr_url"'),
            "detail_pass": "Brain block description mentions pr_url in its JSON contract",
            "detail_fail": 'Brain block description missing "pr_url" in JSON contract',
            "points": 5,
        },
    ]
    for slug in _AUTOPILOT_SLUGS
}

for _slug in _AUTOPILOT_TEST_SLUGS:
    _SLUG_RUBRICS.setdefault(_slug, []).append({
        "name": "autopilot_has_test_logic",
        "check": lambda _wf, blocks: (
            _logic_condition_contains(blocks, "tests_pass")
            or _logic_condition_contains(blocks, "passed")
        ),
        "detail_pass": "Logic block condition references tests_pass or passed",
        "detail_fail": "No logic block with tests_pass or passed in condition found",
        "points": 5,
    })

for _slug in _REVIEWER_SLUGS:
    _SLUG_RUBRICS.setdefault(_slug, []).extend([
        {
            "name": "reviewer_outputs_critical_count",
            "check": lambda _wf, blocks: _brain_output_has_key(blocks, "critical"),
            "detail_pass": 'Brain block outputs JSON with "critical" key',
            "detail_fail": 'Brain block missing "critical" key in JSON contract',
            "points": 5,
        },
        {
            "name": "reviewer_has_critical_logic",
            "check": lambda _wf, blocks: _logic_condition_contains(blocks, "critical"),
            "detail_pass": "Logic block condition references critical",
            "detail_fail": "No logic block with critical in condition found",
            "points": 5,
        },
    ])

_SLUG_RUBRICS["security_scanner"] = [
    {
        "name": "scanner_outputs_severity_counts",
        "check": lambda _wf, blocks: _brain_output_has_key(blocks, "critical", "high", "medium"),
        "detail_pass": 'Brain block outputs JSON with "critical", "high", "medium" keys',
        "detail_fail": 'Brain block missing severity count keys in JSON contract',
        "points": 5,
    },
]

_SLUG_RUBRICS["issue_triage"] = [
    {
        "name": "triage_outputs_type_priority",
        "check": lambda _wf, blocks: _brain_output_has_key(blocks, "type", "priority"),
        "detail_pass": 'Brain block outputs JSON with "type" and "priority" keys',
        "detail_fail": 'Brain block missing "type" or "priority" key in JSON contract',
        "points": 5,
    },
]

for _slug in ("flaky_test_detective", "postmortem_drafter"):
    _SLUG_RUBRICS[_slug] = [
        {
            "name": "outputs_issue_url",
            "check": lambda _wf, blocks: _brain_desc_contains(blocks, '"issue_url"'),
            "detail_pass": "Brain block description mentions issue_url",
            "detail_fail": 'Brain block description missing "issue_url" in JSON contract',
            "points": 5,
        },
    ]

for _slug in ("dependency_updater", "security_patch_updater"):
    _SLUG_RUBRICS[_slug] = [
        {
            "name": "outputs_pr_url",
            "check": lambda _wf, blocks: _brain_desc_contains(blocks, '"pr_url"'),
            "detail_pass": "Brain block description mentions pr_url",
            "detail_fail": 'Brain block description missing "pr_url" in JSON contract',
            "points": 5,
        },
    ]


# ── structural scoring ────────────────────────────────────────────────────────

def score_structural(playbook_yaml: str, slug: str) -> PlaybookScore:
    """
    Run all structural checks on a raw YAML string.
    Returns a fully-populated PlaybookScore (quality fields left at 0).
    """
    score = PlaybookScore(slug=slug)

    # ── 1. DSL validation (20 pts) ───────────────────────────────────────────
    try:
        from app.dsl import load_workflow_yaml, yaml_to_graph
        wf = load_workflow_yaml(playbook_yaml)
        graph = yaml_to_graph(wf)
        score.criteria.append(CriterionResult(
            name="dsl_valid", passed=True, points_earned=20, points_possible=20,
            detail="YAML parses and schema validates cleanly",
        ))
    except Exception as exc:
        score.criteria.append(CriterionResult(
            name="dsl_valid", passed=False, points_earned=0, points_possible=20,
            detail=f"Validation error: {exc}",
        ))
        # Cannot continue without a valid graph
        score.structural_score = 0
        return score

    raw = yaml.safe_load(playbook_yaml) or {}
    blocks: dict[str, Any] = raw.get("blocks", {})
    block_ids = set(blocks.keys())
    brain_blocks = {k: v for k, v in blocks.items() if v.get("type") == "brain"}
    logic_blocks = {k: v for k, v in blocks.items() if v.get("type") == "logic"}
    output_blocks = {k: v for k, v in blocks.items() if v.get("type") == "output"}
    memory_blocks = {k: v for k, v in blocks.items() if v.get("type") == "memory"}

    # ── 2. Trigger wired (10 pts) ────────────────────────────────────────────
    # Use the validated wf.triggers dict — the DSL loader already handled the
    # YAML 1.1 quirk where bare `on:` parses as Python True instead of "on".
    first_block: str | None = None
    for _event, trigger_obj in (wf.triggers or {}).items():
        nxt = getattr(trigger_obj, "next", None)
        if nxt:
            first_block = nxt
            break
    if first_block and first_block in block_ids:
        score.criteria.append(CriterionResult(
            name="trigger_wired", passed=True, points_earned=10, points_possible=10,
            detail=f"Trigger routes to '{first_block}'",
        ))
    else:
        score.criteria.append(CriterionResult(
            name="trigger_wired", passed=False, points_earned=0, points_possible=10,
            detail=f"Trigger next='{first_block}' not found in blocks",
        ))

    # ── 3. All blocks reachable (8 pts) ──────────────────────────────────────
    reachable = _block_ids_reachable(graph)
    # _trigger itself is synthetic; real blocks are those in block_ids
    unreachable = block_ids - reachable
    if not unreachable:
        score.criteria.append(CriterionResult(
            name="no_orphan_blocks", passed=True, points_earned=8, points_possible=8,
            detail="All blocks reachable from trigger",
        ))
    else:
        score.criteria.append(CriterionResult(
            name="no_orphan_blocks", passed=False, points_earned=0, points_possible=8,
            detail=f"Orphan blocks: {sorted(unreachable)}",
        ))

    # ── 4. Brain descriptions present (7 pts) ────────────────────────────────
    # Accept description:, system:, or prompt: as equivalent description fields
    def _brain_desc(v: dict) -> str:
        return (v.get("description") or v.get("system") or v.get("prompt") or "").strip()

    missing_desc = [
        k for k, v in brain_blocks.items()
        if not _brain_desc(v)
    ]
    if not missing_desc:
        score.criteria.append(CriterionResult(
            name="brain_descriptions", passed=True, points_earned=7, points_possible=7,
            detail=f"All {len(brain_blocks)} brain block(s) have descriptions",
        ))
    else:
        score.criteria.append(CriterionResult(
            name="brain_descriptions", passed=False, points_earned=0, points_possible=7,
            detail=f"Brain blocks missing description: {missing_desc}",
        ))

    # ── 5. Output contract: last-line JSON (8 pts) ────────────────────────────
    def _has_json_contract(v: dict) -> bool:
        for field in ("description", "system", "prompt"):
            text = (v.get(field) or "").strip()
            if re.search(r'\{[^}]*"[a-z_]+"\s*:', text):
                return True
        return False

    contracts_missing = []
    for k, v in brain_blocks.items():
        if not _has_json_contract(v):
            contracts_missing.append(k)
    if not contracts_missing:
        score.criteria.append(CriterionResult(
            name="output_contract_json", passed=True, points_earned=8, points_possible=8,
            detail="All brain blocks declare a JSON output contract",
        ))
    else:
        score.criteria.append(CriterionResult(
            name="output_contract_json", passed=False,
            points_earned=max(0, 8 - len(contracts_missing) * 2),
            points_possible=8,
            detail=f"Brain blocks missing JSON contract: {contracts_missing}",
        ))

    # ── 6. Output block present (5 pts) ──────────────────────────────────────
    if output_blocks:
        score.criteria.append(CriterionResult(
            name="output_block_present", passed=True, points_earned=5, points_possible=5,
            detail=f"Output blocks: {list(output_blocks.keys())}",
        ))
    else:
        score.criteria.append(CriterionResult(
            name="output_block_present", passed=False, points_earned=0, points_possible=5,
            detail="No output block found — playbook is silent",
        ))

    # ── 7. Logic branches complete (7 pts) ────────────────────────────────────
    incomplete_logic = []
    for k, v in logic_blocks.items():
        nxt = v.get("next")
        if not isinstance(nxt, dict) or "pass" not in nxt or "fail" not in nxt:
            incomplete_logic.append(k)
    if not incomplete_logic:
        score.criteria.append(CriterionResult(
            name="logic_branches_complete", passed=True, points_earned=7, points_possible=7,
            detail=f"All {len(logic_blocks)} logic block(s) have both pass and fail branches",
        ))
    else:
        score.criteria.append(CriterionResult(
            name="logic_branches_complete", passed=False, points_earned=0, points_possible=7,
            detail=f"Logic blocks with incomplete routing: {incomplete_logic}",
        ))

    # ── 8. Test fixture present (10 pts) ─────────────────────────────────────
    has_fixture = bool(raw.get("test_trigger") and raw["test_trigger"].get("payload"))
    score.criteria.append(CriterionResult(
        name="test_fixture_present", passed=has_fixture,
        points_earned=10 if has_fixture else 0, points_possible=10,
        detail="test_trigger section with payload found" if has_fixture
               else "Missing test_trigger section — add a realistic webhook payload",
    ))

    # ── 9. Outcome map entry (8 pts) ─────────────────────────────────────────
    try:
        from app.runtime.executor import _OUTCOME_MAP
        in_map = slug in _OUTCOME_MAP
    except ImportError:
        in_map = False
    score.criteria.append(CriterionResult(
        name="outcome_map_entry", passed=in_map,
        points_earned=8 if in_map else 0, points_possible=8,
        detail=f"Slug '{slug}' in _OUTCOME_MAP" if in_map
               else f"Slug '{slug}' not in _OUTCOME_MAP — add it to executor.py",
    ))

    # ── 10. Model input declared (5 pts) ─────────────────────────────────────
    inputs = raw.get("inputs") or {}
    has_model_input = "model" in inputs
    if brain_blocks and not has_model_input:
        score.criteria.append(CriterionResult(
            name="model_input_declared", passed=False, points_earned=0, points_possible=5,
            detail="Brain blocks present but no 'model' input declared",
        ))
    else:
        score.criteria.append(CriterionResult(
            name="model_input_declared", passed=True, points_earned=5, points_possible=5,
            detail="Model input declared" if has_model_input else "No brain blocks — model input not required",
        ))

    # ── 11. No empty block labels (4 pts) ────────────────────────────────────
    empty_labels = [k for k, v in blocks.items() if not (v.get("label") or "").strip()]
    if not empty_labels:
        score.criteria.append(CriterionResult(
            name="block_labels_present", passed=True, points_earned=4, points_possible=4,
            detail="All blocks have human-readable labels",
        ))
    else:
        score.criteria.append(CriterionResult(
            name="block_labels_present", passed=False, points_earned=0, points_possible=4,
            detail=f"Blocks missing labels: {empty_labels}",
        ))

    # ── 12. Memory write after brain (4 pts) ─────────────────────────────────
    # If there are brain blocks, we expect at least one memory write block
    memory_writes = [k for k, v in memory_blocks.items() if v.get("action") == "write"]
    if brain_blocks and not memory_writes:
        score.criteria.append(CriterionResult(
            name="memory_write_present", passed=False, points_earned=0, points_possible=4,
            detail="Brain blocks present but no memory write block — results not persisted",
        ))
    else:
        score.criteria.append(CriterionResult(
            name="memory_write_present", passed=True, points_earned=4, points_possible=4,
            detail=f"Memory write blocks: {memory_writes}" if memory_writes else "No brain blocks",
        ))

    # ── 13. No dead-end blocks (4 pts) ───────────────────────────────────────
    # A block is a dead-end if it has no next: AND is not an output/cleanup type
    terminal_types = {"output"}
    dead_ends = []
    for k, v in blocks.items():
        btype = v.get("type", "")
        nxt = v.get("next")
        # Logic blocks: their next is a dict — not a dead end
        if btype in terminal_types:
            continue
        if btype == "logic":
            continue
        if not nxt:
            dead_ends.append(k)
    if not dead_ends:
        score.criteria.append(CriterionResult(
            name="no_dead_end_blocks", passed=True, points_earned=4, points_possible=4,
            detail="All non-terminal blocks have next: routing",
        ))
    else:
        score.criteria.append(CriterionResult(
            name="no_dead_end_blocks", passed=False, points_earned=0, points_possible=4,
            detail=f"Dead-end blocks (no next:): {dead_ends}",
        ))

    # ── Slug-specific bonus checks ────────────────────────────────────────────
    slug_checks = _SLUG_RUBRICS.get(slug, [])
    for chk in slug_checks:
        passed = chk["check"](wf, blocks)
        pts = chk["points"]
        score.criteria.append(CriterionResult(
            name=chk["name"],
            passed=passed,
            points_earned=pts if passed else 0,
            points_possible=pts,
            detail=chk["detail_pass"] if passed else chk["detail_fail"],
        ))

    # ── Tally ─────────────────────────────────────────────────────────────────
    score.structural_score = sum(c.points_earned for c in score.criteria)
    score.structural_max = sum(c.points_possible for c in score.criteria)
    return score


# ── quality scoring (live mode) ───────────────────────────────────────────────

def score_quality(
    score: PlaybookScore,
    run_status: str,
    outcome: dict | None,
    state: dict,
    total_tokens: int,
    judge_result: Any | None = None,
) -> PlaybookScore:
    """
    Add quality criteria to an existing PlaybookScore after a live run.
    Modifies score in place and returns it.

    Parameters
    ----------
    judge_result:
        Optional :class:`eval.judge.JudgeResult`.  When provided, its
        per-dimension scores (correctness/completeness/actionability, 10 pts
        each) are appended and quality_max is raised from 40 to 70.
    """
    quality_criteria: list[CriterionResult] = []
    quality_max = 40

    # 1. Run succeeded (15 pts)
    succeeded = run_status == "succeeded"
    quality_criteria.append(CriterionResult(
        name="run_succeeded", passed=succeeded,
        points_earned=15 if succeeded else 0, points_possible=15,
        detail=f"run.status={run_status}",
    ))

    # 2. Outcome detected (10 pts)
    outcome_detected = outcome is not None
    quality_criteria.append(CriterionResult(
        name="outcome_detected", passed=outcome_detected,
        points_earned=10 if outcome_detected else 0, points_possible=10,
        detail=f"outcome={outcome}",
    ))

    # 3. Artifact produced (10 pts) — only if the slug requires one
    try:
        from app.runtime.executor import _OUTCOME_MAP
        entry = _OUTCOME_MAP.get(score.slug)
        requires_artifact = entry[2] if entry else False
        artifact_keys = entry[1] if entry else []
    except ImportError:
        requires_artifact = False
        artifact_keys = []

    if requires_artifact:
        artifact_url = outcome.get("artifact_url") if outcome else None
        has_artifact = bool(artifact_url)
        quality_criteria.append(CriterionResult(
            name="artifact_produced", passed=has_artifact,
            points_earned=10 if has_artifact else 0, points_possible=10,
            detail=f"artifact_url={artifact_url}",
        ))
    else:
        # No artifact required; award full marks if run succeeded
        quality_criteria.append(CriterionResult(
            name="artifact_produced", passed=succeeded,
            points_earned=10 if succeeded else 0, points_possible=10,
            detail="No artifact required for this playbook",
        ))

    # 4. Token budget respected (5 pts) — under 50k tokens
    under_budget = total_tokens < 50_000
    quality_criteria.append(CriterionResult(
        name="token_budget", passed=under_budget,
        points_earned=5 if under_budget else 0, points_possible=5,
        detail=f"total_tokens={total_tokens:,} (budget: 50,000)",
    ))

    # 5. LLM-as-judge (30 pts, optional) — correctness + completeness + actionability
    if judge_result is not None and not judge_result.failed:
        for criterion in judge_result.to_criteria():
            quality_criteria.append(CriterionResult(
                name=criterion["name"],
                passed=criterion["passed"],
                points_earned=criterion["points_earned"],
                points_possible=criterion["points_possible"],
                detail=criterion["detail"],
            ))
        quality_max = 70  # 40 mechanical + 30 judge

    score.criteria.extend(quality_criteria)
    score.quality_score = sum(c.points_earned for c in quality_criteria)
    score.quality_max = quality_max
    return score
