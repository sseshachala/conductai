"""
Compliance Packs — install/uninstall Guard + Security rules in one shot.

POST   /compliance/packs/{pack_id}/install    — upsert guard + security rules for the pack
DELETE /compliance/packs/{pack_id}/uninstall  — remove all pack rules (guard + security)
GET    /compliance/packs/installed            — list pack_ids that have rules in this workspace
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.modules.guard.models import GuardPolicy, SkillPack, WorkspaceSkillPack
from app.modules.guard.policy_engine import invalidate_policy_cache

router = APIRouter(prefix="/compliance", tags=["compliance"])

# ── Pack catalog ──────────────────────────────────────────────────────────────

COMPLIANCE_PACKS: dict[str, dict] = {
    "owasp_top10": {
        "guard_rules": [
            {
                "rule_id": "owasp_injection_guard",
                "description": "Block SQL string concatenation patterns (OWASP A03)",
                "match_pattern": r"SELECT\s+.*\+|execute\(.*f['\"]",
                "action": "block",
                "message": "Possible SQL injection — use parameterised queries instead.",
            },
            {
                "rule_id": "owasp_crypto_guard",
                "description": "Warn on MD5/SHA1 for password hashing (OWASP A02)",
                "match_pattern": r"md5|sha1",
                "action": "warn",
                "message": "MD5/SHA1 is weak for password hashing — use bcrypt or argon2.",
            },
            {
                "rule_id": "owasp_hardcoded_role_guard",
                "description": "Warn on hardcoded role/permission strings (OWASP A01)",
                "match_pattern": r"role\s*==\s*['\"]admin['\"]|if.*['\"]superuser['\"]",
                "action": "warn",
                "message": "Hardcoded role check — use a centralised RBAC/permission system instead.",
            },
            {
                "rule_id": "owasp_weak_session_guard",
                "description": "Block weak session token generation (OWASP A07)",
                "match_pattern": r"random\.random\(\).*session|Math\.random\(\).*token",
                "action": "block",
                "message": "Weak randomness for session/token — use secrets.token_hex() or crypto.randomBytes().",
            },
            {
                "rule_id": "owasp_ssrf_guard",
                "description": "Warn on unvalidated URL fetch from user input (OWASP A10)",
                "match_pattern": r"requests\.get\(.*request\.|fetch\(.*req\.(query|body|params)",
                "action": "warn",
                "message": "Possible SSRF — validate and allowlist URLs before making outbound requests.",
            },
            {
                "rule_id": "owasp_eval_guard",
                "description": "Block eval() calls (OWASP A03 code injection)",
                "match_pattern": r"\beval\s*\(",
                "action": "block",
                "message": "eval() enables code injection — avoid it.",
            },
        ],
        "security_rules": [
            {
                "rule_id": "owasp_xss",
                "category": "OWASP",
                "description": "Cross-site scripting via innerHTML assignment",
                "pattern": r"innerHTML\s*=",
                "severity": "high",
                "finding_type": "vulnerability",
            },
            {
                "rule_id": "owasp_sqli",
                "category": "OWASP",
                "description": "SQL injection via string concatenation",
                "pattern": r"SELECT.*\+|execute.*format\(",
                "severity": "critical",
                "finding_type": "vulnerability",
            },
            {
                "rule_id": "owasp_path_traversal",
                "category": "OWASP",
                "description": "Path traversal with ../ sequences",
                "pattern": r"\.\./",
                "severity": "high",
                "finding_type": "vulnerability",
            },
            {
                "rule_id": "owasp_open_redirect",
                "category": "OWASP",
                "description": "Open redirect via unvalidated redirect parameter",
                "pattern": r"redirect\(.*request\.(args|params|query)",
                "severity": "medium",
                "finding_type": "vulnerability",
            },
            {
                "rule_id": "owasp_broken_access_control",
                "category": "OWASP",
                "description": "Direct object reference without ownership check (OWASP A01)",
                "pattern": r"WHERE\s+id\s*=\s*\$|\.find\(req\.(params|query)\.(id|user_id)\)",
                "severity": "high",
                "finding_type": "vulnerability",
            },
            {
                "rule_id": "owasp_no_rate_limit",
                "category": "OWASP",
                "description": "Auth endpoint without rate limiting annotation (OWASP A07)",
                "pattern": r"@app\.(post|route)\(['\"]/(login|signin|auth|token)",
                "severity": "medium",
                "finding_type": "misconfiguration",
            },
            {
                "rule_id": "owasp_sensitive_log",
                "category": "OWASP",
                "description": "Sensitive data written to logs (OWASP A09)",
                "pattern": r"(logger|logging|console\.log)\(.*?(password|token|secret)",
                "severity": "high",
                "finding_type": "vulnerability",
            },
            {
                "rule_id": "owasp_ssrf",
                "category": "OWASP",
                "description": "SSRF via user-controlled URL in outbound request (OWASP A10)",
                "pattern": r"requests\.(get|post)\(.*?(request\.|req\.|params\[|query\[)",
                "severity": "critical",
                "finding_type": "vulnerability",
            },
            {
                "rule_id": "owasp_debug_enabled",
                "category": "OWASP",
                "description": "Debug mode left on in production config (OWASP A05)",
                "pattern": r"app\.run\(.*debug\s*=\s*True|DEBUG\s*=\s*True",
                "severity": "medium",
                "finding_type": "misconfiguration",
            },
            {
                "rule_id": "owasp_deserialization",
                "category": "OWASP",
                "description": "Unsafe deserialization of user input (OWASP A08)",
                "pattern": r"pickle\.loads\(|yaml\.load\([^,)]*\)|unserialize\(",
                "severity": "critical",
                "finding_type": "vulnerability",
            },
        ],
    },
    "soc2": {
        "guard_rules": [
            {
                "rule_id": "soc2_hardcoded_secret_guard",
                "description": "Block hardcoded secrets in source (SOC2 CC6.1)",
                "match_pattern": r"(password|secret|api_key)\s*=\s*['\"][^'\"]{8,}",
                "action": "block",
                "message": "Hardcoded credential detected — use environment variables or a secrets manager.",
            },
            {
                "rule_id": "soc2_log_pii_guard",
                "description": "Warn on logging email/SSN to console (SOC2 CC7.2)",
                "match_pattern": r"(console\.log|print|logger)\(.*email",
                "action": "warn",
                "message": "Possible PII logged to console — ensure logs are scrubbed before production.",
            },
        ],
        "security_rules": [
            {
                "rule_id": "soc2_hardcoded_password",
                "category": "SOC2",
                "description": "Hardcoded password in source",
                "pattern": r"password\s*=\s*['\"][^'\"]{6,}['\"]",
                "severity": "critical",
                "finding_type": "secret",
            },
            {
                "rule_id": "soc2_unencrypted_storage",
                "category": "SOC2",
                "description": "Unencrypted local file write with sensitive name",
                "pattern": r"open\(['\"].*secret.*['\"],\s*['\"]w",
                "severity": "high",
                "finding_type": "vulnerability",
            },
            {
                "rule_id": "soc2_debug_mode_prod",
                "category": "SOC2",
                "description": "DEBUG=True in production config",
                "pattern": r"DEBUG\s*=\s*True",
                "severity": "medium",
                "finding_type": "misconfiguration",
            },
        ],
    },
    "hipaa": {
        "guard_rules": [
            {
                "rule_id": "hipaa_phi_guard",
                "description": "Block writing PHI patterns to unprotected storage (HIPAA §164.312)",
                "match_pattern": r"(patient_id|ssn|dob|date_of_birth|medical_record)",
                "action": "warn",
                "message": "PHI field detected — ensure data is encrypted at rest and access is logged.",
            },
            {
                "rule_id": "hipaa_unencrypted_phi_guard",
                "description": "Block PHI transmission without TLS",
                "match_pattern": r"http://.*patient|http://.*health",
                "action": "block",
                "message": "PHI over plain HTTP is a HIPAA violation — use HTTPS.",
            },
        ],
        "security_rules": [
            {
                "rule_id": "hipaa_ssn_pattern",
                "category": "HIPAA",
                "description": "Social Security Number in source",
                "pattern": r"\b\d{3}-\d{2}-\d{4}\b",
                "severity": "critical",
                "finding_type": "pii",
            },
            {
                "rule_id": "hipaa_dob_field",
                "category": "HIPAA",
                "description": "Date of birth field without encryption annotation",
                "pattern": r"date_of_birth|dob\s*=",
                "severity": "high",
                "finding_type": "pii",
            },
            {
                "rule_id": "hipaa_medical_record",
                "category": "HIPAA",
                "description": "Medical record number hardcoded",
                "pattern": r"mrn\s*=\s*['\"]|medical_record_number\s*=",
                "severity": "high",
                "finding_type": "pii",
            },
        ],
    },
    "pci_dss": {
        "guard_rules": [
            {
                "rule_id": "pci_pan_guard",
                "description": "Block writing card numbers to logs or non-encrypted storage (PCI DSS Req 3)",
                "match_pattern": r"\b4[0-9]{12}(?:[0-9]{3})?\b|\b5[1-5][0-9]{14}\b",
                "action": "block",
                "message": "Card number pattern detected — never log or store PANs in plaintext.",
            },
            {
                "rule_id": "pci_cvv_guard",
                "description": "Block storage of CVV/CVC values (PCI DSS Req 3.2)",
                "match_pattern": r"(cvv|cvc|cvv2)\s*=",
                "action": "block",
                "message": "CVV must never be stored post-authorization (PCI DSS 3.2.1).",
            },
        ],
        "security_rules": [
            {
                "rule_id": "pci_card_number",
                "category": "PCI-DSS",
                "description": "Credit card PAN in source",
                "pattern": r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14})\b",
                "severity": "critical",
                "finding_type": "pii",
            },
            {
                "rule_id": "pci_cvv_stored",
                "category": "PCI-DSS",
                "description": "CVV/CVC value stored in code",
                "pattern": r"(cvv|cvc|security_code)\s*=\s*['\"]?\d{3,4}",
                "severity": "critical",
                "finding_type": "secret",
            },
            {
                "rule_id": "pci_weak_tls",
                "category": "PCI-DSS",
                "description": "Weak TLS version forced in config",
                "pattern": r"TLSv1\b|ssl\.PROTOCOL_TLSv1\b",
                "severity": "high",
                "finding_type": "misconfiguration",
            },
        ],
    },
    "startup_baseline": {
        "guard_rules": [
            {
                "rule_id": "baseline_no_api_keys_guard",
                "description": "Block hardcoded API keys in source",
                "match_pattern": r"(api_key|apikey|access_token)\s*=\s*['\"][A-Za-z0-9_\-]{20,}",
                "action": "block",
                "message": "Hardcoded API key — move to environment variables.",
            },
        ],
        "security_rules": [
            {
                "rule_id": "baseline_hardcoded_token",
                "category": "Baseline",
                "description": "Hardcoded bearer token",
                "pattern": r"Bearer [A-Za-z0-9\-_\.]{20,}",
                "severity": "high",
                "finding_type": "secret",
            },
            {
                "rule_id": "baseline_weak_random",
                "category": "Baseline",
                "description": "Math.random() used for security purposes",
                "pattern": r"Math\.random\(\).*token|secret.*Math\.random\(\)",
                "severity": "medium",
                "finding_type": "vulnerability",
            },
            {
                "rule_id": "baseline_console_error_stack",
                "category": "Baseline",
                "description": "Stack trace leaked to client",
                "pattern": r"res\.send\(err\.stack\)|response\.write\(e\.stack\)",
                "severity": "medium",
                "finding_type": "vulnerability",
            },
        ],
    },
}


# ── Endpoints ─────────────────────────────────────────────────────────────────

LEGACY_SLUG_MAP = {
    "owasp_top10":      "conduct-owasp",
    "soc2":             "conduct-soc2",
    "hipaa":            "conduct-hipaa",
    "pci_dss":          "conduct-pci-dss",
    "startup_baseline": "conduct-base",
}
# reverse: conduct-slug → canonical pack_id
_SLUG_TO_PACK_ID = {v: k for k, v in LEGACY_SLUG_MAP.items()}


class PackStatusOut(BaseModel):
    pack_id: str
    guard_rules_installed: int


class InstalledPacksOut(BaseModel):
    installed: list[str]


class AvailablePackOut(BaseModel):
    slug: str
    name: str
    description: str | None
    tier: str
    rule_count: int


@router.get("/packs/available", response_model=list[AvailablePackOut])
def list_available_packs(
    db: Session = Depends(get_db),
    _workspace_id: str = Depends(get_workspace_id),
):
    """Return all skill packs in the catalog."""
    packs = db.query(SkillPack).order_by(SkillPack.slug, SkillPack.version.desc()).all()
    seen: set[str] = set()
    out = []
    for p in packs:
        if p.slug in seen:
            continue
        seen.add(p.slug)
        out.append(AvailablePackOut(
            slug=p.slug,
            name=p.name,
            description=p.description,
            tier=p.tier,
            rule_count=len(p.rules or []),
        ))
    return out


@router.get("/packs/installed", response_model=InstalledPacksOut)
def list_installed_packs(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    ws_uuid = uuid.UUID(workspace_id)

    # primary: new workspace_skill_packs table
    new_packs = (
        db.query(WorkspaceSkillPack.pack_slug)
        .filter(WorkspaceSkillPack.workspace_id == ws_uuid)
        .all()
    )
    if new_packs:
        return InstalledPacksOut(installed=sorted(_SLUG_TO_PACK_ID.get(r[0], r[0]) for r in new_packs))

    # fallback: legacy guard_policies.pack_id (pre-migration workspaces)
    guard_packs = (
        db.query(GuardPolicy.pack_id)
        .filter(GuardPolicy.workspace_id == ws_uuid, GuardPolicy.pack_id.isnot(None))
        .distinct()
        .all()
    )
    legacy = {LEGACY_SLUG_MAP.get(r[0], r[0]) for r in guard_packs}
    return InstalledPacksOut(installed=sorted(legacy))


@router.post("/packs/{pack_id}/install", response_model=PackStatusOut)
def install_pack(
    pack_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.edit")),
):
    if pack_id not in COMPLIANCE_PACKS:
        raise HTTPException(status_code=404, detail=f"Pack '{pack_id}' not found")

    pack = COMPLIANCE_PACKS[pack_id]
    ws_uuid = uuid.UUID(workspace_id)
    now = datetime.now(timezone.utc)

    guard_count = 0
    for rule in pack.get("guard_rules", []):
        existing = (
            db.query(GuardPolicy)
            .filter(GuardPolicy.workspace_id == ws_uuid, GuardPolicy.rule_id == rule["rule_id"])
            .first()
        )
        if existing is None:
            db.add(GuardPolicy(
                workspace_id=ws_uuid,
                rule_id=rule["rule_id"],
                description=rule.get("description", "")[:255],
                match_pattern=rule.get("match_pattern"),
                action=rule["action"],
                message=rule.get("message"),
                enabled=True,
                builtin=False,
                pack_id=pack_id,
                created_at=now,
                updated_at=now,
            ))
        else:
            existing.description = rule.get("description", existing.description)[:255]
            existing.match_pattern = rule.get("match_pattern", existing.match_pattern)
            existing.action = rule.get("action", existing.action)
            existing.message = rule.get("message", existing.message)
            existing.pack_id = pack_id
            existing.enabled = True
            existing.archived_at = None  # unarchive if previously deleted
            existing.updated_at = now
        guard_count += 1

    # dual-write: register in workspace_skill_packs so compute_policy() sees it
    new_slug = LEGACY_SLUG_MAP.get(pack_id, f"conduct-{pack_id.replace('_', '-')}")
    existing_wsp = db.get(WorkspaceSkillPack, (ws_uuid, new_slug))
    if not existing_wsp:
        db.add(WorkspaceSkillPack(
            workspace_id=ws_uuid,
            pack_slug=new_slug,
            installed_by="compliance:install",
            installed_at=now,
        ))
    invalidate_policy_cache(db, ws_uuid)

    db.commit()
    return PackStatusOut(pack_id=pack_id, guard_rules_installed=guard_count)


@router.delete("/packs/{pack_id}/uninstall", response_model=PackStatusOut)
def uninstall_pack(
    pack_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.edit")),
):
    if pack_id not in COMPLIANCE_PACKS:
        raise HTTPException(status_code=404, detail=f"Pack '{pack_id}' not found")

    ws_uuid = uuid.UUID(workspace_id)

    guard_deleted = (
        db.query(GuardPolicy)
        .filter(GuardPolicy.workspace_id == ws_uuid, GuardPolicy.pack_id == pack_id)
        .delete(synchronize_session=False)
    )

    # dual-write: remove from workspace_skill_packs
    new_slug = LEGACY_SLUG_MAP.get(pack_id, f"conduct-{pack_id.replace('_', '-')}")
    db.query(WorkspaceSkillPack).filter(
        WorkspaceSkillPack.workspace_id == ws_uuid,
        WorkspaceSkillPack.pack_slug == new_slug,
    ).delete(synchronize_session=False)
    invalidate_policy_cache(db, ws_uuid)

    db.commit()
    return PackStatusOut(pack_id=pack_id, guard_rules_installed=guard_deleted)
