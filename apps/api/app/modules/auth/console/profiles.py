"""Local console profile labels; never used to determine authorization."""
from sqlalchemy.orm import Session

from app.core.config import settings
from .models import ConsoleIdentityMapping


def member_names(db: Session, user_ids: list[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    mappings = db.query(ConsoleIdentityMapping).filter(
        ConsoleIdentityMapping.issuer == settings.console_oidc_issuer,
        ConsoleIdentityMapping.user_id.in_(user_ids),
    ).all()
    # Keep disabled members identifiable without implying that they can log in.
    return {row.user_id: (row.display_name or "").strip() or row.subject
            for row in mappings}
