"""ConductGuard policies — request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel


class PolicyOut(BaseModel):
    """Workspace policy as surfaced to the UI. Same shape for custom rules and
    pack rules; the `pack_id` field distinguishes them (None for custom)."""
    id: str
    workspace_id: str
    rule_id: str
    description: Optional[str] = None
    match_tool: Optional[str] = None
    match_pattern: Optional[str] = None
    match_path_pattern: Optional[str] = None
    action: str
    message: Optional[str] = None
    enabled: bool
    builtin: bool
    pack_id: Optional[str] = None
    persona: str = "agent"
    non_overridable: bool = False
    persona_affinity: list[str] = []
    recommendation: Optional[str] = None
    frameworks: list[str] = []
    severity: str = "medium"
    iso_control: Optional[str] = None
    tag: Optional[str] = None
    gates: list[str] = []  # #1733/#1750 Phase B — locked enum [action, prompt, response]
    # #1755 Slice 2 — derived per-PEP surface status. Reads pep_registry
    # capabilities × rule.gates. UI renders these as verified badges on
    # rule detail. Hand-authored `enforcement.<surface>` fields stay
    # in the JSON but are being retired (#1750 Phase D).
    derived_mcp: str = "not_supported"
    derived_proxy: str = "not_supported"
    derived_runtime: str = "not_supported"
    derived_hook: str = "not_supported"
    # #1750 reviewer edit 4 — retained hand-authored prose (NOT deleted in Phase D).
    guarantee: Optional[str] = None
    known_limitations: list[str] = []
    exception_reason: Optional[str] = None
    exception_expires_at: Optional[datetime] = None
    exception_active: bool = False
    exception_expired: bool = False
    last_triggered: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class PolicyCreate(BaseModel):
    rule_id: str
    description: Optional[str] = None
    match_tool: Optional[str] = None
    match_pattern: Optional[str] = None
    match_path_pattern: Optional[str] = None
    action: str
    message: Optional[str] = None
    persona: str = "agent"
    persona_affinity: Optional[list[str]] = None
    recommendation: Optional[str] = None
    frameworks: Optional[list[str]] = None
    severity: Optional[str] = None
    iso_control: Optional[str] = None
    workspace_id: Optional[str] = None


class PolicyPatch(BaseModel):
    enabled: Optional[bool] = None
    description: Optional[str] = None
    match_pattern: Optional[str] = None
    match_path_pattern: Optional[str] = None
    action: Optional[str] = None
    message: Optional[str] = None
    reason: Optional[str] = None
    expires_at: Optional[datetime] = None


class PolicySyncRule(BaseModel):
    rule_id: str
    match_tool: Optional[str] = None
    match_ai_tool: Optional[str] = None
    match_pattern: Optional[str] = None
    match_path_pattern: Optional[str] = None
    action: str
    message: Optional[str] = None


class PolicySyncOut(BaseModel):
    workspace_id: str
    version: str
    persona: str
    fail_mode: str = "fail_open"   # CLI hook reads this to decide outage behavior
    advisory_mode: bool = False     # CLI hook reads this to skip blocking
    rules: list[PolicySyncRule]
    signature: Optional[str] = None    # HMAC-SHA256 hex; present when workspace has a signing key
    signed_at: Optional[str] = None    # ISO-8601 timestamp of when the signature was computed


class PolicyGenerateRequest(BaseModel):
    prompt: str
    workspace_id: Optional[str] = None
    environment_id: Optional[str] = None


class PolicyGenerateOut(BaseModel):
    rule_id: str
    description: str
    match_tool: str
    match_pattern: Optional[str] = None
    match_path_pattern: Optional[str] = None
    action: str
    message: str


class PackSurfaceCounts(BaseModel):
    """Rule count per {hard, not_supported} for one PEP surface (#1751 PR 3)."""
    hard: int = 0
    not_supported: int = 0


class PackCoverageMatrixOut(BaseModel):
    """Per-pack coverage summary: rules per surface × per gate.

    Response of ``GET /guard/policies/packs/{slug}/coverage-matrix`` (#1751 PR 5).
    Feeds the pack-detail coverage table in the Policies UI (#1750 Phase B
    Slice 2 / #1755).
    """
    pack: str
    version: Optional[str] = None
    total_rules: int
    by_surface: dict[str, PackSurfaceCounts]
    by_gate: dict[str, int]


class EnforcementCoverageOut(BaseModel):
    rule_id: str
    name: str
    pack: Optional[str] = None
    pack_version: Optional[str] = None
    builtin: bool
    personas: list[str]
    action: str
    base_action: str
    enabled: bool
    proxy: Literal["hard", "conditional", "advisory", "not_supported"]
    hook: Literal["hard", "conditional", "advisory", "not_supported"]
    mcp: Literal["hard", "conditional", "advisory", "not_supported"]
    runtime: Literal["hard", "conditional", "advisory", "not_supported"]
    # #1755 Slice 2 (real PR 5) — derived counterparts. Same values, but
    # computed live from rule.gates × PEP_CAPABILITIES rather than
    # hand-authored. UI renders both side-by-side so a compliance officer
    # can see when the hand-authored value has gone stale (divergence).
    # After #1750 Phase D retires the hand-authored fields above, these
    # derived fields become the sole source of truth.
    derived_proxy: str = "not_supported"
    derived_hook: str = "not_supported"
    derived_mcp: str = "not_supported"
    derived_runtime: str = "not_supported"
    guarantee: str
    requires: list[str]
    known_limitations: list[str]
    enforcement_version: Literal[1]
    exception_reason: Optional[str] = None
    exception_expires_at: Optional[datetime] = None
    exception_active: bool = False
    exception_expired: bool = False


class LintIssue(BaseModel):
    rule_id: str
    field: str
    message: str


class LintRequest(BaseModel):
    rules: list[dict]
    fail_mode: Optional[str] = None


class LintResponse(BaseModel):
    errors: list[LintIssue] = []
    warnings: list[LintIssue] = []
