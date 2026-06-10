"""
POST /guard/session-reports  — CLI pushes a developer session report (member token auth)
GET  /guard/session-reports  — admin/security lists all reports for a workspace
GET  /guard/session-reports/{id}/html — styled HTML report (API key or Clerk JWT via ?token=)
"""
import hashlib
import uuid
from datetime import datetime, timezone, date as _date
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import _verify_clerk_token, get_guard_hook_auth, require_permission
from app.core.database import get_db
from app.models.conduct_api_key import ConductApiKey
from app.modules.guard.models import SessionReport

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/guard/session-reports", tags=["guard"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class SessionReportIn(BaseModel):
    developer_email: str
    archetype: Optional[str] = None
    autonomy_score: Optional[float] = None
    planning_ratio: Optional[float] = None
    sessions: int = 0
    prompts: int = 0
    commits: int = 0
    lines_per_hour: Optional[float] = None
    active_days: Optional[int] = None
    tools_json: Optional[dict] = None
    report_md: Optional[str] = None


class SessionReportOut(BaseModel):
    id: str
    workspace_id: str
    developer_email: str
    archetype: Optional[str]
    autonomy_score: Optional[float]
    planning_ratio: Optional[float]
    sessions: int
    prompts: int
    commits: int
    lines_per_hour: Optional[float]
    active_days: Optional[int]
    tools_json: Optional[dict]
    report_md: Optional[str]
    created_at: str


# ── Helpers ───────────────────────────────────────────────────────────────────


def _report_to_out(r: SessionReport) -> SessionReportOut:
    return SessionReportOut(
        id=str(r.id),
        workspace_id=str(r.workspace_id),
        developer_email=r.developer_email,
        archetype=r.archetype,
        autonomy_score=r.autonomy_score,
        planning_ratio=r.planning_ratio,
        sessions=r.sessions,
        prompts=r.prompts,
        commits=r.commits,
        lines_per_hour=r.lines_per_hour,
        active_days=r.active_days,
        tools_json=r.tools_json,
        report_md=r.report_md,
        created_at=r.created_at.isoformat(),
    )


# ── GET /guard/session-reports ────────────────────────────────────────────────


@router.get("", response_model=list[SessionReportOut])
def list_session_reports(
    workspace_id: UUID = Query(..., description="Workspace UUID"),
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("guard.activity.view_all")),
):
    """List session reports for a workspace, newest first, up to 200 rows.

    Requires guard.activity.view_all (admin or security role).
    """
    rows = (
        db.query(SessionReport)
        .filter(SessionReport.workspace_id == workspace_id)
        .order_by(SessionReport.created_at.desc())
        .limit(200)
        .all()
    )
    return [_report_to_out(r) for r in rows]


# ── GET /guard/session-reports/{id} ───────────────────────────────────────────

@router.get("/{report_id}", response_model=SessionReportOut)
def get_session_report(
    report_id: UUID,
    workspace_id: UUID = Query(..., description="Workspace UUID"),
    _: str = Depends(require_permission("guard.activity.view_all")),
    db: Session = Depends(get_db),
) -> SessionReportOut:
    r = (
        db.query(SessionReport)
        .filter(SessionReport.id == report_id, SessionReport.workspace_id == workspace_id)
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
    return _report_to_out(r)


# ── POST /guard/session-reports ───────────────────────────────────────────────


@router.post("", response_model=SessionReportOut, status_code=201)
def create_session_report(
    body: SessionReportIn,
    db: Session = Depends(get_db),
    auth_workspace_id: str = Depends(get_guard_hook_auth),
):
    """Push a new session report from the CLI.

    Auth accepts a member token, Clerk JWT, or cond_live_ API key —
    the same trust model as POST /guard/events. The workspace_id is
    derived from the token, not the request body.
    """
    try:
        ws_uuid = uuid.UUID(auth_workspace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id from token")

    today = _date.today()
    report = (
        db.query(SessionReport)
        .filter(
            SessionReport.workspace_id == ws_uuid,
            SessionReport.developer_email == body.developer_email,
            SessionReport.created_at >= datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc),
        )
        .first()
    )
    created = report is None
    if report is None:
        report = SessionReport(workspace_id=ws_uuid, developer_email=body.developer_email)
        db.add(report)

    report.archetype = body.archetype
    report.autonomy_score = body.autonomy_score
    report.planning_ratio = body.planning_ratio
    report.sessions = body.sessions
    report.prompts = body.prompts
    report.commits = body.commits
    report.lines_per_hour = body.lines_per_hour
    report.active_days = body.active_days
    report.tools_json = body.tools_json
    report.report_md = body.report_md
    db.commit()

    log.info(
        "session_report.upserted",
        report_id=str(report.id),
        workspace_id=auth_workspace_id,
        developer_email=body.developer_email,
        created=created,
    )

    return _report_to_out(report)


# ── GET /guard/session-reports/{report_id}/html ───────────────────────────────

_HTML_401 = HTMLResponse(
    "<html><body style='font-family:sans-serif;padding:40px'>"
    "<h2>401 — Authentication required</h2>"
    "<p>Pass <code>?token=your-api-key</code> or a Clerk JWT.</p>"
    "</body></html>",
    status_code=401,
)

_HTML_401_INVALID = HTMLResponse(
    "<html><body style='font-family:sans-serif;padding:40px'>"
    "<h2>401 — Invalid credentials</h2>"
    "</body></html>",
    status_code=401,
)

_HTML_404 = HTMLResponse(
    "<html><body style='font-family:sans-serif;padding:40px'>"
    "<h2>404 — Report not found</h2>"
    "</body></html>",
    status_code=404,
)


def _format_report_date(dt: datetime) -> str:
    """Format a datetime as 'Jun 10, 2026'."""
    return dt.strftime("%b %-d, %Y")


def _autonomy_color(score: float) -> str:
    if score >= 70:
        return "var(--ok)"
    if score >= 50:
        return "var(--warn)"
    return "var(--err)"


def _build_html(report: SessionReport) -> str:
    email = report.developer_email or ""
    archetype = report.archetype or ""
    autonomy = report.autonomy_score
    sessions = report.sessions or 0
    commits = report.commits or 0
    lph = report.lines_per_hour
    lph_str = str(round(lph)) if lph is not None else "—"
    report_date = _format_report_date(report.created_at) if report.created_at else ""
    report_md = report.report_md or ""

    # Autonomy score display
    if autonomy is not None:
        auto_color = _autonomy_color(autonomy)
        auto_display = f'<span style="font-size:32px;font-weight:800;color:{auto_color};line-height:1">{autonomy:.1f}</span>'
    else:
        auto_display = '<span style="font-size:32px;font-weight:800;color:var(--text-muted);line-height:1">—</span>'

    # Archetype badge
    archetype_badge = ""
    if archetype:
        archetype_badge = (
            f'<span style="background:var(--accent-weak);color:var(--accent-text);'
            f'border-radius:6px;padding:3px 10px;font-size:12px;font-weight:500">'
            f'{archetype}</span>'
        )

    # Tools table
    tools_html = ""
    tools_json = report.tools_json
    if tools_json and isinstance(tools_json, dict) and tools_json:
        sorted_tools = sorted(tools_json.items(), key=lambda x: x[1], reverse=True)
        max_calls = max(v for _, v in sorted_tools) or 1
        rows_html = ""
        for tool_name, calls in sorted_tools:
            bar_width = round((calls / max_calls) * 200)
            rows_html += (
                f"<tr>"
                f'<td style="padding:8px 12px;border-bottom:1px solid var(--border);font-size:13px;color:var(--text)">{tool_name}</td>'
                f'<td style="padding:8px 12px;border-bottom:1px solid var(--border);font-size:13px;color:var(--text-2)">{calls}</td>'
                f'<td style="padding:8px 12px;border-bottom:1px solid var(--border)">'
                f'<div style="width:{bar_width}px;max-width:200px;height:6px;background:var(--accent-weak);border-radius:3px"></div>'
                f"</td>"
                f"</tr>"
            )
        tools_html = f"""
        <div style="margin-bottom:28px">
          <div class="eyebrow">TOP TOOLS</div>
          <table style="width:100%;border-collapse:collapse;margin-top:10px">
            <thead>
              <tr>
                <th style="background:var(--surface-3);font-size:11px;text-transform:uppercase;letter-spacing:.08em;padding:8px 12px;text-align:left;color:var(--text-muted);font-weight:600">Tool</th>
                <th style="background:var(--surface-3);font-size:11px;text-transform:uppercase;letter-spacing:.08em;padding:8px 12px;text-align:left;color:var(--text-muted);font-weight:600">Calls</th>
                <th style="background:var(--surface-3);font-size:11px;text-transform:uppercase;letter-spacing:.08em;padding:8px 12px;text-align:left;color:var(--text-muted);font-weight:600">Usage</th>
              </tr>
            </thead>
            <tbody>
              {rows_html}
            </tbody>
          </table>
        </div>
        """

    # Report markdown section
    if report_md:
        md_section = (
            f'<pre style="background:var(--surface-2);border:1px solid var(--border);'
            f'border-radius:var(--r-card);padding:20px 24px;font-family:ui-monospace,monospace;'
            f'font-size:12.5px;color:var(--text-2);white-space:pre-wrap;line-height:1.7;overflow-x:auto;margin:0">'
            f'{report_md}</pre>'
        )
    else:
        md_section = '<p style="color:var(--text-muted);font-size:13px;margin:0">No report text available.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Session Report — {email}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #faf9f7;
      --surface: #ffffff;
      --surface-2: #faf9f7;
      --surface-3: #f5f3f0;
      --border: #e7e5e4;
      --border-2: #d6d3d1;
      --text: #1c1917;
      --text-2: #57534e;
      --text-3: #78716c;
      --text-muted: #a8a29e;
      --accent: #4f46e5;
      --accent-weak: #eef2ff;
      --accent-text: #4338ca;
      --ok: #059669;
      --ok-bg: #ecfdf5;
      --warn: #d97706;
      --warn-bg: #fffbeb;
      --err: #dc2626;
      --err-bg: #fef2f2;
      --info: #2563eb;
      --info-bg: #eff6ff;
      --shadow: 0 1px 3px rgba(28,25,23,.07), 0 1px 2px rgba(28,25,23,.04);
      --shadow-md: 0 4px 14px rgba(28,25,23,.08);
      --r-card: 14px;
    }}
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: 'Inter', ui-sans-serif, system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      -webkit-font-smoothing: antialiased;
    }}
    .header {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 20px 32px 18px;
    }}
    .back-link {{
      display: inline-block;
      font-size: 13px;
      color: var(--text-3);
      text-decoration: none;
      margin-bottom: 12px;
      transition: color .15s;
    }}
    .back-link:hover {{ color: var(--accent); }}
    .page-title {{
      font-size: 20px;
      font-weight: 700;
      color: var(--text);
      margin: 0 0 6px;
      letter-spacing: -.02em;
    }}
    .subtitle {{
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 13px;
      color: var(--text-3);
    }}
    .content {{
      max-width: 960px;
      margin: 0 auto;
      padding: 32px 24px 64px;
    }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 32px;
    }}
    .kpi-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--r-card);
      padding: 20px 22px;
      box-shadow: var(--shadow);
    }}
    .eyebrow {{
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: .1em;
      color: var(--text-muted);
      margin-bottom: 8px;
    }}
    .kpi-value {{
      font-size: 32px;
      font-weight: 800;
      color: var(--text);
      line-height: 1;
    }}
    .section-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--r-card);
      padding: 24px;
      box-shadow: var(--shadow);
      margin-bottom: 24px;
    }}
    .section-label {{
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: .1em;
      color: var(--text-muted);
      margin-bottom: 14px;
    }}
    footer {{
      text-align: center;
      font-size: 11.5px;
      color: var(--text-muted);
      padding: 16px 0 32px;
    }}
    @media (max-width: 640px) {{
      .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
    }}
  </style>
</head>
<body>
  <div class="header">
    <a class="back-link" href="../">← Guard</a>
    <h1 class="page-title">{email}</h1>
    <div class="subtitle">
      {archetype_badge}
      <span>{report_date}</span>
    </div>
  </div>

  <div class="content">
    <!-- KPI Grid -->
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="eyebrow">Autonomy Score</div>
        {auto_display}
      </div>
      <div class="kpi-card">
        <div class="eyebrow">Sessions</div>
        <div class="kpi-value">{sessions}</div>
      </div>
      <div class="kpi-card">
        <div class="eyebrow">Commits</div>
        <div class="kpi-value">{commits}</div>
      </div>
      <div class="kpi-card">
        <div class="eyebrow">Lines / hr</div>
        <div class="kpi-value">{lph_str}</div>
      </div>
    </div>

    {tools_html}

    <!-- Full report -->
    <div class="section-card">
      <div class="section-label">Full Report</div>
      {md_section}
    </div>
  </div>

  <footer>Generated by Conduct Guard &middot; conduct session-report</footer>
</body>
</html>"""


@router.get("/{report_id}/html", response_class=HTMLResponse)
async def get_session_report_html(
    report_id: str,
    token: str | None = Query(None),
    workspace_id: str | None = Query(None),
    x_api_key: str | None = Header(None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Return a styled HTML view of a session report.

    Auth: accepts ?token= or X-Api-Key header with either a cond_live_ API key
    or a Clerk JWT. Workspace isolation is enforced — the report must belong to
    the authenticated workspace.
    """
    api_key_val = token or x_api_key
    if not api_key_val:
        return _HTML_401

    # Resolve workspace_id from the credential
    ws_id: str | None = None

    if api_key_val.startswith("cond_live_"):
        # cond_live_ API key path
        key_hash = hashlib.sha256(api_key_val.encode()).hexdigest()
        key_row = db.query(ConductApiKey).filter(ConductApiKey.key_hash == key_hash).first()
        if not key_row:
            return _HTML_401_INVALID
        ws_id = str(key_row.workspace_id)
    else:
        # Clerk JWT path — verify token, then require workspace_id query param
        claims = _verify_clerk_token(api_key_val)
        if not claims:
            return _HTML_401_INVALID
        # Clerk org_id is not a UUID — workspace_id must be passed explicitly
        if not workspace_id:
            return HTMLResponse("<html><body><h1>400</h1><p>Pass ?workspace_id= alongside ?token= for Clerk auth.</p></body></html>", status_code=400)
        ws_id = workspace_id

    # Fetch the report, enforcing workspace isolation
    try:
        report_uuid = uuid.UUID(report_id)
    except ValueError:
        return _HTML_404

    try:
        ws_uuid = uuid.UUID(ws_id)
    except ValueError:
        return _HTML_401_INVALID

    report = (
        db.query(SessionReport)
        .filter(
            SessionReport.id == report_uuid,
            SessionReport.workspace_id == ws_uuid,
        )
        .first()
    )
    if not report:
        return _HTML_404

    return HTMLResponse(_build_html(report))
