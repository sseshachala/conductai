"""Attach authorized accounting evidence without duplicating ledger math."""
from dataclasses import replace
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.core.auth import check_permission
from app.modules.glens.trial_evidence import TrialEvidenceResult
from app.runtime.accounting.reader import AccountingReader


def attach_trial_accounting(db, user_id: str, evidence: TrialEvidenceResult):
    evidence.accounting_status = "not_requested"
    evidence.accounting_totals = None
    evidence.accounting_unlinked_event_count = 0
    evidence.accounting_limitations = []
    for event in evidence.records:
        event.accounting = None
    if not evidence.records:
        if evidence.status == "empty":
            evidence.accounting_status = "empty"
        return evidence
    try:
        check_permission(
            user_id=user_id, workspace_id=str(evidence.workspace_id), credentials=None, db=db,
            permission=f"guard.spend.view_{'all' if evidence.scope == 'workspace' else 'own'}",
        )
        requests = {}
        for event in evidence.records:
            if event.request_id is None:
                evidence.accounting_unlinked_event_count += 1
                continue
            try:
                requests[event.request_id] = UUID(event.agent_identity_id)
            except ValueError:
                evidence.accounting_unlinked_event_count += 1
        batch = AccountingReader(db).evidence_for_requests(
            workspace_id=evidence.workspace_id, requests=requests,
        )
        for event in evidence.records:
            event.accounting = batch.requests.get(event.request_id)
        totals = batch.totals
        if evidence.accounting_unlinked_event_count:
            # Unlinked events have unknown usage; don't invent a zero receipt.
            def incomplete(value):
                return replace(value, status="partial") if value.status == "complete" else value
            totals = replace(
                totals, input_tokens=incomplete(totals.input_tokens),
                output_tokens=incomplete(totals.output_tokens),
                calculated_cost_microdollars=incomplete(totals.calculated_cost_microdollars),
            )
        evidence.accounting_totals = totals
        evidence.accounting_status = "ok" if all(value.status == "complete" for value in (
            totals.input_tokens, totals.output_tokens, totals.calculated_cost_microdollars,
        )) else "partial"
        evidence.accounting_limitations = [
            "Totals cover returned authorized records only, not the entire matching time window.",
            "Partial values are recorded subtotals; null is unavailable, not zero.",
            "Costs are calculated USD, not provider invoices. Only complete, priced receipts contribute to cost totals.",
            "Cache and reasoning tokens are breakdowns, not additions to input/output totals.",
            "Missing receipts, unknown attempt counts, or unfinished audit lifecycles prevent complete totals.",
        ]
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
        evidence.accounting_status = "denied"
    except SQLAlchemyError:
        evidence.accounting_status = "unavailable"
    return evidence
