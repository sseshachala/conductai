"""Deterministic investigation answers from registered Lens evidence tools."""
import html
import json
import re
from decimal import Decimal
from uuid import UUID

from pydantic import ValidationError

from app.modules.glens.masking import mask_secrets
from app.modules.glens.trial_evidence import TrialEvidenceQuery, TrialEvidenceResult

UNAVAILABLE = "Evidence is unavailable. I cannot verify decisions or usage right now."
SAVED = "Evidence must be refreshed with your current permissions."


def _literal(value):
    if value is None:
        return "not recorded"
    text = html.escape(mask_secrets(str(value)))
    text = " ".join(text.split())[:240]
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", text)


def citation(evidence: TrialEvidenceResult, source_id: UUID) -> str:
    if source_id not in {record.source_id for record in evidence.records}:
        raise ValueError("Citation is not in the authorized evidence")
    return f"[Flight Recorder](/logs/guard?id={source_id})"


def _metric(metric, money=False):
    if metric.value is None:
        return "unavailable"
    value = f"${Decimal(metric.value) / Decimal(1_000_000):.6f} USD" if money else str(metric.value)
    if metric.status != "complete":
        value += " (partial recorded subtotal)"
    return value


def render_evidence(evidence: TrialEvidenceResult) -> str:
    platform = hasattr(evidence, "surface")
    if evidence.status == "denied":
        return "You do not have access to this evidence in this workspace and scope."
    if evidence.status == "unavailable":
        return UNAVAILABLE
    lines = [
        "## Recorded Conduct Activity" if platform else "## Your Recorded Trial",
        f"Scope: {'your activity' if evidence.scope == 'own' else 'workspace activity'}.",
        f"Window: {evidence.since.isoformat()} (inclusive) to {evidence.until.isoformat()} (exclusive).",
        f"Retrieved: {evidence.retrieved_at.isoformat()}.",
    ]
    if not evidence.records:
        lines.append("No matching records were returned for policy activity. This does not prove no activity occurred.")
        if not platform:
            return "\n\n".join(lines)
    lines.append(f"Showing {len(evidence.records)} of {evidence.total_matching} matching recorded events.")
    if evidence.status == "partial":
        lines.append("This is partial evidence; some requested records may be outside this page, scope or time window.")
    for record in evidence.records:
        lines.append(
            f"- Recorded decision: **{_literal(record.decision)}**. "
            + (f"Source: {_literal(record.source)}. " if platform else "") +
            f"Recorded at: {record.recorded_at.isoformat()}. "
            f"Rule: {_literal(record.rule_id)}; policy version: {_literal(record.policy_hash)}. "
            f"Execution: {_literal(record.execution_status)}; lifecycle: {_literal(record.lifecycle_state)}. "
            f"Provider/model: {_literal(record.provider)} / {_literal(record.model)}. "
            f"{citation(evidence, record.source_id)}"
        )
        if record.accounting:
            for attempt in record.accounting.attempts:
                lines.append(
                    f"  Attempt {attempt.attempt_ordinal}: {_literal(attempt.provider)} / {_literal(attempt.model)}; "
                    f"outcome {_literal(attempt.execution_outcome)}; usage {_literal(attempt.usage_completeness)}; "
                    f"pricing {_literal(attempt.pricing_completeness)}."
                )
    lines.append("A recorded policy decision does not prove that execution completed. Rule identifiers alone do not explain the full policy rationale.")
    totals = evidence.accounting_totals
    if totals is not None and evidence.accounting_status in {"ok", "partial"}:
        lines.append(
            "Recorded usage for returned events only: "
            f"input {_metric(totals.input_tokens)}; output {_metric(totals.output_tokens)}; "
            f"calculated cost {_metric(totals.calculated_cost_microdollars, money=True)}."
        )
        versions = sorted({a.pricing_version for r in evidence.records if r.accounting
                           for a in r.accounting.attempts if a.pricing_version})
        lines.append("Receipt pricing versions: " + (", ".join(_literal(v) for v in versions) or "not recorded") + ".")
        lines.append("Costs are recorded calculations, not provider invoices. Cache and reasoning breakdowns are not added to token totals again.")
    else:
        lines.append("Usage and cost: " + ("access denied" if evidence.accounting_status == "denied" else "unavailable") + ". Neither means zero.")
    if platform:
        lines.extend(_run_lines(evidence))
    return "\n\n".join(lines)


def _run_lines(evidence):
    if evidence.runs_status == "not_requested":
        return []
    if evidence.runs_status in {"denied", "unavailable"}:
        return ["Workflow evidence: " + evidence.runs_status + "."]
    lines = [f"## Workflow Runs\n\nShowing {len(evidence.runs)} of {evidence.runs_total} matching runs (selected by creation time)."]
    for run in evidence.runs:
        # Links are built only from validated UUIDs in the authorized run result.
        lines.append(f"- {_literal(run.workflow_name)}: **{_literal(run.status)}**. "
                     f"Current block: {_literal(run.current_block_id)}. "
                     f"[Run details](/runs/{run.source_id})")
        lines.append(f"  Latest {len(run.steps)} of {run.steps_total} recorded step events:")
        for step in run.steps:
            lines.append(f"  {_literal(step.block_id)}: {_literal(step.kind)} at {step.recorded_at.isoformat()}.")
    lines.append("Step events are recorded outcomes, not an inferred root cause. Missing links do not prove a run made no model calls.")
    return lines


def answer_from_result(raw: str, workspace_id: str, tool_name="get_trial_evidence"):
    """Reject malformed or wrong-workspace results before any tokens are emitted."""
    try:
        from app.modules.glens.platform_evidence import PlatformEvidenceQuery, PlatformEvidenceResult
        platform = tool_name == "get_platform_evidence"
        evidence = (PlatformEvidenceResult if platform else TrialEvidenceResult).model_validate_json(raw)
        if evidence.workspace_id != UUID(workspace_id):
            return UNAVAILABLE, None
        query = (PlatformEvidenceQuery if platform else TrialEvidenceQuery)(
            scope=evidence.scope, since=evidence.since, until=evidence.until,
            request_ids=evidence.request_ids, limit=evidence.limit,
            **({"surface": evidence.surface, "run_id": evidence.run_id, "decision": evidence.decision} if platform else {}),
        )
        return render_evidence(evidence), query.model_dump(mode="json")
    except (ValidationError, ValueError, TypeError):
        return UNAVAILABLE, None


def refresh_saved_evidence(content: str, db, workspace_id: str, user_id: str) -> str:
    """Sessions are workspace-shared; never persist or replay protected prose."""
    from app.modules.glens.trial_accounting import attach_trial_accounting
    from app.modules.glens.trial_evidence import read_trial_evidence

    try:
        saved = json.loads(content)
    except (ValueError, TypeError):
        return content
    if not isinstance(saved, dict) or "evidence_query" not in saved:
        return content
    answer = UNAVAILABLE
    try:
        if not saved["evidence_query"]:
            return json.dumps({"answer": answer, "skill": "governance"})
        if saved.get("evidence_tool") == "get_platform_evidence":
            from app.modules.glens.platform_evidence import PlatformEvidenceQuery, read_platform_evidence
            query = PlatformEvidenceQuery.model_validate(saved["evidence_query"])
            evidence = read_platform_evidence(db, workspace_id, user_id, query)
        else:
            query = TrialEvidenceQuery.model_validate(saved["evidence_query"])
            evidence = read_trial_evidence(db, workspace_id, user_id, query)
            attach_trial_accounting(db, user_id, evidence)
        answer = render_evidence(evidence)
    except (ValidationError, ValueError, TypeError):
        pass
    return json.dumps({"answer": answer, "skill": "governance"})
