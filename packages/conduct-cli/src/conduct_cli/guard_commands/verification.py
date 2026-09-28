"""Guard CLI: verification."""
from __future__ import annotations

from pathlib import Path
import sys

from . import shared as _guard_shared


def cmd_guard_debug_hook(args):
    """Run a hook module standalone with JSON piped from stdin and print the outcome.

    Usage:
        echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}' | \\
            conduct guard debug-hook pretooluse
    """
    import subprocess as _sp
    toolname = args.toolname  # pretooluse | posttooluse | stop | precompact | session-start

    module_map = {
        "pretooluse":   "conduct_cli.hooks.pretooluse",
        "posttooluse":  "conduct_cli.hooks.posttooluse",
        "stop":         "conduct_cli.hooks.stop",
        "precompact":   "conduct_cli.hooks.precompact",
        "session-start":"conduct_cli.hooks.session_start",
    }
    module = module_map[toolname]

    print(f"{_guard_shared.BOLD}conduct guard debug-hook {toolname}{_guard_shared.RESET}")
    print(f"{_guard_shared.GRAY}Reading JSON from stdin (send EOF when done — Ctrl+D)…{_guard_shared.RESET}\n")

    stdin_data = sys.stdin.read()
    if not stdin_data.strip():
        # Provide a neutral no-op payload so the hook doesn't crash
        stdin_data = "{}"

    result = _sp.run(
        [sys.executable, "-c", f"from {module} import main; main()"],
        input=stdin_data,
        capture_output=True,
        text=True,
    )

    if result.stdout:
        print(f"{_guard_shared.BOLD}stdout:{_guard_shared.RESET}")
        print(result.stdout)
    if result.stderr:
        print(f"{_guard_shared.BOLD}stderr:{_guard_shared.RESET}")
        print(result.stderr)

    exit_label = {0: f"{_guard_shared.GREEN}0 — allowed{_guard_shared.RESET}", 2: f"{_guard_shared.RED}2 — blocked{_guard_shared.RESET}"}.get(
        result.returncode, f"{_guard_shared.YELLOW}{result.returncode}{_guard_shared.RESET}"
    )
    print(f"\n{_guard_shared.BOLD}Exit code:{_guard_shared.RESET} {exit_label}")


_PRIV_KEYWORDS = ["privilege", "escalat", "role_abuse", "admin_access", "no-sudo", "nosudo", "runasroot"]


_OWASP_MAP: list[tuple[list[str], str, str]] = [
    (["prompt_inject", "injection", "jailbreak", "override_system", "indirect_prompt"],
     "A01", "Prompt Injection"),
    (["secret", "credential", "token_leak", "api_key_leak", "password", "sensitive_data", "pii", "exfil"],
     "A02", "Sensitive Information Disclosure"),
    (["supply_chain", "dependency", "package", "malicious_package", "unsigned"],
     "A03", "Supply Chain Vulnerabilities"),
    (["excessive_agency", "no-rm-rf", "norms", "rmrf", "scope", "overreach", "unauthorized_action", "out_of_scope", "shell_destruct"],
     "A04", "Excessive Agency"),
    (["model_theft", "model_extract", "weights"],
     "A05", "Model Theft"),
    (["communication", "callback", "exfiltrate_output", "covert_channel"],
     "A06", "Agentic Communication Vulnerabilities"),
    (["unmonitored", "no_audit", "policy_eval_error", "policy_signature_invalid"],
     "A07", "Insufficient Monitoring and Logging"),
    (["hallucin", "unverified", "over_reliance", "fabricat"],
     "A08", "Over-reliance on Model Outputs"),
    (_PRIV_KEYWORDS,
     "A09", "Privilege Escalation"),
    (["budget", "rate_limit", "dos", "denial", "hard_cap", "spend"],
     "A10", "Model Denial of Service"),
]


_OWASP_UNKNOWN = ("A??", "Uncategorised")


def _map_owasp(rule_id: str) -> tuple[str, str]:
    key = (rule_id or "").lower()
    for keywords, code, title in _OWASP_MAP:
        if any(k in key for k in keywords):
            return code, title
    return _OWASP_UNKNOWN


_GRADE_COLORS = {"A": "\033[32m", "B": "\033[32m", "C": "\033[33m", "D": "\033[33m", "F": "\033[31m"}


_GRADE_ORDER  = ["A", "B", "C", "D", "F"]


def _grade_below(actual: str, minimum: str) -> bool:
    return _GRADE_ORDER.index(actual) > _GRADE_ORDER.index(minimum.upper())


_VERDICT_COLOR = {"held": _guard_shared.GREEN, "bypassed": _guard_shared.RED, "not_tested": _guard_shared.YELLOW}


def cmd_verify(args) -> None:
    """conduct verify — governance grade + OWASP Agentic Top 10 coverage."""
    import json as _json

    evidence_out = getattr(args, "evidence", None)
    badge        = getattr(args, "badge", False)
    min_grade    = getattr(args, "min_grade", None)
    strict       = getattr(args, "strict", False)
    fmt          = getattr(args, "format", "text")
    run_battery  = getattr(args, "run", False)

    cfg          = _guard_shared._require_guard_config()
    workspace_id = cfg.get("workspace_id")
    agent_token  = cfg.get("agent_token", "")
    base_url     = _guard_shared._api_url(cfg)

    # ── fetch evidence from API ───────────────────────────────────────────────
    ev = _guard_shared._req(
        "GET",
        f"{base_url}/guard/verify/evidence?workspace_id={workspace_id}",
        token=agent_token or None,
    )

    grade        = ev.get("grade", "F")
    coverage_pct = ev.get("coverage_pct", 0)
    score        = ev.get("score", 0)
    blocked_24h  = ev.get("blocked_24h", 0)
    controls     = ev.get("controls", [])
    generated_at = ev.get("generated_at", "")

    # ── --run (live adversarial battery) ─────────────────────────────────────
    run_result = None
    if run_battery:
        print(f"\n{_guard_shared.BOLD}Running adversarial test battery…{_guard_shared.RESET}")
        run_result = _guard_shared._req(
            "POST",
            f"{base_url}/guard/verify/run?workspace_id={workspace_id}",
            token=agent_token or None,
        )
        if fmt == "json":
            print(_json.dumps(run_result, indent=2))
            return
        rs      = run_result.get("score", 0)
        rg      = run_result.get("grade", "F")
        passed  = run_result.get("passed_tests", 0)
        total   = run_result.get("total_tests", 0)
        results = run_result.get("results", [])
        rg_col  = _GRADE_COLORS.get(rg, _guard_shared.GRAY)
        print()
        print(f"{_guard_shared.BOLD}conduct verify --run — Live Adversarial Score{_guard_shared.RESET}")
        print("─" * 60)
        print(f"\n  Live Grade: {rg_col}{_guard_shared.BOLD}{rg}{_guard_shared.RESET}  ({rs}/100) · {passed}/{total} held\n")
        print(f"  {_guard_shared.BOLD}{'ASI':<8} {'Verdict':<12} {'Expected':<10} {'Actual':<10} Test{_guard_shared.RESET}")
        print("  " + "─" * 56)
        for r in results:
            vc = _VERDICT_COLOR.get(r.get("verdict", ""), _guard_shared.GRAY)
            print(
                f"  {r.get('asi',''):<8} "
                f"{vc}{r.get('verdict',''):<12}{_guard_shared.RESET} "
                f"{r.get('expected',''):<10} "
                f"{r.get('actual',''):<10} "
                f"{r.get('name','')}"
            )
        print()
        if min_grade and _grade_below(rg, min_grade):
            print(f"  {_guard_shared.RED}✗ Live grade {rg} is below minimum {min_grade.upper()}.{_guard_shared.RESET}\n")
            sys.exit(1)
        print(f"  {_guard_shared.GREEN}✓ PASS{_guard_shared.RESET}\n")
        return

    # ── --badge ───────────────────────────────────────────────────────────────
    if badge:
        color = {"A": "brightgreen", "B": "green", "C": "yellow", "D": "orange", "F": "red"}.get(grade, "lightgrey")
        print(f"![Conduct Guard](https://img.shields.io/badge/Guard-Grade_{grade}-{color})")
        return

    # ── --evidence (write artifact) ───────────────────────────────────────────
    if evidence_out:
        artifact = {
            "grade":        grade,
            "coverage_pct": coverage_pct,
            "score":        score,
            "blocked_24h":  blocked_24h,
            "controls":     controls,
            "generated_at": generated_at,
            "workspace_id": workspace_id,
        }
        Path(evidence_out).write_text(_json.dumps(artifact, indent=2))
        print(f"{_guard_shared.GREEN}✓ Evidence artifact written to {evidence_out}{_guard_shared.RESET}")

    # ── output ────────────────────────────────────────────────────────────────
    if fmt == "json":
        print(_json.dumps(ev, indent=2))
    else:
        grade_color = _GRADE_COLORS.get(grade, _guard_shared.GRAY)
        print()
        print(f"{_guard_shared.BOLD}conduct verify — Governance Grade{_guard_shared.RESET}")
        print("─" * 60)
        print(f"\n  Grade:    {grade_color}{_guard_shared.BOLD}{grade}{_guard_shared.RESET}  (score {score}/100)")
        print(f"  Coverage: {coverage_pct}% of OWASP ASI controls active")
        print(f"  Blocked (24h): {blocked_24h}")
        print()
        print(f"{_guard_shared.BOLD}  {'Control':<8} {'Status':<10} Name{_guard_shared.RESET}")
        print("  " + "─" * 56)
        for c in controls:
            status = c.get("status", "missing")
            if status == "active":
                sc = f"{_guard_shared.GREEN}active   {_guard_shared.RESET}"
            elif status == "partial":
                sc = f"{_guard_shared.YELLOW}partial  {_guard_shared.RESET}"
            else:
                sc = f"{_guard_shared.RED}missing  {_guard_shared.RESET}"
            print(f"  {c.get('id',''):<8} {sc} {c.get('name','')}")
        print()

        # CI checks
        failed = False
        if strict and blocked_24h > 0:
            print(f"  {_guard_shared.RED}✗ Strict mode: {blocked_24h} blocked event(s) in last 24h.{_guard_shared.RESET}")
            failed = True
        if min_grade and _grade_below(grade, min_grade):
            print(f"  {_guard_shared.RED}✗ Grade {grade} is below minimum {min_grade.upper()}.{_guard_shared.RESET}")
            failed = True
        if not failed:
            print(f"  {_guard_shared.GREEN}✓ PASS{_guard_shared.RESET}")
        print()

    # ── exit codes ────────────────────────────────────────────────────────────
    if (strict and blocked_24h > 0) or (min_grade and _grade_below(grade, min_grade)):
        sys.exit(1)


def cmd_guard_simulate(args):
    """conduct guard simulate --as-okta-agent <jwt-or-file>

    Runs an *authenticated* GET /auth/whoami against the configured API,
    using the supplied JWT as the Bearer token. Prints what auth resolved
    to — identity name, source, source_id, lifecycle_state — so an
    operator can verify their Okta setup end-to-end before wiring a real
    agent. Purely a read-only probe; nothing is executed on the server.

    Explicitly labelled a *simulation* — do not use this as a production
    auth path.
    """
    import json as _json
    import urllib.error as _uerr
    import urllib.request as _ureq
    from pathlib import Path as _Path

    raw = getattr(args, "as_okta_agent", None)
    if not raw:
        print("Missing --as-okta-agent <jwt-or-file>", file=sys.stderr)
        sys.exit(2)

    _p = _Path(raw)
    if _p.exists() and _p.is_file():
        jwt = _p.read_text().strip()
    else:
        jwt = raw.strip()

    if jwt.count(".") != 2:
        print("Value does not look like a JWT (expected three dot-separated segments).", file=sys.stderr)
        sys.exit(2)

    cfg = _guard_shared._require_guard_config()
    api = _guard_shared._api_url(cfg)
    ws = cfg.get("workspace_id") or cfg.get("workspace")
    if not ws:
        print("No workspace configured — run `conduct login` first.", file=sys.stderr)
        sys.exit(2)

    url = f"{api.rstrip('/')}/auth/whoami?workspace_id={ws}"
    req = _ureq.Request(url, headers={
        "Authorization": f"Bearer {jwt}",
        "Accept": "application/json",
        "User-Agent": "Conduct-Guard-Simulate/1.0",
    })
    print(f"[simulation] GET {url}")
    try:
        with _ureq.urlopen(req, timeout=15) as resp:
            body = _json.loads(resp.read().decode("utf-8"))
    except _uerr.HTTPError as e:
        try:
            detail = _json.loads(e.read().decode("utf-8"))
        except Exception:
            detail = {"detail": e.reason}
        print(f"[simulation] HTTP {e.code}: {detail.get('detail', detail)}")
        sys.exit(1)
    except _uerr.URLError as e:
        print(f"[simulation] connection failed: {e.reason}", file=sys.stderr)
        sys.exit(1)

    print(f"[simulation] workspace: {body.get('workspace_id')}")
    print(f"[simulation] token kind: {body.get('token_kind')}")
    ident = body.get("identity")
    if ident:
        print(f"[simulation] identity   : {ident.get('name')} ({ident.get('source')}:{ident.get('source_id')})")
        print(f"[simulation] lifecycle  : {ident.get('lifecycle_state')}")
    else:
        print("[simulation] identity   : (none — token did not resolve to an AgentIdentity)")


def cmd_guard_approvals(args, guard_p):
    """List and decide Guard HITL approval requests (#1140)."""
    sub = getattr(args, "approvals_command", None)
    if sub not in ("list", "approve", "reject"):
        guard_p.print_help()
        sys.exit(1)

    cfg          = _guard_shared._require_guard_config()
    workspace_id = cfg.get("workspace_id")
    agent_token  = cfg.get("agent_token", "")
    base_url     = _guard_shared._api_url(cfg)

    if sub == "list":
        url = f"{base_url}/guard/approvals?workspace_id={workspace_id}&status={args.status}&limit={args.limit}"
        resp = _guard_shared._req("GET", url, token=agent_token or None)
        items = resp.get("items", []) if isinstance(resp, dict) else []
        if not items:
            print(f"{_guard_shared.GRAY}No approvals with status={args.status}.{_guard_shared.RESET}")
            return
        id_w, req_w, rule_w, msg_w = 38, 26, 24, 40
        print()
        print(f"{_guard_shared.BOLD}{'ID':<{id_w}} {'Requester':<{req_w}} {'Rule':<{rule_w}} {'Message':<{msg_w}} Status{_guard_shared.RESET}")
        print("─" * (id_w + req_w + rule_w + msg_w + 12))
        colors = {"pending": _guard_shared.YELLOW, "approved": _guard_shared.GREEN, "rejected": _guard_shared.RED, "timed_out": _guard_shared.GRAY}
        for it in items:
            st = it.get("status", "?")
            print(
                f"{it.get('id',''):<{id_w}} "
                f"{(it.get('requester_email') or '—')[:req_w-1]:<{req_w}} "
                f"{(it.get('rule_id') or '—')[:rule_w-1]:<{rule_w}} "
                f"{(it.get('rule_message') or '—')[:msg_w-1]:<{msg_w}} "
                f"{colors.get(st, '')}{st}{_guard_shared.RESET}"
            )
        return

    # approve / reject share a body shape
    decision = "approved" if sub == "approve" else "rejected"
    body = {"decision": decision}
    if args.reason:
        body["reason"] = args.reason
    url = f"{base_url}/guard/approvals/{args.request_id}/decide?workspace_id={workspace_id}"
    resp = _guard_shared._req("POST", url, body=body, token=agent_token or None)
    req = resp.get("request") if isinstance(resp, dict) else None
    if not req:
        print(f"{_guard_shared.RED}Decision failed — no response body.{_guard_shared.RESET}")
        sys.exit(1)
    color = _guard_shared.GREEN if decision == "approved" else _guard_shared.RED
    print(f"{color}{decision.upper()}{_guard_shared.RESET} — {req.get('rule_id','')}  "
          f"by {req.get('decided_by_email','?')}  "
          f"latency={req.get('latency_ms','?')}ms  "
          f"run_resumed={resp.get('run_resumed')}")
