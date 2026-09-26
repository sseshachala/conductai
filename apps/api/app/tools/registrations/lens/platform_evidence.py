"""Platform investigations exposed through the existing Lens registry."""
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from app.modules.glens.platform_evidence import (
    PlatformEvidenceQuery, PlatformEvidenceResult, read_platform_evidence,
)
from app.tools.registrations.lens._shared import _LENS_TAGS, _READ_ONLY
from app.tools.types import ToolDef


def get_platform_evidence(ctx, **arguments):
    from app.core.database import SessionLocal
    from app.core.workspace_context import set_workspace_rls

    query = PlatformEvidenceQuery.model_validate(arguments)
    db = None
    try:
        db = SessionLocal()
        set_workspace_rls(db, ctx.workspace_id)
        return read_platform_evidence(db, ctx.workspace_id, ctx.clerk_user_id, query).model_dump(mode="json")
    except SQLAlchemyError:
        return PlatformEvidenceResult(
            status="unavailable", workspace_id=ctx.workspace_id, scope=query.scope,
            retrieved_at=datetime.now(timezone.utc), since=query.since, until=query.until,
            request_ids=query.request_ids, limit=query.limit, surface=query.surface,
            run_id=query.run_id, decision=query.decision, intent=query.intent,
            event_ids=query.event_ids, block_id=query.block_id, exact_resource=query.exact_resource,
        ).model_dump(mode="json")
    finally:
        if db is not None:
            db.close()


TOOLS = [ToolDef(
    name="get_platform_evidence",
    description=(Path(__file__).resolve().parents[3] / "modules/glens/prompts/platform_evidence.txt").read_text().strip(),
    input_schema={**PlatformEvidenceQuery.model_json_schema(), "required": []},
    output_schema=PlatformEvidenceResult.model_json_schema(), impl=get_platform_evidence,
    annotations=_READ_ONLY, tags=_LENS_TAGS,
)]
