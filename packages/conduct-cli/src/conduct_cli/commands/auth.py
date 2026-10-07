"""Login flows, agent-token refresh/rotation, and `conduct sync`."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from conduct_cli import api
from conduct_cli import deployment
from conduct_cli.commands.shared import (
    BOLD,
    CONFIG_PATH,
    CYAN,
    GRAY,
    GREEN,
    RED,
    RESET,
    _atomic_write,
    _load_config,
)


_DEFAULT_API_URL = deployment.SAAS_API
_DEFAULT_WEB_URL = deployment.SAAS_WEB


def _find_free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _exchange_clerk_token(api_url: str, clerk_token: str, workspace_id: str) -> dict:
    """POST /oauth/token (RFC 8693 grant) to exchange a Clerk JWT for cond_agt_* + cond_ref_*.

    Endpoint moved from /token → /oauth/token in the OAuth 2.1 consolidation.
    /token remains as a backwards-compat alias for older CLI installs; delete
    the alias after ~60 days of zero traffic there.
    """
    _GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"
    _TYPE  = "urn:ietf:params:oauth:token-type:jwt"
    body = urllib.parse.urlencode({
        "grant_type":         _GRANT,
        "subject_token":      clerk_token,
        "subject_token_type": _TYPE,
        "resource":           workspace_id,
    }).encode()
    req = urllib.request.Request(
        f"{api_url}/oauth/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return {
            "agent_token":   data["access_token"],
            "refresh_token": data.get("refresh_token", ""),
            "workspace_id":  data.get("workspace_id", workspace_id),
        }
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        try:
            detail = json.loads(body_text).get("detail", body_text)
        except Exception:
            detail = body_text[:120]
        print(f"{RED}Login failed: {detail} — run `conduct login` to try again{RESET}")
        sys.exit(1)


def _web_login_flow(api_url: str, web_url: str) -> dict:
    """Open browser → localhost callback → return {agent_token, refresh_token, workspace_id}."""
    import http.server
    import secrets
    import threading
    import webbrowser

    state = secrets.token_urlsafe(16)
    port  = _find_free_port()
    result: dict = {}
    event = threading.Event()
    success_url = (
        "https://conductai.ai/cli-connected"
        if urllib.parse.urlparse(web_url).hostname in {"app.conductai.ai", "conductai.ai", "www.conductai.ai"}
        else web_url.rstrip("/") + "/cli-connected"
    )

    class _Handler(http.server.BaseHTTPRequestHandler):
        timeout = 10

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = dict(urllib.parse.parse_qsl(parsed.query))

            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return

            if not secrets.compare_digest(params.get("state", ""), state):
                self.send_response(400)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                return

            try:
                if not params.get("workspace_id"):
                    raise ValueError("Missing workspace")
                authenticated = params
                if params.get("clerk_token") and not params.get("agent_token"):
                    authenticated = _exchange_clerk_token(api_url, params["clerk_token"], params["workspace_id"])
                if not authenticated.get("agent_token"):
                    raise ValueError("Missing agent token")
                result.update(authenticated)
            except (Exception, SystemExit):
                result["login_failed"] = True

            try:
                self.send_response(400 if result.get("login_failed") else 303)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                if not result.get("login_failed"):
                    self.send_header("Location", success_url)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                if result.get("login_failed"):
                    self.wfile.write(b"Login failed. Return to your terminal and run conduct login again.")
            finally:
                event.set()

        def log_message(self, *_):
            pass  # silence server logs

    # Browsers may preconnect without sending a request. Keep those sockets
    # from blocking the callback or shutdown after a successful login.
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    auth_url = f"{web_url}/cli-auth?port={port}&state={state}&api={urllib.parse.quote(api_url, safe='')}"
    print(f"\n{BOLD}Opening browser for authentication…{RESET}")
    print(f"{GRAY}If the browser didn't open, visit:{RESET}")
    print(f"  {CYAN}{auth_url}{RESET}\n")
    try:
        webbrowser.open(auth_url)
        completed = event.wait(timeout=300)
    finally:
        server.shutdown()
        server.server_close()
    if not completed:
        print(f"{RED}Login timed out (5 min). Try again.{RESET}")
        sys.exit(1)

    if result.get("login_failed"):
        print(f"{RED}Login failed. Run `conduct login` to try again.{RESET}")
        sys.exit(1)

    if not result.get("workspace_id"):
        print(f"{RED}Login failed — missing workspace in callback. Try again.{RESET}")
        sys.exit(1)

    if not result.get("agent_token"):
        print(f"{RED}Login failed — token exchange failed. Try again.{RESET}")
        sys.exit(1)

    return result


def _token_login_flow(agent_token: str, api_url: str) -> dict:
    """Manual --token flow: validate token against API and return workspace info."""
    hdrs = {"Authorization": f"Bearer {agent_token}", "Content-Type": "application/json"}
    try:
        me = api.req("GET", f"{api_url}/me", hdrs)
        return {"agent_token": agent_token, "workspace_id": me.get("workspace_id", "")}
    except SystemExit:
        print(f"{RED}Token rejected by server. Check your token and try again.{RESET}")
        sys.exit(1)


def cmd_login(args):
    from conduct_cli.login_config import endpoints
    cfg = _load_config()
    try:
        api_url, web_url = endpoints(args, cfg, _DEFAULT_API_URL, _DEFAULT_WEB_URL)
    except ValueError as exc:
        print(f"{RED}{exc}{RESET}")
        raise SystemExit(1) from None
    # Workspace IDs and refresh credentials must not cross deployment boundaries.
    if api_url != deployment.api_url(cfg):
        cfg = {}
    for name in ("gateway_url", "mcp_url"):
        value = getattr(args, name, None)
        if value:
            cfg[name] = value
    try:
        deployment.resolve({**cfg, "api_url": api_url, "web_url": web_url})
    except ValueError as exc:
        print(f"{RED}{exc}{RESET}")
        raise SystemExit(1) from None

    # Capture the workspace the user was on BEFORE login — so we can restore
    # it after the login flow (which always returns the account's default).
    prior_ws = cfg.get("workspace_id") or cfg.get("workspace") or ""

    # Manual login: accept an agent token passed via the token argument (no browser)
    manual_token = getattr(args, "token", None)
    if manual_token:
        if not manual_token.startswith("cond_agt_"):
            print(f"{RED}Invalid token format. Expected cond_agt_... token from the dashboard.{RESET}")
            sys.exit(1)
        result = _token_login_flow(manual_token, api_url)
    else:
        result = _web_login_flow(api_url, web_url)

    # Clear old managed Copilot credentials even if the subsequent sync fails.
    from conduct_cli.guard_commands.copilot import clear_managed
    clear_managed()
    # Write config
    import datetime as _dt
    cfg["api_url"]          = api_url
    if web_url:
        cfg["web_url"] = web_url
    cfg["agent_token"]      = result["agent_token"]
    cfg["workspace"]        = result["workspace_id"]
    cfg["workspace_id"]     = result["workspace_id"]
    cfg["token_expires_at"] = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=8)).isoformat()
    if result.get("refresh_token"):
        cfg["refresh_token"] = result["refresh_token"]
    else:
        cfg.pop("refresh_token", None)
    # Clear legacy api_key — agent_token is the credential now
    cfg.pop("api_key", None)
    cfg.pop("token", None)
    cfg.pop("server", None)
    _atomic_write(CONFIG_PATH, cfg, merge=False)

    # Restore prior workspace if login returned a different default. Otherwise
    # every `conduct login` silently blows away the last `conduct switch`.
    if prior_ws and str(prior_ws) != str(result["workspace_id"]):
        try:
            _hdrs_restore = {"Authorization": f"Bearer {result['agent_token']}", "Content-Type": "application/json"}
            _r = api.req("POST", f"{api_url}/auth/switch-workspace", _hdrs_restore, {"workspace_id": prior_ws})
            if _r and _r.get("agent_token"):
                cfg["agent_token"] = _r["agent_token"]
                if _r.get("refresh_token"):
                    cfg["refresh_token"] = _r["refresh_token"]
                cfg["workspace"]    = prior_ws
                cfg["workspace_id"] = prior_ws
                cfg["token_expires_at"] = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=int(_r.get("expires_in", 28800)))).isoformat()
                _atomic_write(CONFIG_PATH, cfg)
                # Update `result` so subsequent code (name display, sync) targets prior workspace
                result["workspace_id"] = prior_ws
                result["agent_token"] = cfg["agent_token"]
        except SystemExit:
            pass  # not a member of prior workspace anymore, or endpoint missing — keep server default
        except Exception:
            pass

    # Fetch workspaces so we can display the current one by name and nudge
    # the user if their account has more than one (cross-surface switch drift).
    try:
        _hdrs = {"Authorization": f"Bearer {result['agent_token']}", "Content-Type": "application/json"}
        _workspaces = api.req("GET", f"{api_url}/projects", _hdrs) or []
    except Exception:
        _workspaces = []
    _current = next((w for w in _workspaces if str(w.get("id")) == str(result["workspace_id"])), None)
    _name = (_current or {}).get("name") or ""
    if _name:
        print(f"{GREEN}✓ Logged in{RESET} — workspace {BOLD}{_name}{RESET} {GRAY}({str(result['workspace_id'])[:8]}…){RESET}")
    else:
        print(f"{GREEN}✓ Logged in{RESET} — workspace {GRAY}{result['workspace_id']}{RESET}")

    # Auto-sync: register hooks + pull policy
    if not getattr(args, "no_sync", False):
        try:
            import conduct_cli.guard as _g
            import types
            _g.cmd_guard_sync(types.SimpleNamespace())
        except SystemExit:
            pass
        except Exception:
            pass

    # Nudge if the account has multiple workspaces — the web UI and CLI hold
    # workspace context independently, so users routinely forget which one
    # the CLI is now targeting.
    if len(_workspaces) > 1:
        _others = [w.get("name","") for w in _workspaces if str(w.get("id")) != str(result["workspace_id"])]
        _preview = ", ".join(o for o in _others[:3] if o)
        print(f"\n  {GRAY}You have {len(_workspaces)} workspaces. This CLI now targets:{RESET} {BOLD}{_name or result['workspace_id']}{RESET}")
        print(f"  {GRAY}Switch with:{RESET} {CYAN}conduct switch \"<name>\"{RESET}  {GRAY}(others: {_preview}){RESET}")


# ── conduct sync / test-guard ────────────────────────────────

def _refresh_agent_token(expected_config: dict | None = None) -> bool:
    """Rotate once across concurrent callers, without crossing login contexts."""
    from conduct_cli.credential_lock import credential_lock
    snapshot = dict(expected_config if expected_config is not None else _load_config())
    if not snapshot.get("refresh_token"):
        return False
    try:
        with credential_lock(CONFIG_PATH):
            current = _load_config()
            for key in ("api_url", "workspace_id", "clerk_user_id"):
                if current.get(key) != snapshot.get(key):
                    return False
            if current.get("agent_token") != snapshot.get("agent_token"):
                return bool(current.get("agent_token"))
            if current.get("refresh_token") != snapshot.get("refresh_token"):
                return False
            return _rotate_agent_token(current)
    except Exception:
        return False


def _rotate_agent_token(cfg: dict) -> bool:
    """Silently rotate agent_token using refresh_token. Returns True if refreshed."""
    cfg = dict(cfg)
    refresh_token = cfg.get("refresh_token", "")
    if not refresh_token:
        return False
    api_url = deployment.api_url(cfg)
    try:
        import json as _json
        req = urllib.request.Request(
            f"{api_url}/auth/refresh",
            data=_json.dumps({"refresh_token": refresh_token}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
        if not all(isinstance(data.get(k), str) and data[k] for k in ("agent_token", "refresh_token", "workspace_id")):
            return False
        if cfg.get("workspace_id") and data["workspace_id"] != cfg["workspace_id"]:
            return False
        current = _load_config()
        if any(current.get(k) != cfg.get(k) for k in ("api_url", "workspace_id", "clerk_user_id", "agent_token", "refresh_token")):
            return False
        expires_in = int(data.get("expires_in", 28800))
        if expires_in <= 0:
            return False
        import datetime as _dt
        cfg["agent_token"]      = data["agent_token"]
        cfg["refresh_token"]    = data["refresh_token"]
        cfg["workspace"]        = data["workspace_id"]
        cfg["workspace_id"]     = data["workspace_id"]
        cfg["token_expires_at"] = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=expires_in)).isoformat()
        _atomic_write(CONFIG_PATH, cfg)
        return True
    except Exception:
        return False


def cmd_sync(args):
    """Sync Guard policies (and Security Loop policies if installed)."""
    import conduct_cli.guard as _g
    # Proactive refresh if token expires within 5 min
    cfg = _load_config()
    if cfg.get("refresh_token"):
        import datetime as _dt
        exp = cfg.get("token_expires_at", "")
        try:
            if not exp or _dt.datetime.fromisoformat(exp) < _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(minutes=5):
                _refresh_agent_token()
        except ValueError:
            pass
    print(f"\n{BOLD}▶ conduct sync{RESET}\n")
    _g.cmd_guard_sync(args)
    print(f"\n{GREEN}Sync complete.{RESET}\n")
