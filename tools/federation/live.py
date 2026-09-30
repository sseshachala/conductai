"""Interactive PKCE smoke test; credentials remain in process memory only."""
import argparse
import base64
import getpass
import hashlib
import json
import re
import secrets
import ssl
import sys
import time
import warnings
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from uuid import uuid4


class TestError(Exception):
    pass


TLS_CONTEXT = None


class SubjectMismatch(TestError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(url, data=None, headers=None):
    request = Request(url, data=data, headers=headers or {})
    try:
        response = build_opener(NoRedirect, HTTPSHandler(context=TLS_CONTEXT)).open(request, timeout=30)
    except HTTPError as error:
        response = error
    with response:
        status = response.code
        raw = response.read(1_048_577)
        if len(raw) > 1_048_576:
            raise TestError("Response exceeds size limit")
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeError):
            body = {}
        return status, body if isinstance(body, dict) else {}


def https_origin(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.fragment or parsed.query):
        raise TestError("Expected a public HTTPS URL without credentials/query/fragment")
    return parsed.scheme, parsed.hostname, parsed.port or 443


def jwt_part(token, index):
    try:
        part = token.split(".")[index]
        data = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except (ValueError, IndexError, UnicodeError):
        raise TestError("Access token is not a readable JWT") from None


def check_claims(token, config, user):
    # Sanity checks only. Production Conduct performs signature/trust verification.
    claims = jwt_part(token, 1)
    audience = claims.get("aud")
    audience = [audience] if isinstance(audience, str) else audience
    checks = (
        (claims.get("iss") == config["issuer"], "issuer"),
        (claims.get("sub") == user["subject"], "subject"),
        (isinstance(audience, list) and config["audience"] in audience, "audience"),
        (claims.get("token_use") == "access", "access-token profile"),
        (jwt_part(token, 0).get("alg") == "RS256", "signing algorithm"),
    )
    mismatches = [label for valid, label in checks if not valid]
    if mismatches:
        guidance = ""
        if "subject" in mismatches:
            matches = [entry["username"] for entry in config.get("users", [])
                       if entry["subject"] == claims.get("sub")]
            if matches:
                guidance = " Token subject matches configured account: " + ", ".join(matches) + "."
            else:
                guidance = " Token subject matches neither configured test account."
            guidance += " Check the login account and its Keycloak Details > ID; do not change grants."
        error_type = SubjectMismatch if mismatches == ["subject"] else TestError
        raise error_type("Local token check failed: " + ", ".join(mismatches)
                         + "; token was NOT sent to Conduct." + guidance)
    expiry = claims.get("exp")
    if not isinstance(expiry, (int, float)) or expiry <= time.time():
        raise TestError("Access token is expired or has no expiry")


def browser_token(config, metadata, user, manual_browser=False):
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    redirect = config["redirect_uri"]
    parsed = urlsplit(redirect)
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port
            or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise TestError("Test callback must be an explicit loopback HTTP URL")
    outcome = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            incoming = urlsplit(self.path)
            params = parse_qs(incoming.query)
            valid = incoming.path == parsed.path and params.get("state") == [state]
            if valid and len(params.get("code", [])) == 1:
                outcome["code"] = params["code"][0]
            elif valid:
                outcome["error"] = True
            self.send_response(200 if valid else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(b"Return to your terminal. You can close this tab." if valid else b"Invalid callback.")

    auth_url = metadata["authorization_endpoint"] + "?" + urlencode({
        "client_id": config["client_id"], "redirect_uri": redirect,
        "response_type": "code", "scope": "openid", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
        "prompt": "login", "max_age": "0", "login_hint": user["username"],
    })
    with HTTPServer(("127.0.0.1", parsed.port), Callback) as server:
        server.timeout = 1
        print(f"Log in as {user['username']} in the browser. Waiting up to 5 minutes.", flush=True)
        if manual_browser:
            print("Close ALL private/incognito windows, open a fresh private window, then open this URL:", flush=True)
        else:
            print("If no browser opens, open this login URL:", flush=True)
        print(auth_url, flush=True)
        if not manual_browser:
            webbrowser.open(auth_url)
        deadline = time.monotonic() + 300
        while not outcome and time.monotonic() < deadline:
            server.handle_request()
    if "code" not in outcome:
        raise TestError("Login failed or timed out; no tokens were sent to Conduct")
    status, body = request_json(metadata["token_endpoint"], urlencode({
        "grant_type": "authorization_code", "client_id": config["client_id"],
        "redirect_uri": redirect, "code": outcome.pop("code"), "code_verifier": verifier,
    }).encode(), {"Content-Type": "application/x-www-form-urlencoded"})
    token = body.get("access_token")
    if status != 200 or not isinstance(token, str):
        raise TestError(f"Token exchange failed (HTTP {status}); response withheld")
    check_claims(token, config, user)
    return token


def token_with_retry(config, metadata, user, manual_browser=False):
    for attempt in range(3):
        try:
            return browser_token(config, metadata, user, manual_browser=manual_browser)
        except SubjectMismatch as error:
            print(str(error))
            if attempt == 2 or input("Retry this user in a fresh private window? [y/N] ").strip().lower() != "y":
                raise TestError("Subject mismatch unresolved; no request sent for this user") from None
            manual_browser = True


def expected_grant_denial(positive_passed, status, denied, diagnostic):
    return positive_passed and status == 403 and denied and diagnostic == "federation_grant_invalid"


def mcp_check(config, credential, subject_token, session_id):
    rpc_id = str(uuid4())
    payload = {"jsonrpc": "2.0", "id": rpc_id, "method": "tools/call",
               "params": {"name": "guard_check_prompt", "arguments": {"prompt": "Say hello."}}}
    status, body = request_json(config["api_url"].rstrip("/") + "/mcp", json.dumps(payload).encode(), {
        "Authorization": "Bearer " + credential, "Content-Type": "application/json",
        "Conduct-Federation-Connection": config["connection_id"],
        "Conduct-Subject-Token": subject_token, "X-Claude-Surface": "oidc-live-test",
        "X-Session-Id": session_id,
    })
    result = body.get("result")
    result = result if isinstance(result, dict) else {}
    error = body.get("error")
    error = error if isinstance(error, dict) else {}
    marker = error.get("data") or result.get("structuredContent") or {}
    safe_codes = {
        "federation_evidence_required", "federation_invalid_evidence",
        "federation_evidence_expired", "federation_ambiguous_evidence",
        "federation_invalid_connection", "federation_caller_inactive",
        "federation_workspace_mismatch", "federation_binding_required",
        "federation_grant_invalid", "federation_principal_required",
        "federation_connection_inactive", "federation_storage_unavailable",
        "federation_service_caller_required",
    }
    diagnostic = "unclassified_response"
    code = marker.get("code") if isinstance(marker, dict) else None
    if isinstance(code, str) and code in safe_codes:
        diagnostic = code
    elif error.get("message") == "Token not recognized":
        diagnostic = "caller_token_not_recognized"
    elif error.get("message") == "missing token (use Authorization: Bearer)":
        diagnostic = "caller_token_missing"
    denied = status in (401, 403) or (isinstance(marker, dict) and marker.get("identity_required") is True)
    verdict = "unknown"
    for item in result.get("content", []) or []:
        if isinstance(item, dict) and item.get("type") == "text":
            text = str(item.get("text", "")).lower()
            for prefix in ("ok", "warning", "blocked", "pending", "advisory"):
                if text.startswith(prefix):
                    verdict = prefix
                    break
    accepted = (status == 200 and body.get("id") == rpc_id and not error and not denied
                and not result.get("isError") and verdict in ("ok", "warning", "blocked", "pending"))
    return status, denied, accepted, verdict, diagnostic


def main(argv=None):
    global TLS_CONTEXT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Non-secret JSON test configuration")
    parser.add_argument("--ca", help="Trusted CA PEM for local HTTPS; never disables verification")
    parser.add_argument("--revoke", action="store_true", help="Pause for operator revocation of a dedicated grant, then retest the same token")
    parser.add_argument("--manual-browser", action="store_true",
                        help="Print login URLs for separate private browser sessions; do not auto-open")
    args = parser.parse_args(argv)
    TLS_CONTEXT = ssl.create_default_context(cafile=args.ca)
    with open(args.config, encoding="utf-8") as source:
        config = json.load(source)
    origin = https_origin(config["issuer"])
    https_origin(config["api_url"])
    status, metadata = request_json(config["issuer"].rstrip("/") + "/.well-known/openid-configuration")
    if status != 200 or metadata.get("issuer") != config["issuer"]:
        raise TestError("Discovery failed or issuer mismatch")
    for key in ("authorization_endpoint", "token_endpoint"):
        if https_origin(metadata.get(key, "")) != origin:
            raise TestError("Discovery endpoint origin mismatch")
    if "S256" not in metadata.get("code_challenge_methods_supported", []):
        raise TestError("IdP does not advertise S256 PKCE")
    if not sys.stdin.isatty():
        raise TestError("Run this test in your own interactive terminal")
    print("Target: " + config["api_url"] + " (policy checks only; no inference)")
    print("Connection: " + config["connection_id"])
    warnings.simplefilter("error", getpass.GetPassWarning)
    credential = getpass.getpass("Conduct service cond_api_* credential (hidden): ").strip()
    if not re.fullmatch(r"cond_api_[A-Za-z0-9_-]+", credential):
        raise TestError("Expected an API-type Conduct credential")
    session_id = "oidc-live-" + str(uuid4())
    print("Audit session: " + session_id)
    positive_passed = False
    passed = True
    retained = None
    for user in config["users"]:
        input(f"Press Enter to test {user['username']}...")
        token = token_with_retry(config, metadata, user, manual_browser=args.manual_browser)
        status, denied, accepted, verdict, diagnostic = mcp_check(config, credential, token, session_id)
        if user["expect"] == "accepted" and accepted and retained is None:
            retained = (token, user)
        token = None
        if user["expect"] == "accepted":
            positive_passed = accepted
            success = accepted
        else:
            # A broken credential must not make the negative test appear to pass.
            success = expected_grant_denial(positive_passed, status, denied, diagnostic)
        passed = passed and success
        print(f"{user['username']}: {'PASS' if success else 'FAIL'}; HTTP {status}; "
              f"identity denied={denied}; policy verdict={verdict}")
        if not accepted:
            print("Diagnostic: " + diagnostic)
        if user["expect"] == "accepted" and not success:
            print("Stopping before the negative test: fix Alice's positive path first.")
            return 1
    print("Check Flight Recorder for the audit session and acting-principal attribution.")
    if args.revoke:
        if not passed or retained is None:
            raise TestError("Positive and negative tests must pass before revocation")
        token, user = retained
        input("Revoke ONLY the dedicated positive test user's delegation grant in Conduct, then press Enter. ")
        check_claims(token, config, user)
        status, denied, _, _, diagnostic = mcp_check(config, credential, token, session_id)
        success = expected_grant_denial(True, status, denied, diagnostic)
        passed = passed and success
        print("Revoked grant, same unexpired token: " + ("PASS" if success else "FAIL"))
        print("Restore the dedicated test grant before another positive-path run.")
    else:
        print("SKIP grant revocation: rerun with --revoke using a disposable grant")
    print("Direct MCP identity verification only; LiteLLM delegation remains a separate adapter test.")
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (TestError, KeyboardInterrupt, EOFError, getpass.GetPassWarning) as error:
        print("Stopped: " + (str(error) if isinstance(error, TestError) else "Interactive test cancelled"))
        sys.exit(1)
    except Exception as error:
        print("Test failed: " + type(error).__name__ + "; details withheld to avoid exposing credentials")
        sys.exit(1)
