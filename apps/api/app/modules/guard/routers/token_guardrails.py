"""
GET   /guard/token-guardrails?workspace_id=...  — unified guardrail state (auto-detected + manual)
PATCH /guard/token-guardrails                   — update manual flags and/or slack_webhook_url
"""
import json
import urllib.request
import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from app.core.auth import get_workspace_id
from app.core.database import get_db
from app.modules.guard.models import GuardConfig, GuardPolicy, GuardSpendBudget

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/guard/token-guardrails", tags=["guard"])

_MANUAL_KEYS = ["prompt_caching", "model_routing", "prompt_splitting"]


# ── Schemas ───────────────────────────────────────────────────────────────────

class TokenGuardrailsOut(BaseModel):
    prompt_caching: bool
    model_routing: bool
    prompt_splitting: bool
    deterministic_offload: bool
    output_compression: bool
    structured_retrieval: bool
    metrics_budgets: bool
    manual_keys: list[str]
    slack_webhook_url: Optional[str] = None
    slack_integration_id: Optional[str] = None


class TokenGuardrailsPatch(BaseModel):
    workspace_id: Optional[str] = None
    prompt_caching: Optional[bool] = None
    model_routing: Optional[bool] = None
    prompt_splitting: Optional[bool] = None
    slack_webhook_url: Optional[str] = None
    slack_integration_id: Optional[str] = None


# ── Drift helpers ─────────────────────────────────────────────────────────────

def _check_guardrail_drift(
    team: GuardConfig,
    current_tools: list[str],
    current_snapshot: dict,
) -> list[str]:
    prev = team.guardrail_snapshot or {}
    prev_tools = set(prev.get("tools_installed", []))
    curr_tools = set(current_tools)

    drifts = []
    if "rtk" in prev_tools and "rtk" not in curr_tools:
        drifts.append("⚠️ RTK removed — Output compression guardrail is no longer active")
    if "booster" in prev_tools and "booster" not in curr_tools:
        drifts.append("⚠️ Agent Booster removed — Structured retrieval guardrail is no longer active")
    if prev.get("deterministic_offload") and not current_snapshot.get("deterministic_offload"):
        drifts.append("⚠️ warn-deterministic-compute policy disabled — Deterministic offload guardrail inactive")
    if prev.get("metrics_budgets") and not current_snapshot.get("metrics_budgets"):
        drifts.append("⚠️ Spend budget removed — Metrics & budgets guardrail inactive")
    return drifts


def _post_slack_drift(webhook_url: str, workspace_name: str, drifts: list[str]):
    if not webhook_url or not drifts:
        return
    text = (
        f"*ConductGuard drift detected* in workspace *{workspace_name}*:\n"
        + "\n".join(drifts)
    )
    try:
        payload = json.dumps({"text": text}).encode()
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


# ── Auto-detection helper ─────────────────────────────────────────────────────

def _build_guardrail_state(db: Session, workspace_id: str) -> dict:
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id")

    team = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
    if not team:
        raise HTTPException(status_code=404, detail="Guard not configured for this workspace")

    # ── Auto-detect: tools via savings rows ───────────────────────────────────
    row = db.execute(
        sa_text("""
            SELECT
                COALESCE(SUM(gs.rtk_saved_tokens), 0)     AS rtk_tokens,
                COALESCE(SUM(gs.rtk_total_commands), 0)   AS rtk_commands,
                COALESCE(SUM(gs.booster_saved_tokens), 0) AS booster_tokens,
                COALESCE(SUM(gs.booster_total_reads), 0)  AS booster_reads
            FROM guard_savings gs
            INNER JOIN (
                SELECT member_email, MAX(recorded_at) AS max_ts
                FROM guard_savings
                WHERE workspace_id = :ws
                GROUP BY member_email
            ) latest ON gs.member_email = latest.member_email
                     AND gs.recorded_at  = latest.max_ts
            WHERE gs.workspace_id = :ws
        """),
        {"ws": str(ws_uuid)},
    ).fetchone()

    has_rtk     = bool(row and (row.rtk_tokens > 0 or row.rtk_commands > 0))
    has_booster = bool(row and (row.booster_tokens > 0 or row.booster_reads > 0))
    current_tools = (["rtk"] if has_rtk else []) + (["booster"] if has_booster else [])

    # ── Auto-detect: deterministic offload policy ─────────────────────────────
    # Builtin default is active. Only inactive if a row exists with enabled=False.
    explicitly_disabled = (
        db.query(GuardPolicy)
        .filter(
            GuardPolicy.workspace_id == ws_uuid,
            GuardPolicy.rule_id == "warn-deterministic-compute",
            GuardPolicy.enabled.is_(False),
        )
        .first()
    ) is not None
    deterministic_offload = not explicitly_disabled

    # ── Auto-detect: any spend budget ─────────────────────────────────────────
    metrics_budgets = (
        db.query(GuardSpendBudget)
        .filter(GuardSpendBudget.workspace_id == ws_uuid)
        .first()
    ) is not None

    # ── Manual flags ──────────────────────────────────────────────────────────
    manual = team.token_guardrails or {}

    current_snapshot = {
        "tools_installed": current_tools,
        "deterministic_offload": deterministic_offload,
        "metrics_budgets": metrics_budgets,
    }

    return {
        "team": team,
        "current_tools": current_tools,
        "current_snapshot": current_snapshot,
        "out": TokenGuardrailsOut(
            prompt_caching=bool(manual.get("prompt_caching", True)),
            model_routing=bool(manual.get("model_routing", True)),
            prompt_splitting=bool(manual.get("prompt_splitting", True)),
            deterministic_offload=deterministic_offload,
            output_compression=has_rtk,
            structured_retrieval=has_booster,
            metrics_budgets=metrics_budgets,
            manual_keys=_MANUAL_KEYS,
            slack_webhook_url=team.slack_webhook_url,
            slack_integration_id=str(team.slack_integration_id) if team.slack_integration_id else None,
        ),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=TokenGuardrailsOut)
def get_token_guardrails(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    return _build_guardrail_state(db, workspace_id)["out"]


@router.patch("", response_model=TokenGuardrailsOut)
def patch_token_guardrails(
    body: TokenGuardrailsPatch,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    resolved_ws = body.workspace_id or workspace_id
    state = _build_guardrail_state(db, resolved_ws)
    team: GuardConfig = state["team"]

    manual = dict(team.token_guardrails or {})
    if body.prompt_caching is not None:
        manual["prompt_caching"] = body.prompt_caching
    if body.model_routing is not None:
        manual["model_routing"] = body.model_routing
    if body.prompt_splitting is not None:
        manual["prompt_splitting"] = body.prompt_splitting
    team.token_guardrails = manual

    if body.slack_webhook_url is not None:
        team.slack_webhook_url = body.slack_webhook_url
    if body.slack_integration_id is not None:
        team.slack_integration_id = uuid.UUID(body.slack_integration_id)

    db.commit()
    db.refresh(team)

    log.info("guard.token_guardrails_updated", workspace_id=resolved_ws, manual=manual)
    return _build_guardrail_state(db, resolved_ws)["out"]
