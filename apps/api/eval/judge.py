"""
LLM-as-judge quality rubric for the Conduct eval harness.

Evaluates playbook output quality on three universal dimensions (30 pts total):
  Correctness   0-10 pts  — output addresses the trigger event correctly
  Completeness  0-10 pts  — all required output fields present and substantive
  Actionability 0-10 pts  — outputs are concrete, specific, and immediately usable

Plus per-playbook-type precision criterion (0-10 pts, only for known slug types):
  PR reviewer / security scanner:  correctly identified issues without false positives
  Issue triage:                     priority + type assignment accuracy
  Incident responder:               root cause hypothesis quality
  Autopilot:                        PR description quality
  Release notes:                    coverage and formatting

Uses claude-haiku-4-5 (cheapest) for judging by default.
Estimated cost: ~$0.002–0.005 per judgment.

Usage
-----
  from eval.judge import judge_output, JudgeResult

  result = judge_output(
      slug="pr_reviewer",
      trigger_payload={"action": "opened", "pull_request": {...}},
      brain_output="The PR introduces a hardcoded API key...",
      model="claude-haiku-4-5-20251001",
  )
  print(result.total_score)  # 0-40
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

# ── per-playbook rubric prompts ───────────────────────────────────────────────

_RUBRIC_OVERRIDES: dict[str, str] = {
    "pr_reviewer": """\
For a PR reviewer:
- Correctness: Did it identify real issues that actually exist in this PR? No hallucinated problems.
- Completeness: Did it cover all critical issues (security, logic, tests) without omitting important ones?
- Actionability: Are suggestions specific (file + line + fix), not vague ("consider improving error handling")?\
""",

    "copilot_reviewer": """\
For an AI PR reviewer:
- Correctness: Did it correctly identify the primary code quality and security issues?
- Completeness: Did it cover security, performance, and correctness dimensions?
- Actionability: Does each finding have a concrete suggested fix, not just a description of the problem?\
""",

    "security_scanner": """\
For a security scanner:
- Correctness: Are reported findings genuinely present in the PR diff? No phantom vulnerabilities.
- Completeness: Are all severity levels (critical, high, medium) classified correctly? Are false negatives minimal?
- Actionability: Does each finding include CWE/CVE reference, affected code location, and remediation steps?\
""",

    "issue_triage": """\
For an issue triager:
- Correctness: Is the assigned type (bug/feature/security) correct for this issue? Is priority calibrated correctly?
- Completeness: Did it assign both type and priority, and add relevant labels?
- Actionability: Is there a clear next step (assign to team, link to component, ask for repro steps)?\
""",

    "incident_responder": """\
For an incident responder:
- Correctness: Is the hypothesis consistent with the alert data and likely root causes?
- Completeness: Did it cover what to check (logs, metrics, recent deploys) and who to notify?
- Actionability: Are the investigation steps specific (which logs, which queries, which dashboards)?\
""",

    "postmortem_drafter": """\
For a postmortem drafter:
- Correctness: Does the draft accurately reflect the incident timeline and impact?
- Completeness: Does it cover timeline, root cause, impact, action items, and prevention?
- Actionability: Are action items specific with owners and dates, not vague process improvements?\
""",

    "autopilot": """\
For an autopilot PR opener:
- Correctness: Does the implementation address the issue request correctly?
- Completeness: Does the PR include tests, docs, and migration if applicable?
- Actionability: Is the PR description clear enough for a reviewer to understand what changed and why?\
""",

    "autopilot_quick": """\
For a quick autopilot:
- Correctness: Does the code change correctly address the requested issue?
- Completeness: Does it handle edge cases and not just the happy path?
- Actionability: Is the change scoped correctly (not too broad, not too narrow)?\
""",

    "autopilot_full": """\
For a full autopilot implementation:
- Correctness: Does the implementation satisfy all requirements in the issue?
- Completeness: Are tests, error handling, logging, and documentation included?
- Actionability: Would a senior engineer approve this PR without major revision requests?\
""",

    "autopilot_approved": """\
For an approval-gated autopilot:
- Correctness: Is the approval request framed accurately (no exaggeration of risk or impact)?
- Completeness: Does it provide enough context for an approver to make an informed decision?
- Actionability: Is there a clear approve/reject binary choice with a summary of what will change?\
""",

    "release_notes": """\
For a release notes drafter:
- Correctness: Do the notes accurately reflect the actual commits/changes included in the release?
- Completeness: Are breaking changes, new features, bug fixes, and deprecations all covered?
- Actionability: Are notes written for the end-user audience (not internal jargon), with upgrade steps if needed?\
""",

    "release_readiness": """\
For a release readiness reviewer:
- Correctness: Is the readiness assessment accurate? No false-positives (blocking a ready PR) or false-negatives.
- Completeness: Did it check CI status, migration completeness, docs, CHANGELOG, and test coverage?
- Actionability: Are blockers clearly listed with specific remediation steps?\
""",

    "dependency_updater": """\
For a dependency updater:
- Correctness: Are the proposed updates valid (correct package names, version ranges)?
- Completeness: Were all outdated packages across all package managers identified?
- Actionability: Is the PR structured to be safe to merge (one package per commit, lock file updated)?\
""",

    "security_patch_updater": """\
For a security patch updater:
- Correctness: Is the patched version actually the fixed version for this CVE?
- Completeness: Are all affected transitive dependencies also updated?
- Actionability: Does the PR include a test to verify the vulnerability is remediated?\
""",

    "docs_drift_detector": """\
For a docs drift detector:
- Correctness: Is the identified drift real (code changed, docs did not)? No false alarms.
- Completeness: Are all drifted areas identified (API docs, README, CHANGELOG)?
- Actionability: Does the issue clearly describe which specific docs need updating and what changed?\
""",

    "flaky_test_detective": """\
For a flaky test detective:
- Correctness: Is the identified flakiness pattern accurate (not just a stable failure)?
- Completeness: Does it identify all affected tests and the likely root cause category?
- Actionability: Is the fix recommendation specific (use explicit waits, seed the RNG, isolate DB state)?\
""",

    "terraform_reviewer": """\
For a Terraform plan reviewer:
- Correctness: Are flagged risks actually present in the plan? No phantom concerns.
- Completeness: Does it cover security groups, IAM policies, destroy operations, and cost implications?
- Actionability: Is each finding tied to a specific resource name and a concrete fix?\
""",

    "ci_notify": """\
For a CI failure alerter:
- Correctness: Is the alert appropriate (real failure on the monitored branch, not a false alarm)?
- Completeness: Does the alert include the workflow name, failing step, and link to the run?
- Actionability: Is there a clear first action for the on-call engineer (check logs, revert PR, etc.)?\
""",

    "ai_ready": """\
For an AI-readiness auditor:
- Correctness: Are the identified gaps genuine deficiencies (missing llms.txt, poor docstrings)?
- Completeness: Does it cover context files, structured outputs, naming conventions, and type hints?
- Actionability: Is each finding accompanied by the specific file/change needed?\
""",
}

_UNIVERSAL_RUBRIC = """\
Evaluate on three dimensions (0–10 each):
- Correctness: Does the output correctly address the trigger event/payload?
- Completeness: Does it cover all required aspects for this playbook type?
- Actionability: Are the outputs concrete, specific, and immediately usable?\
"""


# ── data classes ─────────────────────────────────────────────────────────────

@dataclass
class DimensionScore:
    name: str
    score: int          # 0-10
    max_score: int = 10
    reason: str = ""


@dataclass
class JudgeResult:
    slug: str
    model: str
    correctness: DimensionScore = field(default_factory=lambda: DimensionScore("correctness", 0))
    completeness: DimensionScore = field(default_factory=lambda: DimensionScore("completeness", 0))
    actionability: DimensionScore = field(default_factory=lambda: DimensionScore("actionability", 0))
    reasoning: str = ""
    raw_response: str = ""
    elapsed_ms: int = 0
    error: str | None = None

    @property
    def total_score(self) -> int:
        return self.correctness.score + self.completeness.score + self.actionability.score

    @property
    def max_score(self) -> int:
        return 30

    @property
    def failed(self) -> bool:
        return self.error is not None

    def to_criteria(self) -> list[dict]:
        """Convert to CriterionResult-compatible dicts for integration with PlaybookScore."""
        return [
            {
                "name": "judge_correctness",
                "passed": self.correctness.score >= 6,
                "points_earned": self.correctness.score,
                "points_possible": 10,
                "detail": self.correctness.reason or f"score={self.correctness.score}/10",
            },
            {
                "name": "judge_completeness",
                "passed": self.completeness.score >= 6,
                "points_earned": self.completeness.score,
                "points_possible": 10,
                "detail": self.completeness.reason or f"score={self.completeness.score}/10",
            },
            {
                "name": "judge_actionability",
                "passed": self.actionability.score >= 6,
                "points_earned": self.actionability.score,
                "points_possible": 10,
                "detail": self.actionability.reason or f"score={self.actionability.score}/10",
            },
        ]


# ── main entry point ──────────────────────────────────────────────────────────

def judge_output(
    slug: str,
    trigger_payload: dict[str, Any],
    brain_output: str,
    model: str = "claude-haiku-4-5-20251001",
    api_key: str | None = None,
) -> JudgeResult:
    """
    Run LLM-as-judge evaluation on a playbook's brain output.

    Parameters
    ----------
    slug:
        Playbook slug (e.g. ``pr_reviewer``). Used to select the per-playbook rubric.
    trigger_payload:
        The webhook payload that triggered the run (used as context for the judge).
    brain_output:
        The final output text from the primary brain block.
    model:
        Judge model — default is Haiku for cheapness.
    api_key:
        Anthropic API key override.

    Returns a :class:`JudgeResult` with per-dimension scores.
    """
    start = time.perf_counter()

    rubric = _RUBRIC_OVERRIDES.get(slug, _UNIVERSAL_RUBRIC)
    trigger_summary = _summarise_trigger(trigger_payload)
    prompt = _build_judge_prompt(slug, trigger_summary, brain_output, rubric)

    try:
        raw = _call_claude(prompt, model=model, api_key=api_key)
        result = _parse_judge_response(raw, slug, model)
        result.elapsed_ms = round((time.perf_counter() - start) * 1000)
        result.raw_response = raw
        return result
    except Exception as exc:
        return JudgeResult(
            slug=slug,
            model=model,
            error=str(exc),
            elapsed_ms=round((time.perf_counter() - start) * 1000),
        )


# ── prompt construction ───────────────────────────────────────────────────────

def _build_judge_prompt(
    slug: str,
    trigger_summary: str,
    brain_output: str,
    rubric: str,
) -> str:
    return f"""\
You are an expert evaluator for AI automation playbooks. Score this playbook output objectively.

PLAYBOOK TYPE: {slug}

TRIGGER EVENT (what the playbook received):
{trigger_summary}

PLAYBOOK OUTPUT (what the AI produced):
{brain_output[:3000]}

EVALUATION RUBRIC:
{rubric}

INSTRUCTIONS:
Score each dimension from 0 to 10 where:
  0-3 = poor (missing, wrong, or completely unusable)
  4-6 = adequate (present but incomplete or partially correct)
  7-9 = good (correct, mostly complete, mostly actionable)
  10  = excellent (fully correct, complete, immediately actionable)

Be strict. A score of 10 should be rare.

Respond ONLY with valid JSON on a single line, no markdown:
{{"correctness": <0-10>, "completeness": <0-10>, "actionability": <0-10>, "correctness_reason": "<one sentence>", "completeness_reason": "<one sentence>", "actionability_reason": "<one sentence>", "overall_reasoning": "<two sentences>"}}
"""


def _summarise_trigger(payload: dict[str, Any]) -> str:
    """Produce a compact human-readable summary of a trigger payload."""
    if not payload:
        return "(empty trigger)"

    lines = []
    # Common top-level fields
    for key in ("action", "ref", "sender"):
        if key in payload:
            lines.append(f"{key}: {payload[key]}")

    # PR info
    if "pull_request" in payload:
        pr = payload["pull_request"]
        lines.append(f"pull_request.title: {pr.get('title', '?')}")
        lines.append(f"pull_request.draft: {pr.get('draft', False)}")

    # Issue info
    if "issue" in payload:
        issue = payload["issue"]
        lines.append(f"issue.title: {issue.get('title', '?')}")
        lines.append(f"issue.body: {str(issue.get('body', ''))[:200]}")

    # Alert info
    if "alert" in payload:
        alert = payload["alert"]
        lines.append(f"alert.title: {alert.get('title', '?')}")
        lines.append(f"alert.severity: {alert.get('severity', '?')}")

    # Workflow run info
    if "workflow_run" in payload:
        wr = payload["workflow_run"]
        lines.append(f"workflow_run.name: {wr.get('name', '?')}")
        lines.append(f"workflow_run.conclusion: {wr.get('conclusion', '?')}")
        lines.append(f"workflow_run.head_branch: {wr.get('head_branch', '?')}")

    # Release info
    if "release" in payload:
        rel = payload["release"]
        lines.append(f"release.tag_name: {rel.get('tag_name', '?')}")

    # Repository
    if "repository" in payload:
        lines.append(f"repository: {payload['repository'].get('full_name', '?')}")

    return "\n".join(lines) if lines else json.dumps(payload, indent=2)[:500]


# ── Claude API call ───────────────────────────────────────────────────────────

def _call_claude(prompt: str, model: str, api_key: str | None = None) -> str:
    """Call Claude with the judge prompt. Returns raw response text."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed — pip install anthropic")

    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["api_key"] = api_key

    client = anthropic.Anthropic(**kwargs)
    response = client.messages.create(
        model=model,
        max_tokens=512,
        system=(
            "You are a strict, objective evaluator. "
            "Output ONLY valid JSON. No markdown, no code blocks, no explanation outside JSON."
        ),
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# ── response parsing ──────────────────────────────────────────────────────────

_JSON_RE = re.compile(r'\{.*\}', re.DOTALL)


def _parse_judge_response(raw: str, slug: str, model: str) -> JudgeResult:
    """Parse the judge's JSON response into a JudgeResult."""
    # Strip markdown code fences if model disobeyed instructions
    text = raw.strip()
    m = _JSON_RE.search(text)
    if not m:
        raise ValueError(f"Judge returned non-JSON: {text[:200]}")

    data = json.loads(m.group())

    def _clamp(v: Any) -> int:
        try:
            return max(0, min(10, int(v)))
        except (TypeError, ValueError):
            return 0

    return JudgeResult(
        slug=slug,
        model=model,
        correctness=DimensionScore(
            name="correctness",
            score=_clamp(data.get("correctness", 0)),
            reason=str(data.get("correctness_reason", "")),
        ),
        completeness=DimensionScore(
            name="completeness",
            score=_clamp(data.get("completeness", 0)),
            reason=str(data.get("completeness_reason", "")),
        ),
        actionability=DimensionScore(
            name="actionability",
            score=_clamp(data.get("actionability", 0)),
            reason=str(data.get("actionability_reason", "")),
        ),
        reasoning=str(data.get("overall_reasoning", "")),
        raw_response=raw,
    )


# ── utility: extract brain output from run state ─────────────────────────────

def extract_brain_output(state: dict[str, Any]) -> str:
    """
    Extract the primary brain block output from a final run state.

    Looks for string values in the state that look like brain outputs
    (non-empty strings not starting with ``__``).  Returns the longest one,
    which is usually the most relevant.
    """
    candidates = []
    for k, v in state.items():
        if k.startswith("__") or k == "_trigger":
            continue
        if isinstance(v, str) and len(v) > 50:
            candidates.append(v)
        elif isinstance(v, dict):
            for vk, vv in v.items():
                if isinstance(vv, str) and len(vv) > 50:
                    candidates.append(vv)

    if not candidates:
        return "(no brain output found in state)"

    return max(candidates, key=len)
