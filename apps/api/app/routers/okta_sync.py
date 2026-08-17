"""Pull Okta apps into agent_identities as Guard principals.

Phase 1 of #1036. One endpoint:

    POST /workspaces/{ws}/integrations/okta/sync
        body: { domain, token, limit }
        response: { imported, updated, skipped, errors }

Idempotent via the (workspace_id, source, source_id) partial unique index
added in migration 0090. Imported rows carry `source="okta"`,
`token_type="external"`, and a placeholder token that no Conduct token
resolver accepts (defense-in-depth against auth confusion). Runtime
enforcement flows through Guard using the imported identity as principal.

We never sync Okta secrets — only identity metadata. Okta owns auth,
Conduct governs authority.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.crypto import decrypt, encrypt
from app.core.database import get_db
from app.models.integration import Integration
from app.modules.agent_identity.models import AgentIdentity


_OKTA_HANDLE = "okta"  # single Integration row per workspace (see #1051 for multi-tenant)


router = APIRouter(prefix="/workspaces/{workspace_id}/integrations/okta", tags=["okta-sync"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class OktaSyncRequest(BaseModel):
    domain: Optional[str] = Field(None, description="Okta domain like dev-XXXXXX.okta.com. Omit to use stored config.")
    token: Optional[str] = Field(None, description="Okta API token (SSWS). Omit to use stored config.")
    limit: int = Field(100, ge=1, le=200, description="Page size for Okta /api/v1/apps.")


class OktaSyncResponse(BaseModel):
    imported: int
    updated: int
    skipped: int
    errors: list[str]


class OktaConfigPut(BaseModel):
    # All fields optional so callers can update just the credentials, just
    # the JWT auth config, or both. Handler validates that the caller isn't
    # sending an empty body.
    domain: Optional[str] = Field(None, description="Okta domain like dev-XXXXXX.okta.com.")
    token: Optional[str] = Field(None, description="Okta API token (SSWS). Stored encrypted; never returned.")
    # JWT auth (#1056) — ships disabled until the operator flips the toggle.
    issuer: Optional[str] = Field(None, description="OAuth authorization server issuer, e.g. https://{domain}/oauth2/default")
    audience: Optional[str] = Field(None, description="Expected `aud` claim on Okta-issued JWTs, e.g. api://default")
    jwt_auth_enabled: Optional[bool] = Field(None, description="Enable Okta JWT authentication for this workspace")


class OktaConfigOut(BaseModel):
    configured: bool
    domain: Optional[str] = None
    token_prefix: Optional[str] = None  # first 4 chars, for the user to recognize
    last_synced_at: Optional[datetime] = None
    last_import: Optional[int] = None
    last_update: Optional[int] = None
    last_error: Optional[str] = None
    # JWT auth (#1056)
    issuer: Optional[str] = None
    audience: Optional[str] = None
    jwt_auth_enabled: bool = False


# ─── Mapping ────────────────────────────────────────────────────────────────

_OKTA_STATUS_TO_LIFECYCLE = {
    "ACTIVE": "active",
    "INACTIVE": "deactivated",
    "DELETED": "expired",
}

# Placeholder value stored in token fields for Okta-imported identities.
# Never a valid Conduct token — resolver additionally filters by
# token_type IN ('cli','api') so this row cannot authenticate.
_PLACEHOLDER = "okta_import_no_auth"


def _sanitize_domain(d: str) -> str:
    d = (d or "").strip().rstrip("/")
    for scheme in ("https://", "http://"):
        if d.startswith(scheme):
            d = d[len(scheme):]
    return d


def _extract_platform(app: dict) -> str:
    """AI Agent Import apps carry the source builder in settings.app.
    For non-AI apps, fall back to the Okta app 'name' field."""
    app_settings = (app.get("settings") or {}).get("app") or {}
    for key in ("agent_platform", "source_platform", "vendor", "builder"):
        v = app_settings.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip().lower()[:50]
    return (app.get("name") or "okta").lower()[:50]


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _okta_app_to_row(app: dict) -> dict:
    """Convert one /api/v1/apps entry into an AgentIdentity column dict."""
    status = (app.get("status") or "").upper()
    lifecycle = _OKTA_STATUS_TO_LIFECYCLE.get(status, "active")
    created_at = _parse_iso(app.get("created")) or datetime.now(timezone.utc)
    deactivated_at = _parse_iso(app.get("lastUpdated")) if lifecycle != "active" else None
    metadata = {
        "orn": app.get("orn"),
        "sign_on_mode": app.get("signOnMode"),
        "features": app.get("features") or [],
    }
    return {
        "name": (app.get("label") or app.get("name") or "unnamed")[:100],
        "provider": "okta",
        "source": "okta",
        "source_id": app.get("id"),
        "platform_of_origin": _extract_platform(app),
        "lifecycle_state": lifecycle,
        "created_at": created_at,
        "deactivated_at": deactivated_at,
        "metadata_json": metadata,
    }


def _fetch_first_owner(domain: str, token: str, app_id: str) -> Optional[str]:
    """Fetch /api/v1/apps/{id}/users?limit=1 and return the first user's
    login (email) as the owner. Returns None on any failure — owner
    enrichment is best-effort, never fails the sync."""
    url = f"https://{domain}/api/v1/apps/{app_id}/users?limit=1"
    req = urllib.request.Request(url, headers={
        "Authorization": f"SSWS {token}",
        "Accept": "application/json",
        "User-Agent": "Conduct-Guard-OktaSync/1.0",
    })
    try:
        # Okta API uses https:// consistently but urllib would still accept
        # file:// or other schemes if config is malformed. httpx rejects them
        # (closes bandit B310).
        import httpx
        resp = httpx.request(
            method=req.get_method(),
            url=req.full_url,
            headers=dict(req.headers),
            content=req.data if req.data else None,
            timeout=15,
        )
        data = resp.json()
    except Exception:
        return None
    if not isinstance(data, list) or not data:
        return None
    first = data[0] or {}
    # Prefer credentials.userName (Okta login/email), fall back to the user id.
    login = ((first.get("credentials") or {}).get("userName") or "").strip()
    if login:
        return login[:100]
    uid = (first.get("id") or "").strip()
    return uid[:100] or None


def _extract_next_link(link_header: str) -> Optional[str]:
    """Okta returns RFC 5988 Link headers for pagination."""
    if not link_header:
        return None
    for part in link_header.split(","):
        segments = [s.strip() for s in part.split(";")]
        if any(s == 'rel="next"' for s in segments):
            url_part = segments[0]
            if url_part.startswith("<") and url_part.endswith(">"):
                return url_part[1:-1]
    return None


# ─── Config storage (credential vault via Integration row) ──────────────────

def _load_config(db: Session, workspace_id: str) -> Optional[dict]:
    """Read stored Okta config from the Integration row for this workspace."""
    row = db.query(Integration).filter(
        Integration.workspace_id == uuid.UUID(workspace_id),
        Integration.handle == _OKTA_HANDLE,
    ).first()
    if not row or not row.encrypted_credentials:
        return None
    try:
        return decrypt(row.encrypted_credentials)
    except Exception:
        return None


def _save_config(db: Session, workspace_id: str, payload: dict) -> None:
    ws_uuid = uuid.UUID(workspace_id)
    row = db.query(Integration).filter(
        Integration.workspace_id == ws_uuid,
        Integration.handle == _OKTA_HANDLE,
    ).first()
    encrypted = encrypt(payload)
    if row:
        row.encrypted_credentials = encrypted
    else:
        db.add(Integration(
            workspace_id=ws_uuid,
            service=_OKTA_HANDLE,
            handle=_OKTA_HANDLE,
            auth_method="api_key",
            encrypted_credentials=encrypted,
        ))
    db.commit()


# ─── Config endpoints ───────────────────────────────────────────────────────

@router.get("/config", response_model=OktaConfigOut)
def get_okta_config(
    workspace_id: str,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
) -> OktaConfigOut:
    cfg = _load_config(db, workspace_id)
    row = db.query(Integration).filter(
        Integration.workspace_id == uuid.UUID(workspace_id),
        Integration.handle == _OKTA_HANDLE,
    ).first()
    if not cfg and not row:
        return OktaConfigOut(configured=False)
    cfg = cfg or {}
    tok = cfg.get("token") or ""
    return OktaConfigOut(
        configured=True,
        domain=cfg.get("domain"),
        token_prefix=(tok[:4] + "…") if tok else None,
        last_synced_at=_parse_iso(cfg.get("last_synced_at")),
        last_import=cfg.get("last_import"),
        last_update=cfg.get("last_update"),
        last_error=cfg.get("last_error"),
        issuer=(row.okta_issuer if row else None),
        audience=(row.okta_audience if row else None),
        jwt_auth_enabled=bool(row.okta_auth_enabled) if row else False,
    )


@router.put("/config", response_model=OktaConfigOut)
def put_okta_config(
    workspace_id: str,
    body: OktaConfigPut,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
) -> OktaConfigOut:
    # Empty-body guard — reject requests that would be a no-op.
    if body.domain is None and body.token is None and body.issuer is None and body.audience is None and body.jwt_auth_enabled is None:
        raise HTTPException(status_code=422, detail="At least one field required")

    existing = _load_config(db, workspace_id) or {}

    # Credential update — both domain and token must be provided together
    if body.domain is not None or body.token is not None:
        if not body.domain or not body.token:
            raise HTTPException(status_code=422, detail="Domain and token must be provided together")
        domain = _sanitize_domain(body.domain)
        if not domain:
            raise HTTPException(status_code=422, detail="Okta domain required")
        existing.update({"domain": domain, "token": body.token})
        _save_config(db, workspace_id, existing)

    # #1056 — update JWT auth columns on the Integration row.
    row = db.query(Integration).filter(
        Integration.workspace_id == uuid.UUID(workspace_id),
        Integration.handle == _OKTA_HANDLE,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Okta integration not configured — save credentials first")
    if body.issuer is not None:
        row.okta_issuer = body.issuer.strip() or None
    if body.audience is not None:
        row.okta_audience = body.audience.strip() or None
    if body.jwt_auth_enabled is not None:
        row.okta_auth_enabled = bool(body.jwt_auth_enabled)
    db.commit()

    tok = existing.get("token") or ""
    return OktaConfigOut(
        configured=True,
        domain=existing.get("domain"),
        token_prefix=(tok[:4] + "…") if tok else None,
        last_synced_at=_parse_iso(existing.get("last_synced_at")),
        last_import=existing.get("last_import"),
        last_update=existing.get("last_update"),
        last_error=existing.get("last_error"),
        issuer=row.okta_issuer,
        audience=row.okta_audience,
        jwt_auth_enabled=bool(row.okta_auth_enabled),
    )


@router.delete("/config", status_code=204)
def delete_okta_config(
    workspace_id: str,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
):
    row = db.query(Integration).filter(
        Integration.workspace_id == uuid.UUID(workspace_id),
        Integration.handle == _OKTA_HANDLE,
    ).first()
    if row:
        db.delete(row)
        db.commit()


# ─── Sync endpoint ──────────────────────────────────────────────────────────

@router.post("/sync", response_model=OktaSyncResponse)
def sync_okta(
    workspace_id: str,
    body: OktaSyncRequest,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
) -> OktaSyncResponse:
    """Pull Okta apps into agent_identities. Idempotent — reruns update in place.
    domain and token may be omitted; falls back to stored config from PUT /config."""
    stored = _load_config(db, workspace_id) or {}
    domain = _sanitize_domain(body.domain or stored.get("domain") or "")
    token = body.token or stored.get("token") or ""
    if not domain:
        raise HTTPException(status_code=422, detail="Okta domain required (in request body or via /config)")
    if not token:
        raise HTTPException(status_code=422, detail="Okta API token required (in request body or via /config)")
    # rebind body.token so the loop below (which uses body.token for owner enrichment) works either way
    body.token = token

    imported = 0
    updated = 0
    skipped = 0
    errors: list[str] = []
    ws_uuid = uuid.UUID(workspace_id)

    placeholder_encrypted = encrypt({"token": _PLACEHOLDER})

    url = f"https://{domain}/api/v1/apps?limit={body.limit}"
    while url:
        req = urllib.request.Request(url, headers={
            "Authorization": f"SSWS {body.token}",
            "Accept": "application/json",
            "User-Agent": "Conduct-Guard-OktaSync/1.0",
        })
        try:
            # httpx rejects non-http(s) schemes (closes bandit B310).
            import httpx
            hx_resp = httpx.request(
                method=req.get_method(),
                url=req.full_url,
                headers=dict(req.headers),
                content=req.data if req.data else None,
                timeout=30,
            )
            hx_resp.raise_for_status()
            raw = hx_resp.text
            link_header = hx_resp.headers.get("Link", "")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"Okta API returned {e.response.status_code}: {e.response.reason_phrase}")
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Okta API request failed: {e}")
        except urllib.error.URLError as e:
            raise HTTPException(status_code=502, detail=f"Okta unreachable: {e.reason}")

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            errors.append("Okta returned non-JSON response")
            break

        if not isinstance(data, list):
            errors.append(f"Unexpected response shape from Okta: {type(data).__name__}")
            break

        for app in data:
            if not app.get("id"):
                skipped += 1
                continue
            try:
                row_data = _okta_app_to_row(app)
                # Best-effort owner enrichment. Never fails the sync.
                owner = _fetch_first_owner(domain, body.token, row_data["source_id"])
                existing = db.query(AgentIdentity).filter(
                    AgentIdentity.workspace_id == ws_uuid,
                    AgentIdentity.source == "okta",
                    AgentIdentity.source_id == row_data["source_id"],
                ).first()
                if existing:
                    for k, v in row_data.items():
                        if k == "created_at":
                            continue  # never mutate the original discovery timestamp
                        setattr(existing, k, v)
                    # Only overwrite owner_user_id if we found one AND the
                    # existing owner was unassigned or was itself Okta-derived.
                    if owner and not existing.owner_user_id:
                        existing.owner_user_id = owner
                    updated += 1
                else:
                    new_row = AgentIdentity(
                        id=str(uuid.uuid4()),
                        workspace_id=ws_uuid,
                        token_prefix=_PLACEHOLDER[:30],
                        token_encrypted=placeholder_encrypted,
                        token_type="external",
                        owner_user_id=owner,
                        **row_data,
                    )
                    db.add(new_row)
                    imported += 1
            except Exception as e:
                errors.append(f"{app.get('id')}: {type(e).__name__}: {e}")
                skipped += 1

        url = _extract_next_link(link_header)

    db.commit()

    # Record the sync outcome in the stored config so the UI can show
    # last-run stats. Only touches config if one already exists — an
    # ad-hoc sync with body-supplied creds should not create config.
    if stored:
        stored["last_synced_at"] = datetime.now(timezone.utc).isoformat()
        stored["last_import"] = imported
        stored["last_update"] = updated
        stored["last_error"] = "; ".join(errors[:3]) if errors else None
        _save_config(db, workspace_id, stored)

    return OktaSyncResponse(imported=imported, updated=updated, skipped=skipped, errors=errors)


if __name__ == "__main__":
    # Self-check: pure mapping, no network.
    sample = {
        "id": "0oa1677gbczxbjmcI698",
        "orn": "orn:okta:idp:00o:apps:oidc_client:0oa1677gbczxbjmcI698",
        "name": "oidc_client",
        "label": "Sample External Agent",
        "status": "ACTIVE",
        "created": "2026-08-10T01:19:40.000Z",
        "lastUpdated": "2026-08-10T01:19:40.000Z",
        "signOnMode": "OPENID_CONNECT",
        "features": [],
        "settings": {"app": {}},
    }
    r = _okta_app_to_row(sample)
    assert r["source_id"] == "0oa1677gbczxbjmcI698"
    assert r["name"] == "Sample External Agent"
    assert r["source"] == "okta"
    assert r["lifecycle_state"] == "active"
    assert r["platform_of_origin"] == "oidc_client"
    assert r["metadata_json"]["sign_on_mode"] == "OPENID_CONNECT"
    assert r["deactivated_at"] is None

    inactive = {**sample, "status": "INACTIVE"}
    r2 = _okta_app_to_row(inactive)
    assert r2["lifecycle_state"] == "deactivated"
    assert r2["deactivated_at"] is not None

    ai_app = {**sample, "settings": {"app": {"agent_platform": "Gemini Enterprise"}}}
    r3 = _okta_app_to_row(ai_app)
    assert r3["platform_of_origin"] == "gemini enterprise"

    link = '<https://x.okta.com/api/v1/apps?after=abc&limit=100>; rel="next", <https://x.okta.com/api/v1/apps>; rel="self"'
    assert _extract_next_link(link) == "https://x.okta.com/api/v1/apps?after=abc&limit=100"
    assert _extract_next_link("") is None

    assert _sanitize_domain("https://foo.okta.com/") == "foo.okta.com"
    assert _sanitize_domain("http://foo.okta.com") == "foo.okta.com"
    assert _sanitize_domain("foo.okta.com") == "foo.okta.com"

    print("okta sync self-check: OK")
