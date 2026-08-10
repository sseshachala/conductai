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
from app.core.crypto import encrypt
from app.core.database import get_db
from app.modules.agent_identity.models import AgentIdentity


router = APIRouter(prefix="/workspaces/{workspace_id}/integrations/okta", tags=["okta-sync"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class OktaSyncRequest(BaseModel):
    domain: str = Field(..., description="Okta domain like dev-XXXXXX.okta.com. No scheme, no trailing slash — the endpoint sanitizes both.")
    token: str = Field(..., description="Okta API token (SSWS). Never returned in the response.")
    limit: int = Field(100, ge=1, le=200, description="Page size for Okta /api/v1/apps.")


class OktaSyncResponse(BaseModel):
    imported: int
    updated: int
    skipped: int
    errors: list[str]


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


# ─── Endpoint ───────────────────────────────────────────────────────────────

@router.post("/sync", response_model=OktaSyncResponse)
def sync_okta(
    workspace_id: str,
    body: OktaSyncRequest,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
) -> OktaSyncResponse:
    """Pull Okta apps into agent_identities. Idempotent — reruns update in place."""
    domain = _sanitize_domain(body.domain)
    if not domain:
        raise HTTPException(status_code=422, detail="Okta domain required")

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
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                link_header = resp.headers.get("Link", "")
        except urllib.error.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Okta API returned {e.code}: {e.reason}")
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
                    updated += 1
                else:
                    new_row = AgentIdentity(
                        id=str(uuid.uuid4()),
                        workspace_id=ws_uuid,
                        token_prefix=_PLACEHOLDER[:30],
                        token_encrypted=placeholder_encrypted,
                        token_type="external",
                        **row_data,
                    )
                    db.add(new_row)
                    imported += 1
            except Exception as e:
                errors.append(f"{app.get('id')}: {type(e).__name__}: {e}")
                skipped += 1

        url = _extract_next_link(link_header)

    db.commit()
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
