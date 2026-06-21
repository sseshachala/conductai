"""Governance dashboard endpoints — aggregate compliance + run + spend data
into the three-view outcome surface defined by issue #750.

Phase 1 endpoints:
    GET /governance/frameworks   — multi-framework coverage matrix
    GET /governance/narrative    — plain-English summary paragraph (template-based for now)
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import require_permission, get_workspace_id
from app.core.database import get_db
from app.modules.guard.models import (
    GuardAuditEvent,
    SkillPack,
    WorkspaceSkillPack,
)


router = APIRouter(prefix="/governance", tags=["governance"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class FrameworkRow(BaseModel):
    framework: str               # e.g. "SOC2"
    rules_count: int             # how many installed rules carry this framework tag
    controls: list[str]          # distinct control IDs covered (e.g. ["CC6.1", "CC8.1"])
    packs: list[str]             # pack slugs that contribute (e.g. ["conduct-base", "conduct-soc2"])


class BonusFrameworkRow(BaseModel):
    framework: str
    rules_count: int
    controls: list[str]
    packs: list[str]                # packs that cross-tag this framework
    recommended_pack: str | None    # slug of the dedicated pack, if one exists


class FrameworksOut(BaseModel):
    installed: list[FrameworkRow]   # frameworks where a dedicated pack is installed
    bonus: list[BonusFrameworkRow]  # frameworks getting cross-coverage only
    total_rules: int                # sum of all installed rules (across packs)
    rules_with_framework: int       # how many of those have at least one framework tag


# Maps pack slug → the framework it's designed for. None = general (no primary).
# Used to split framework coverage into "installed" (dedicated pack present) and
# "bonus" (cross-tagged rules from packs designed for other frameworks).
PACK_PRIMARY_FRAMEWORK: dict[str, str | None] = {
    "conduct-soc2":     "SOC2",
    "conduct-owasp":    "OWASP",
    "conduct-hipaa":    "HIPAA",
    "conduct-pci-dss":  "PCI_DSS",
    "conduct-base":     None,
}

# Reverse map: given a framework name, recommend the dedicated pack to install.
# None = no dedicated pack ships today (e.g. GDPR, EU_AI_Act, ISO_42001).
RECOMMENDED_PACK: dict[str, str | None] = {
    "SOC2":      "conduct-soc2",
    "OWASP":     "conduct-owasp",
    "HIPAA":     "conduct-hipaa",
    "PCI_DSS":   "conduct-pci-dss",
    "ISO_42001": None,
    "GDPR":      None,
    "EU_AI_ACT": None,
    "NIST":      None,
    "NIS2":      None,
    "DORA":      None,
}


class NarrativeOut(BaseModel):
    paragraph: str
    generated_at: datetime
    source: str                  # "template" | "llm"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _latest_pack(db: Session, slug: str, pinned: str | None) -> SkillPack | None:
    if pinned:
        return db.get(SkillPack, (slug, pinned))
    return (
        db.query(SkillPack)
        .filter(SkillPack.slug == slug)
        .order_by(SkillPack.version.desc())
        .first()
    )


def _split_framework(token: str) -> tuple[str, str | None]:
    """Parse 'SOC2:CC6.1' → ('SOC2', 'CC6.1'). Bare 'OWASP_TOP_10' → ('OWASP_TOP_10', None)."""
    if ":" in token:
        fw, ctrl = token.split(":", 1)
        return fw.strip(), ctrl.strip()
    return token.strip(), None


# ── Endpoints ─────────────────────────────────────────────────────────────────

def _compute_framework_coverage(db: Session, workspace_id: str) -> FrameworksOut:
    """Shared logic — called by the public endpoint and by /narrative."""
    ws_uuid = uuid.UUID(workspace_id)

    installed = (
        db.query(WorkspaceSkillPack)
        .filter(WorkspaceSkillPack.workspace_id == ws_uuid)
        .all()
    )

    # framework → {controls: set, packs: set, rules: int}
    agg: dict[str, dict] = defaultdict(lambda: {"controls": set(), "packs": set(), "rules": 0})
    total_rules = 0
    rules_with_framework = 0

    for wp in installed:
        pack = _latest_pack(db, wp.pack_slug, wp.pinned_version)
        if not pack:
            continue
        for rule in pack.rules or []:
            total_rules += 1
            fw_tokens = rule.get("frameworks") or []
            if not fw_tokens:
                continue
            rules_with_framework += 1
            for tok in fw_tokens:
                fw, ctrl = _split_framework(tok)
                bucket = agg[fw]
                bucket["rules"] += 1
                if ctrl:
                    bucket["controls"].add(ctrl)
                bucket["packs"].add(pack.slug)

    # Set of frameworks for which a dedicated pack is installed.
    installed_frameworks = {
        PACK_PRIMARY_FRAMEWORK.get(wp.pack_slug)
        for wp in installed
        if PACK_PRIMARY_FRAMEWORK.get(wp.pack_slug) is not None
    }

    installed_rows: list[FrameworkRow] = []
    bonus_rows: list[BonusFrameworkRow] = []
    for fw, data in sorted(agg.items(), key=lambda kv: -kv[1]["rules"]):
        if fw in installed_frameworks:
            installed_rows.append(FrameworkRow(
                framework=fw,
                rules_count=data["rules"],
                controls=sorted(data["controls"]),
                packs=sorted(data["packs"]),
            ))
        else:
            bonus_rows.append(BonusFrameworkRow(
                framework=fw,
                rules_count=data["rules"],
                controls=sorted(data["controls"]),
                packs=sorted(data["packs"]),
                recommended_pack=RECOMMENDED_PACK.get(fw),
            ))

    return FrameworksOut(
        installed=installed_rows,
        bonus=bonus_rows,
        total_rules=total_rules,
        rules_with_framework=rules_with_framework,
    )


@router.get("/frameworks", response_model=FrameworksOut)
def get_framework_coverage(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.view")),
):
    """Aggregate all installed-pack rules by framework tag."""
    return _compute_framework_coverage(db, workspace_id)


@router.get("/narrative", response_model=NarrativeOut)
def get_narrative(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.activity.view_own")),
):
    """Plain-English summary. Template-based; LLM upgrade in Phase 2."""
    ws_uuid = uuid.UUID(workspace_id)
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    installed_packs = (
        db.query(WorkspaceSkillPack)
        .filter(WorkspaceSkillPack.workspace_id == ws_uuid)
        .count()
    )

    blocked_7d = (
        db.query(GuardAuditEvent)
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.decision == "blocked",
            GuardAuditEvent.ts >= week_ago,
        )
        .count()
    )

    warned_7d = (
        db.query(GuardAuditEvent)
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.decision == "warned",
            GuardAuditEvent.ts >= week_ago,
        )
        .count()
    )

    total_7d = (
        db.query(GuardAuditEvent)
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.ts >= week_ago,
        )
        .count()
    )

    # Frameworks covered — count primary (installed dedicated pack) first; mention bonus only if no primary.
    fw_resp = _compute_framework_coverage(db, workspace_id)
    primary_count = len(fw_resp.installed)
    bonus_count = len(fw_resp.bonus)
    fw_count = primary_count
    fw_names = ", ".join(r.framework for r in fw_resp.installed[:3])

    if total_7d == 0 and installed_packs == 0:
        para = (
            "No AI activity recorded yet. Install a compliance pack from the marketplace "
            "to start covering frameworks like SOC 2, ISO 42001, OWASP, or HIPAA."
        )
    else:
        bits = []
        if total_7d > 0:
            bits.append(f"Guard screened {total_7d:,} AI tool calls this week")
        if blocked_7d > 0:
            bits.append(f"intercepted {blocked_7d} risky actions")
        if warned_7d > 0:
            bits.append(f"flagged {warned_7d} for review")
        if fw_count > 0:
            bits.append(f"covering {fw_count} frameworks ({fw_names})")
            if bonus_count > 0:
                bits.append(f"with bonus coverage on {bonus_count} more")
        elif bonus_count > 0:
            bits.append(f"with bonus coverage on {bonus_count} frameworks from {installed_packs} pack(s)")
        elif installed_packs > 0:
            bits.append(f"with {installed_packs} pack(s) installed")
        para = ". ".join(b.capitalize() if i == 0 else b for i, b in enumerate(bits)) + "."

    return NarrativeOut(paragraph=para, generated_at=now, source="template")
