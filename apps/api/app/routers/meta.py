from fastapi import APIRouter, Depends
from app.core.auth import require_permission
from app.runtime.block_schemas import BLOCK_SCHEMAS

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/block-schemas")
def get_block_schemas(
    _: str = Depends(require_permission("platform.workflows.view")),
):
    """Return the full block schema registry — drives canvas field rendering and DSL validation."""
    return BLOCK_SCHEMAS
