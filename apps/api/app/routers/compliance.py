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
from app.modules.guard.models import GuardPolicy
from app.models.security_config import SecurityPolicy

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

class PackStatusOut(BaseModel):
    pack_id: str
    guard_rules_installed: int
    security_rules_installed: int


class InstalledPacksOut(BaseModel):
    installed: list[str]


@router.get("/packs/installed", response_model=InstalledPacksOut)
def list_installed_packs(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    ws_uuid = uuid.UUID(workspace_id)
    guard_packs = (
        db.query(GuardPolicy.pack_id)
        .filter(GuardPolicy.workspace_id == ws_uuid, GuardPolicy.pack_id.isnot(None))
        .distinct()
        .all()
    )
    sec_packs = (
        db.query(SecurityPolicy.pack_id)
        .filter(SecurityPolicy.workspace_id == ws_uuid, SecurityPolicy.pack_id.isnot(None))
        .distinct()
        .all()
    )
    installed = sorted({r[0] for r in guard_packs} | {r[0] for r in sec_packs})
    return InstalledPacksOut(installed=installed)


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

    sec_count = 0
    for rule in pack.get("security_rules", []):
        existing = (
            db.query(SecurityPolicy)
            .filter(SecurityPolicy.workspace_id == ws_uuid, SecurityPolicy.rule_id == rule["rule_id"])
            .first()
        )
        if existing is None:
            db.add(SecurityPolicy(
                workspace_id=ws_uuid,
                rule_id=rule["rule_id"],
                description=rule.get("description", "")[:255],
                pattern=rule.get("pattern"),
                category=rule.get("category"),
                finding_type=rule.get("finding_type", "vulnerability"),
                severity=rule.get("severity", "medium"),
                enabled=True,
                builtin=False,
                pack_id=pack_id,
                created_at=now,
                updated_at=now,
            ))
        else:
            existing.description = rule.get("description", existing.description)[:255]
            existing.pattern = rule.get("pattern", existing.pattern)
            existing.category = rule.get("category", existing.category)
            existing.pack_id = pack_id
            existing.updated_at = now
        sec_count += 1

    db.commit()
    return PackStatusOut(pack_id=pack_id, guard_rules_installed=guard_count, security_rules_installed=sec_count)


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
    sec_deleted = (
        db.query(SecurityPolicy)
        .filter(SecurityPolicy.workspace_id == ws_uuid, SecurityPolicy.pack_id == pack_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return PackStatusOut(pack_id=pack_id, guard_rules_installed=guard_deleted, security_rules_installed=sec_deleted)
