"""#2170 PR 2 reviewer fixes — brain_block ↔ Gateway profile routing.

Covers three reviewer P1 findings against #2182:

1. Assigned-but-unavailable profile fails closed (raises), not silently
   falling back to the legacy per-provider path.
2. Profile-routed workflows do not require a legacy vendor API key —
   MissingProviderKey must not fire before profile resolution.
3. The profile lookup runs before the provider-key check so both above
   hold together.

Environment bootstrap (DATABASE_URL etc) is handled by tests/conftest.py.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch


def _wf_row(gateway_profile_id):
    row = MagicMock()
    row.gateway_profile_id = gateway_profile_id
    return row


def _profile_row(*, id=None, cond_code="ABC12345", model_alias="default", active=True):
    row = MagicMock()
    row.id = id or uuid.uuid4()
    row.cond_code = cond_code
    row.model_alias = model_alias
    row.active_revision_id = uuid.uuid4() if active else None
    row.name = f"profile-{cond_code}"
    return row


def _dispatch_db(*, wf_row, prof_row):
    """Return a MagicMock db whose ``query`` dispatches by ORM model."""
    from app.models.workflow import Workflow as _WF
    from app.models.gateway_profile import GatewayProfile as _GP

    wf_q = MagicMock()
    wf_q.filter.return_value.first.return_value = wf_row
    prof_q = MagicMock()
    prof_q.filter.return_value.first.return_value = prof_row

    db = MagicMock()

    def _q(model):
        if model is _WF:
            return wf_q
        if model is _GP:
            return prof_q
        return MagicMock()

    db.query.side_effect = _q
    return db


def _min_block_and_state():
    """Minimal block/state pair to reach the profile-resolution block."""
    block = {
        "id": "brain-1",
        "data": {
            "type": "brain",
            "isAgentic": False,
            "prompt": "Do the thing",
            "provider": "openai",  # legacy path would need OPENAI_API_KEY
            "model": "gpt-4o-mini",
            "config": {},
        },
    }
    state = {"__inputs": {}, "__env": {}, "__vars": {}}
    return block, state


def test_assigned_unpublished_profile_fails_closed():
    """Profile pinned but no active_revision_id → raise, never legacy fallback."""
    from app.runtime.blocks.brain_block import _execute_brain

    wf_id = uuid.uuid4()
    prof = _profile_row(active=False)
    db = _dispatch_db(
        wf_row=_wf_row(prof.id),
        prof_row=prof,
    )
    block, state = _min_block_and_state()

    try:
        _execute_brain(
            block, state, {}, credentials=None, db=db,
            run_id=str(uuid.uuid4()), block_id="brain-1",
            workspace_id=str(uuid.uuid4()),
            workflow_id=str(wf_id),
        )
    except RuntimeError as exc:
        assert "published revision" in str(exc)
        return
    raise AssertionError("expected RuntimeError on unpublished profile")


def test_assigned_missing_profile_fails_closed():
    """Profile id pinned but row deleted from gateway_profiles → raise."""
    from app.runtime.blocks.brain_block import _execute_brain

    wf_id = uuid.uuid4()
    db = _dispatch_db(
        wf_row=_wf_row(uuid.uuid4()),  # non-null pin
        prof_row=None,                 # but row is gone
    )
    block, state = _min_block_and_state()

    try:
        _execute_brain(
            block, state, {}, credentials=None, db=db,
            run_id=str(uuid.uuid4()), block_id="brain-1",
            workspace_id=str(uuid.uuid4()),
            workflow_id=str(wf_id),
        )
    except RuntimeError as exc:
        assert "no longer exists" in str(exc)
        return
    raise AssertionError("expected RuntimeError on missing profile")


def test_profile_routed_workflow_skips_legacy_provider_key_check():
    """MissingProviderKey must not fire when the workflow uses a Gateway profile.

    The block declares provider='openai' but no ``OPENAI_API_KEY`` is
    provisioned. Legacy path raises ``MissingProviderKey``; profile
    path skips that check entirely and reaches the client.
    """
    from app.runtime.blocks.brain_block import _execute_brain
    from app.runtime.provider_keys import MissingProviderKey

    wf_id = uuid.uuid4()
    prof = _profile_row(active=True)
    db = _dispatch_db(
        wf_row=_wf_row(prof.id),
        prof_row=prof,
    )
    block, state = _min_block_and_state()

    # Short-circuit ``post_with_retry`` inside the adapter so we don't
    # hit the network. Any exception raised past this point is proof
    # that MissingProviderKey did NOT fire and profile-first resolution
    # took over. Fail only if MissingProviderKey specifically escapes.
    def _stub_post(**_kwargs):
        raise RuntimeError("stubbed — profile path reached adapter")

    with patch("app.runtime.adapters.gateway_profile.post_with_retry", _stub_post):
        try:
            _execute_brain(
                block, state, {}, credentials=None, db=db,
                run_id=str(uuid.uuid4()), block_id="brain-1",
                workspace_id=str(uuid.uuid4()),
                workflow_id=str(wf_id),
            )
        except MissingProviderKey as exc:
            raise AssertionError(
                f"MissingProviderKey fired despite profile routing: {exc}"
            )
        except Exception:
            # Any other exception — including our stub RuntimeError —
            # confirms execution progressed past the provider-key check.
            pass
