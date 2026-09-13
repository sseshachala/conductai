"""Loopback-only Gmail OTP broker for production security journeys."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
DEFAULT_DIRECTORY = Path.home() / ".conduct" / "e2e" / "otpbroker"
DEFAULT_TOKEN_FILE = DEFAULT_DIRECTORY / "token.json"
OTP_PATTERNS = (
    re.compile(r"(?:verification|security|one[ -]time|sign[ -]in)\s+code\s*(?:is|:)?\s*(\d{6})", re.I),
    re.compile(r"\bcode\s*(?:is|:)?\s*(\d{6})\b", re.I),
)


class OtpBrokerError(RuntimeError):
    pass


def discover_client_file(directory: Path = DEFAULT_DIRECTORY) -> Path:
    candidates = sorted(path for path in directory.glob("*.json") if path.name != "token.json")
    if len(candidates) != 1:
        raise OtpBrokerError(
            f"expected exactly one OAuth client JSON in {directory}; found {len(candidates)}"
        )
    return candidates[0]


def load_client(path: Path) -> dict[str, str]:
    try:
        raw = json.loads(path.read_text())
        client = raw["installed"]
        return {
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "auth_uri": client.get("auth_uri", "https://accounts.google.com/o/oauth2/v2/auth"),
            "token_uri": client.get("token_uri", "https://oauth2.googleapis.com/token"),
        }
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise OtpBrokerError(f"invalid installed-app OAuth client file: {path}") from error


def write_private_json(path: Path, value: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream)
            stream.write("\n")
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def post_form(url: str, fields: dict[str, str]) -> dict:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(fields).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except (urllib.error.URLError, json.JSONDecodeError) as error:
        raise OtpBrokerError("Google OAuth token request failed") from error


def authorize(client_file: Path, token_file: Path) -> None:
    client = load_client(client_file)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    result: dict[str, str] = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            if hmac.compare_digest(query.get("state", [""])[0], state):
                result["code"] = query.get("code", [""])[0]
            result["error"] = query.get("error", [""])[0]
            body = b"Authorization received. You can close this window."
            self.send_response(200 if result.get("code") else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), CallbackHandler)
    server.timeout = 180
    redirect_uri = f"http://127.0.0.1:{server.server_port}/"
    authorization_url = client["auth_uri"] + "?" + urllib.parse.urlencode({
        "client_id": client["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GMAIL_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    print("Opening Google authorization for Gmail read-only access...")
    if not webbrowser.open(authorization_url):
        print(f"Open this URL in a browser:\n{authorization_url}")
    server.handle_request()
    server.server_close()
    if not result.get("code"):
        raise OtpBrokerError(f"Google authorization failed: {result.get('error') or 'no callback received'}")
    token = post_form(client["token_uri"], {
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "code": result["code"],
        "code_verifier": verifier,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    })
    if not token.get("refresh_token"):
        raise OtpBrokerError("Google did not return a refresh token")
    granted_scopes = set(str(token.get("scope", "")).split())
    if GMAIL_SCOPE not in granted_scopes:
        raise OtpBrokerError("Google did not grant Gmail read-only access")
    token["expires_at"] = time.time() + int(token.get("expires_in", 3600))
    token["scope"] = token.get("scope", GMAIL_SCOPE)
    write_private_json(token_file, token)
    print(f"Gmail authorization saved to {token_file}")


def decode_body(payload: dict) -> str:
    chunks: list[str] = []

    def visit(part: dict) -> None:
        data = part.get("body", {}).get("data")
        if data:
            try:
                padded = data + "=" * (-len(data) % 4)
                chunks.append(base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace"))
            except (ValueError, TypeError):
                pass
        for child in part.get("parts", []):
            visit(child)

    visit(payload)
    plain = html.unescape(re.sub(r"<[^>]+>", " ", "\n".join(chunks)))
    return re.sub(r"\s+", " ", plain)


def extract_code(message: dict) -> str | None:
    headers = message.get("payload", {}).get("headers", [])
    subject = next((header.get("value", "") for header in headers if header.get("name", "").lower() == "subject"), "")
    text = subject + " " + decode_body(message.get("payload", {}))
    for pattern in OTP_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


class GmailClient:
    def __init__(self, client_file: Path, token_file: Path):
        self.client = load_client(client_file)
        self.token_file = token_file
        self.used_message_ids: set[str] = set()
        try:
            self.token = json.loads(token_file.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise OtpBrokerError(
                "missing or invalid Gmail token; run production.py --authorize-gmail first"
            ) from error
        if not self.token.get("refresh_token"):
            raise OtpBrokerError("Gmail token does not contain a refresh token")

    def access_token(self) -> str:
        if self.token.get("access_token") and float(self.token.get("expires_at", 0)) > time.time() + 60:
            return self.token["access_token"]
        refreshed = post_form(self.client["token_uri"], {
            "client_id": self.client["client_id"],
            "client_secret": self.client["client_secret"],
            "refresh_token": self.token["refresh_token"],
            "grant_type": "refresh_token",
        })
        if not refreshed.get("access_token"):
            raise OtpBrokerError("Google did not return an access token")
        self.token.update(refreshed)
        self.token["expires_at"] = time.time() + int(refreshed.get("expires_in", 3600))
        write_private_json(self.token_file, self.token)
        return self.token["access_token"]

    def api_json(self, path: str, query: dict[str, str] | None = None) -> dict:
        url = "https://gmail.googleapis.com/gmail/v1/" + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.access_token()}"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except (urllib.error.URLError, json.JSONDecodeError) as error:
            raise OtpBrokerError("Gmail API request failed") from error

    def find_code(self, recipient: str, after_ms: int) -> str | None:
        listing = self.api_json("users/me/messages", {
            "q": f'to:"{recipient}" newer_than:1d',
            "maxResults": "10",
        })
        for item in listing.get("messages", []):
            message_id = item.get("id", "")
            if not message_id or message_id in self.used_message_ids:
                continue
            message = self.api_json(f"users/me/messages/{urllib.parse.quote(message_id)}", {"format": "full"})
            if int(message.get("internalDate", 0)) < after_ms - 10_000:
                continue
            code = extract_code(message)
            if code:
                self.used_message_ids.add(message_id)
                return code
        return None

    def wait_for_code(self, recipient: str, after_ms: int, timeout: int = 90) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            code = self.find_code(recipient, after_ms)
            if code:
                return code
            time.sleep(2)
        raise OtpBrokerError("timed out waiting for a new Clerk verification email")


@contextmanager
def serve(client: GmailClient, allowed_recipients: set[str]) -> Iterator[tuple[str, str]]:
    bearer = secrets.token_urlsafe(32)
    allowed = {recipient.casefold() for recipient in allowed_recipients}

    class BrokerHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if self.path != "/otp" or not hmac.compare_digest(
                self.headers.get("Authorization", ""), f"Bearer {bearer}"
            ):
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 4096:
                    raise ValueError("invalid request size")
                request = json.loads(self.rfile.read(length))
                recipient = str(request["email"]).casefold()
                after_ms = int(request["after_ms"])
                if recipient not in allowed:
                    raise ValueError("recipient is not allowlisted")
                code = client.wait_for_code(recipient, after_ms)
                self._json(200, {"code": code})
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                self._json(400, {"error": str(error)})
            except OtpBrokerError as error:
                self._json(504, {"error": str(error)})

        def _json(self, status: int, value: dict) -> None:
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), BrokerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/otp", bearer
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-file", type=Path)
    parser.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN_FILE)
    args = parser.parse_args()
    authorize(args.client_file or discover_client_file(), args.token_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
