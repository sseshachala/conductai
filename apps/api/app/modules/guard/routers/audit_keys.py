"""GET /.well-known/conduct-audit-keys: public keys for audit checkpoint verification.

Deliberately unauthenticated. An auditor or ``conduct audit verify`` must be
able to fetch the verification keys independently of the workspace being
audited (otherwise the operator could hand over a matching forged key). The
response is public-key material only: key_id, algorithm, base64 SubjectPublicKeyInfo
DER, created_at. No workspace data, no private key, no KMS identifiers.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.guard.audit_signing import published_keys

well_known_router = APIRouter(tags=["guard-audit"])


@well_known_router.get("/.well-known/conduct-audit-keys")
def conduct_audit_keys(db: Session = Depends(get_db)):
    try:
        keys = published_keys(db)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Audit keys unavailable") from exc
    return JSONResponse({"keys": keys}, headers={"Cache-Control": "public, max-age=300"})
