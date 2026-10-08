"""Conduct agent/API/member token resolvers (split from app.core.auth; re-exported there)."""
from fastapi import HTTPException
from sqlalchemy.orm import Session


def _trial_member(db: Session, identity):
    """Trial identities have a separate owner binding, never a CLI-link takeover."""
    if getattr(identity, "source", None) != "conduct_trial":
        return None
    owner = getattr(identity, "owner_user_id", None)
    if not isinstance(owner, str) or not owner:
        return None
    from sqlalchemy import text
    row = db.execute(text("""
        SELECT member.clerk_user_id
        FROM guard_member_config member
        JOIN workspace_users membership
          ON membership.workspace_id = member.workspace_id
         AND membership.clerk_user_id = member.clerk_user_id
        JOIN workspaces workspace ON workspace.id = member.workspace_id
        WHERE member.workspace_id = :ws AND member.clerk_user_id = :uid
          AND member.active = true AND workspace.owner_id = :uid
        LIMIT 1
    """), {"ws": str(identity.workspace_id), "uid": owner}).fetchone()
    return row.clerk_user_id if row else None


def _resolve_agent_token(token: str, db: Session):
    """Validate a cond_agt_* or cond_api_* token and return (AgentIdentity, clerk_user_id).
    Raises HTTPException on invalid/expired token or missing GMC link.
    For api tokens (token_type='api') there is no GMC link by design — returns (ai, None).
    Shared by get_workspace_id, get_user_id, get_guard_hook_auth to avoid double-decrypt.
    """
    from app.modules.agent_identity.models import AgentIdentity
    from app.core.crypto import decrypt
    from sqlalchemy import text as _t
    from datetime import datetime, timezone as _tz
    from app.modules.agent_identity.credentials import SESSION_ACCESS_PREFIX, find_session_credential
    if token.startswith(SESSION_ACCESS_PREFIX):
        matched = find_session_credential(token, db)
        if matched is None:
            raise HTTPException(status_code=401, detail="Invalid agent token")
        ai, expires_at = matched
        # #2162 — a NULL expiry column (or a mocked expiry in tests) would
        # otherwise trip TypeError on the comparison. Treat missing
        # ``expires_at`` as "no explicit expiry"; the credential is still
        # subject to ``lifecycle_state`` below.
        if expires_at is not None and expires_at <= datetime.now(_tz.utc):
            raise HTTPException(status_code=401, detail="Agent token expired")
        if ai.token_type != "cli" or ai.lifecycle_state in ("deactivated", "expired"):
            raise HTTPException(status_code=401, detail="Agent identity is inactive")
        row = db.execute(
            _t("SELECT clerk_user_id FROM guard_member_config "
               "WHERE agent_identity_id = :aid AND workspace_id = :ws AND active = true LIMIT 1"),
            {"aid": ai.id, "ws": str(ai.workspace_id)},
        ).fetchone()
        if not row or not _has_workspace_membership(db, ai.workspace_id, row.clerk_user_id):
            raise HTTPException(status_code=401, detail="Agent token membership revoked")
        return ai, row.clerk_user_id
    for ai in db.query(AgentIdentity).filter(AgentIdentity.token_prefix == token[:13]).all():
        try:
            if decrypt(ai.token_encrypted).get("token") == token:
                if ai.expires_at and ai.expires_at < datetime.now(_tz.utc):
                    raise HTTPException(status_code=401, detail="Agent token expired — run `conduct login`")
                # Fail-secure lifecycle guard (#1037). Deactivated/expired
                # identities cannot authenticate even if their token has not
                # expired. Applies to cond_agt_*, cond_api_*, and legacy paths.
                _lifecycle = getattr(ai, "lifecycle_state", None)
                if _lifecycle in ("deactivated", "expired"):
                    raise HTTPException(status_code=401, detail=f"Agent identity is {_lifecycle}")
                # External identities (Okta-imported, etc.) authenticate via
                # their source system, never through Conduct's token path.
                # #1036 defense-in-depth against auth confusion.
                if getattr(ai, "token_type", "cli") == "external":
                    raise HTTPException(status_code=401, detail="External agent identity cannot authenticate via Conduct token path")
                token_type = getattr(ai, 'token_type', 'cli')
                # API tokens have no guard_member_config row by design and are
                # workspace credentials rather than a user's login session.
                if token_type == 'api':
                    return ai, None
                if getattr(ai, "source", None) == "conduct_trial":
                    owner = _trial_member(db, ai)
                    if not owner:
                        raise HTTPException(status_code=401, detail="Agent token membership revoked")
                    return ai, owner
                row = db.execute(
                    _t("SELECT clerk_user_id FROM guard_member_config WHERE agent_identity_id = :aid LIMIT 1"),
                    {"aid": ai.id},
                ).fetchone()
                clerk_user_id = row.clerk_user_id if row else None
                if not clerk_user_id or not _has_workspace_membership(db, ai.workspace_id, clerk_user_id):
                    raise HTTPException(status_code=401, detail="Agent token membership revoked")
                return ai, clerk_user_id
        except HTTPException:
            raise
        except Exception:
            continue
    raise HTTPException(status_code=401, detail="Invalid agent token")


# ─── Shared agent token resolver ──────────────────────────────────────────────

_AGENT_PREFIX  = "cond_agt_"
_API_PREFIX    = "cond_api_"
_MEMBER_PREFIX = "guard-mt-"
_PREFIX_LOOKUP_LEN = len(_AGENT_PREFIX) + 4  # same length for all conduct token types


def _has_workspace_membership(db: Session, workspace_id, clerk_user_id: str) -> bool:
    from sqlalchemy import text as _text

    return db.execute(
        _text("""
            SELECT 1 FROM workspace_users
            WHERE workspace_id = :ws AND clerk_user_id = :uid
            LIMIT 1
        """),
        {"ws": str(workspace_id), "uid": clerk_user_id},
    ).fetchone() is not None


def resolve_agent_token(token: str, db: Session) -> tuple[str, str] | None:
    """Resolve any Conduct agent token → (workspace_id, clerk_user_id) or None.

    Accepts: cond_agt_*, cond_api_*, guard-mt-* (legacy member tokens).
    Used by proxy, MCP, WebSocket, and any other auth surface.

    Fail-secure: expired tokens return None. Callers that need to distinguish
    "expired" from "unknown" (e.g. proxy UX copy) can call token_is_expired()
    on the same token to disambiguate before rendering the error message.
    """
    from sqlalchemy import text as _text
    from datetime import datetime, timezone as _tz
    from app.modules.agent_identity.credentials import SESSION_ACCESS_PREFIX

    if token.startswith(SESSION_ACCESS_PREFIX):
        try:
            identity, user_id = _resolve_agent_token(token, db)
            return str(identity.workspace_id), user_id
        except HTTPException:
            return None

    if token.startswith((_AGENT_PREFIX, _API_PREFIX)):
        from app.core.crypto import decrypt as _decrypt
        from app.modules.agent_identity.models import AgentIdentity

        prefix = token[:_PREFIX_LOOKUP_LEN]
        for ai_row in db.query(AgentIdentity).filter(AgentIdentity.token_prefix == prefix).all():
            try:
                if _decrypt(ai_row.token_encrypted).get("token") != token:
                    continue
            except Exception:
                continue

            # Reject expired session tokens (cond_agt_ has 8h TTL). API tokens
            # (cond_api_) leave expires_at=NULL by design, so this only bites
            # session tokens.
            if ai_row.expires_at and ai_row.expires_at < datetime.now(_tz.utc):
                return None

            # Fail-secure on identity lifecycle state (#1037).
            # deactivated or expired identities cannot authenticate regardless
            # of token freshness. pending_review is a signal, not a stop.
            _lifecycle = getattr(ai_row, "lifecycle_state", None)
            if _lifecycle in ("deactivated", "expired"):
                return None

            if getattr(ai_row, "source", None) == "conduct_trial":
                owner = _trial_member(db, ai_row)
                return (str(ai_row.workspace_id), owner) if owner else None

            # Try guard_member_config link first (session tokens always have this)
            member = db.execute(
                _text("""
                    SELECT workspace_id::text, clerk_user_id
                    FROM guard_member_config
                    WHERE agent_identity_id = :aid AND active = true
                    LIMIT 1
                """),
                {"aid": ai_row.id},
            ).fetchone()
            if member:
                if not _has_workspace_membership(db, member[0], member[1]):
                    return None
                return (member[0], member[1])

            # A session token must always remain linked to a live member. Do
            # not reinterpret an unlinked/revoked session token as an API key.
            if token.startswith(_AGENT_PREFIX):
                return None

            # API tokens: fall back to creator or synthetic label.
            creator = getattr(ai_row, "created_by_clerk_user_id", None)
            if creator:
                return (str(ai_row.workspace_id), creator)

            label = getattr(ai_row, "token_name", None) or getattr(ai_row, "name", "api-token")
            return (str(ai_row.workspace_id), f"api:{label}")

        return None

    # Legacy guard-mt-* member token
    bare = token[len(_MEMBER_PREFIX):] if token.startswith(_MEMBER_PREFIX) else token
    row = db.execute(
        _text("""
            SELECT gmc.workspace_id::text, gmc.clerk_user_id
            FROM guard_member_config gmc
            JOIN workspace_users wu
              ON wu.workspace_id = gmc.workspace_id
             AND wu.clerk_user_id = gmc.clerk_user_id
            WHERE gmc.member_token = :tok AND gmc.active = true
            LIMIT 1
        """),
        {"tok": bare},
    ).fetchone()
    return (row[0], row[1]) if row else None


def resolve_agent_identity_row(token: str, db: Session):
    """Same lookup semantics as ``resolve_agent_token`` but returns the
    AgentIdentity row instead of the (ws, user) tuple.

    Returns None for unknown / expired / deactivated tokens and for legacy
    ``guard-mt-*`` member tokens (which don't have a 1:1 AgentIdentity row).

    Used by PEPs that need identity fields beyond auth — e.g. ``risk_tier``
    to populate PolicyContext for tier-gated policies.
    """
    from datetime import datetime, timezone as _tz
    from app.modules.agent_identity.credentials import SESSION_ACCESS_PREFIX

    if token.startswith(SESSION_ACCESS_PREFIX):
        try:
            return _resolve_agent_token(token, db)[0]
        except HTTPException:
            return None

    if not token.startswith((_AGENT_PREFIX, _API_PREFIX)):
        return None

    from app.core.crypto import decrypt as _decrypt
    from app.modules.agent_identity.models import AgentIdentity

    prefix = token[:_PREFIX_LOOKUP_LEN]
    for ai_row in db.query(AgentIdentity).filter(AgentIdentity.token_prefix == prefix).all():
        try:
            if _decrypt(ai_row.token_encrypted).get("token") != token:
                continue
        except Exception:
            continue
        if ai_row.expires_at and ai_row.expires_at < datetime.now(_tz.utc):
            return None
        _lifecycle = getattr(ai_row, "lifecycle_state", None)
        if _lifecycle in ("deactivated", "expired"):
            return None
        return ai_row
    return None


def token_is_expired(token: str, db: Session) -> bool:
    """True iff token matches a real AgentIdentity row whose expires_at has passed.

    Used by proxy 401 handler to render "session expired — run conduct login"
    instead of the generic "not recognized" message. Cheap: one indexed lookup
    on token_prefix, decrypt only the prefix-collision matches.
    """
    if not token.startswith((_AGENT_PREFIX, _API_PREFIX)):
        return False
    from datetime import datetime, timezone as _tz
    from app.core.crypto import decrypt as _decrypt
    from app.modules.agent_identity.models import AgentIdentity
    from app.modules.agent_identity.credentials import SESSION_ACCESS_PREFIX, find_session_credential

    if token.startswith(SESSION_ACCESS_PREFIX):
        matched = find_session_credential(token, db)
        return bool(matched and matched[1] <= datetime.now(_tz.utc))

    prefix = token[:_PREFIX_LOOKUP_LEN]
    for ai_row in db.query(AgentIdentity).filter(AgentIdentity.token_prefix == prefix).all():
        try:
            if _decrypt(ai_row.token_encrypted).get("token") != token:
                continue
        except Exception:
            continue
        return bool(ai_row.expires_at and ai_row.expires_at < datetime.now(_tz.utc))
    return False
