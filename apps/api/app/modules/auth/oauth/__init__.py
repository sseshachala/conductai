"""OAuth 2.1 + DCR module. See `router.py` for the FastAPI wiring."""
from app.modules.auth.oauth.router import (
    router,
    well_known_router,
    legacy_token_router,
)

__all__ = ["router", "well_known_router", "legacy_token_router"]
