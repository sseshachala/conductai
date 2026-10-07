"""Lens gateway_v2 summary must match the v3 ProfileOut shape (no bindings)."""
from datetime import datetime, timezone
from uuid import uuid4

from app.routers.gateway_profiles_v2 import ProfileOut
from app.tools.registrations.lens.gateway_v2 import _profile_summary


def _profile(active):
    now = datetime.now(timezone.utc)
    return ProfileOut(
        id=uuid4(), workspace_id=uuid4(), name="prod", model_alias="sonnet",
        cond_code="ab12", active_revision_id=active, working_copy=None,
        created_at=now, updated_at=now,
    )


def test_summary_projects_v3_fields() -> None:
    rev = uuid4()
    out = _profile_summary(_profile(rev))
    assert out["cond_code"] == "ab12"
    assert out["active_revision_id"] == str(rev)
    assert out["revisions"] == 0
    assert "bindings" not in out


def test_summary_unpublished_profile() -> None:
    assert _profile_summary(_profile(None))["active_revision_id"] is None
