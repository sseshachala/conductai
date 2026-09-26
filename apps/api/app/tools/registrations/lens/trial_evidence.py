"""Trial evidence uses the same reader on every registry transport."""
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from app.modules.glens.trial_evidence import (
    TrialEvidenceQuery, TrialEvidenceResult, read_trial_evidence,
)
from app.modules.glens.trial_accounting import attach_trial_accounting
from app.tools.registrations.lens._shared import _LENS_TAGS, _READ_ONLY
from app.tools.types import ToolDef


def get_trial_evidence(ctx, **arguments):
    from app.core.database import SessionLocal
    from app.core.workspace_context import set_workspace_rls

    query = TrialEvidenceQuery.model_validate(arguments)
    db = None
    try:
        db = SessionLocal()
        set_workspace_rls(db, ctx.workspace_id)
        evidence = read_trial_evidence(
            db, ctx.workspace_id, ctx.clerk_user_id, query,
        )
        return attach_trial_accounting(db, ctx.clerk_user_id, evidence).model_dump(mode="json")
    except SQLAlchemyError:
        return TrialEvidenceResult(
            status="unavailable", workspace_id=ctx.workspace_id, scope=query.scope,
            retrieved_at=datetime.now(timezone.utc), since=query.since, until=query.until,
            request_ids=query.request_ids, limit=query.limit,
        ).model_dump(mode="json")
    finally:
        if db is not None:
            db.close()


TOOLS = [ToolDef(
    name="get_trial_evidence",
    description=(
        "Retrieve recorded Guard trial decisions: 'What happened in my trial?' "
        "Defaults to your own trial identities and the last 24 hours. Workspace scope "
        "requires view-all permission. Use total_matching, never the returned list length, "
        "for totals. Respect partial/unavailable/denied states; missing evidence is not zero activity. "
        "Includes receipt-backed tokens and calculated cost when spend permission allows. "
        "Accounting totals cover returned records only; partial values are subtotals, not full spend. "
        "Never add cache or reasoning breakdowns again. No prompts or credentials are returned."
    ),
    input_schema={**TrialEvidenceQuery.model_json_schema(), "required": []},
    output_schema=TrialEvidenceResult.model_json_schema(),
    impl=get_trial_evidence,
    annotations=_READ_ONLY,
    tags=_LENS_TAGS,
)]
