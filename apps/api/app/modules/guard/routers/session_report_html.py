"""Styled HTML rendering for GET /guard/session-reports/{id}/html."""

from datetime import datetime

from app.modules.guard.models import SessionReport


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
            f"{archetype}</span>"
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
            f"border-radius:var(--r-card);padding:20px 24px;font-family:ui-monospace,monospace;"
            f'font-size:12.5px;color:var(--text-2);white-space:pre-wrap;line-height:1.7;overflow-x:auto;margin:0">'
            f"{report_md}</pre>"
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
