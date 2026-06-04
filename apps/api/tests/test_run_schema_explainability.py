from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.schemas.run import RunOut


def test_run_out_exposes_explainability_and_governance_from_state():
    now = datetime.now(timezone.utc)
    explainability = {
        "version": "phase2.v1",
        "source": "manual:create_run",
        "trigger_provider": "manual",
        "budget": {"max_turns": 20, "max_cost_usd": 5.0},
    }
    governance = {
        "policy_surface": "unified",
        "provider": "manual",
        "enforcement_mode": "consistent",
        "version": "phase2.v1",
    }

    payload = {
        "id": uuid.uuid4(),
        "workflow_version_id": uuid.uuid4(),
        "status": "queued",
        "created_at": now,
        "state": {
            "__run_explainability": explainability,
            "__governance": governance,
        },
    }

    out = RunOut.model_validate(payload)

    assert out.explainability == explainability
    assert out.governance == governance
