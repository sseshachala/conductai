"""Okta agent JWT resolution (split from app.core.auth; re-exported there)."""
import contextvars

import structlog
from fastapi import HTTPException
from sqlalchemy.orm import Session

log = structlog.get_logger("app.core.auth")

# Per-request dedupe for Okta audit emissions. FastAPI runs each request in a
# fresh async context, so this ContextVar naturally resets between requests.
# Same token resolved twice in one request → one audit row, not two (fixes
# the /auth/whoami double-emit).
_okta_audit_emitted: contextvars.ContextVar[set[str] | None] = contextvars.ContextVar(
    "okta_audit_emitted", default=None,
)


def _resolve_okta_jwt(token: str, db: Session):
    """Try to resolve `token` as an Okta-signed JWT (#1056).

    Returns (AgentIdentity, None) on success, matching the shape of
    `_resolve_agent_token(cond_api_*, ...)`. Returns None if the token is not
    a JWT or its `iss` is not configured for any workspace with
    Okta agent trust — the caller falls through to the next auth path
    (Clerk). Any real verification failure raises HTTPException(401).
    """
    if token.count(".") != 2:
        return None

    from app.core.okta_jwt import OktaJWTError, verify_okta_jwt
    from app.modules.auth.federation.okta_agent import candidates, valid_config, workspace_scope
    from app.modules.agent_identity.models import AgentIdentity
    import jwt as _pyjwt

    try:
        unverified = _pyjwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_exp": False,
                "verify_aud": False,
                "verify_iss": False,
            },
        )
    except Exception:
        return None
    iss = unverified.get("iss")
    if not iss:
        return None

    rows = candidates(db, iss)
    if not rows:
        return None  # unconfigured issuer — fall through to Clerk

    # #1057 — hash-chained audit event for every verify attempt. Wrapped in
    # try/except so audit failures never break auth.
    import time as _time
    _t0 = _time.perf_counter()
    unverified_sub = unverified.get("sub", "")

    def _emit_audit(*, workspace_id, decision: str, sub: str, reason: str | None = None):
        # Per-request dedupe: if the same (workspace, decision, sub) was already
        # audited in this request, skip. See _okta_audit_emitted.
        _seen = _okta_audit_emitted.get()
        if _seen is None:
            _seen = set()
            _okta_audit_emitted.set(_seen)
        _key = f"{workspace_id}|{decision}|{sub}"
        if _key in _seen:
            return
        _seen.add(_key)
        try:
            from app.modules.guard.models import GuardAuditEvent, chain_hash_for_insert
            from datetime import datetime, timezone as _tz
            _now = datetime.now(_tz.utc)
            _tool = "auth.okta_jwt.verify"
            prev_hash, entry_hash = chain_hash_for_insert(db, workspace_id, _now, _tool, decision)
            db.add(GuardAuditEvent(
                workspace_id=workspace_id,
                user_email=sub or "unknown",
                ai_tool="okta_jwt",
                tool_call=_tool,
                source="okta_jwt",
                input_summary=f"iss={iss}",
                decision=decision,
                rule_id="okta_jwt",
                rule_message=reason,
                ts=_now,
                duration_ms=int((_time.perf_counter() - _t0) * 1000),
                previous_hash=prev_hash,
                entry_hash=entry_hash,
            ))
            db.commit()
        except Exception as _e:  # never let audit break auth
            log.warning("okta.audit.emit_failed", error=str(_e))
            try:
                db.rollback()
            except Exception:
                pass

    last_error: Exception | None = OktaJWTError("trust is disabled or requires review")
    matches = []
    for row in rows:
        if row.config.get("status") != "active" or not valid_config(row.config):
            continue
        aud = row.config["audience"]
        try:
            claims = verify_okta_jwt(token, issuer=iss, audience=aud)
        except OktaJWTError as e:
            last_error = e
            continue
        sub = claims.get("sub")
        if not sub:
            _emit_audit(workspace_id=row.workspace_id, decision="blocked", sub=unverified_sub, reason="missing sub claim")
            raise HTTPException(status_code=401, detail="Okta JWT missing sub claim")
        with workspace_scope(db, row.workspace_id):
            ai = (
                db.query(AgentIdentity)
                .filter(
                    AgentIdentity.workspace_id == row.workspace_id,
                    AgentIdentity.source == "okta",
                    AgentIdentity.source_id == sub,
                )
                .first()
            )
        if not ai:
            _emit_audit(workspace_id=row.workspace_id, decision="blocked", sub=sub, reason="identity not synced")
            raise HTTPException(status_code=401, detail="Okta identity not synced — run Okta sync in Conduct")
        lifecycle = getattr(ai, "lifecycle_state", None)
        if lifecycle in ("deactivated", "expired"):
            _emit_audit(workspace_id=row.workspace_id, decision="blocked", sub=sub, reason=f"lifecycle={lifecycle}")
            raise HTTPException(status_code=401, detail=f"Agent identity is {lifecycle}")
        matches.append((ai, row.workspace_id, sub))

    if len(matches) > 1:
        _emit_audit(workspace_id=matches[0][1], decision="blocked", sub=matches[0][2], reason="ambiguous workspace trust")
        raise HTTPException(status_code=401, detail="Okta identity matches multiple workspaces")
    if matches:
        ai, workspace, sub = matches[0]
        _emit_audit(workspace_id=workspace, decision="allowed", sub=sub)
        return ai, None

    # All configured workspaces rejected the token
    _emit_audit(workspace_id=rows[0].workspace_id, decision="blocked", sub=unverified_sub, reason=str(last_error))
    raise HTTPException(status_code=401, detail=f"Okta JWT verification failed: {last_error}")
