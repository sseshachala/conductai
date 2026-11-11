"""Push sinks for ``conduct audit feed``: Splunk HEC and Microsoft Sentinel.

Sinks receive native feed events (dicts) and deliver them in size-bounded
batches. ``send`` returns only after the destination acknowledged every batch
(retrying 429/5xx/network errors with exponential backoff and jitter), so the
caller advances its cursor strictly after acknowledgement. Delivery is
at-least-once: after a crash mid-page the page is sent again, and the event
``id`` is the dedupe key.

Secrets come from files or environment variables only. They are never put on
argv and never appear in log lines or error messages.
"""
from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SINKS = ("splunk-hec", "sentinel")
HEC_TOKEN_ENV = "CONDUCT_HEC_TOKEN"
SENTINEL_SECRET_ENV = "CONDUCT_SENTINEL_CLIENT_SECRET"
HEC_SOURCETYPE = "conduct:guard:audit"
INGEST_API_VERSION = "2023-01-01"
MONITOR_SCOPE = "https://monitor.azure.com//.default"
MAX_BATCH_EVENTS = 500
MAX_BATCH_BYTES = 900_000  # Logs Ingestion API caps a call at 1 MB


class SinkError(RuntimeError):
    """Delivery failed permanently (non-retryable response or retries exhausted)."""


class _Retryable(Exception):
    def __init__(self, reason, retry_after=None):
        super().__init__(reason)
        self.retry_after = retry_after


def read_secret(file_path, env_name, environ=None, what="secret"):
    """Secret from a file (preferred) or an environment variable. Never from argv."""
    environ = os.environ if environ is None else environ
    if file_path:
        try:
            value = Path(file_path).expanduser().read_text().strip()
        except OSError as exc:
            raise SinkError("cannot read %s file: %s" % (what, exc.strerror or "error")) from exc
        if not value:
            raise SinkError("%s file is empty" % what)
        return value
    value = (environ.get(env_name) or "").strip()
    if not value:
        raise SinkError("%s not provided: use the file option or set $%s" % (what, env_name))
    return value


def _epoch(ts):
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def make_batches(items, max_events=MAX_BATCH_EVENTS, max_bytes=MAX_BATCH_BYTES):
    """Group ``(payload_bytes)`` items into batches bounded by count and size."""
    batch, size = [], 0
    for item in items:
        if batch and (len(batch) >= max_events or size + len(item) > max_bytes):
            yield batch
            batch, size = [], 0
        batch.append(item)
        size += len(item)
    if batch:
        yield batch


class _Http:
    """POST wrapper that reports status instead of raising, so callers classify errors."""

    def __init__(self, urlopen=None, timeout=30):
        self._urlopen = urlopen or urllib.request.urlopen
        self.timeout = timeout

    def post(self, url, data, headers):
        req = urllib.request.Request(url, data=data, method="POST", headers=headers)
        try:
            with self._urlopen(req, timeout=self.timeout) as resp:
                return resp.status if hasattr(resp, "status") else resp.getcode(), resp.read(), resp.headers
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read() if hasattr(exc, "read") else b"", exc.headers
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise _Retryable("network error: %s" % type(exc).__name__) from exc


def _retry_after(headers):
    try:
        value = headers.get("Retry-After") if headers is not None else None
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class _Sink:
    def __init__(self, *, http=None, sleep=time.sleep, attempts=8, backoff=1.0, backoff_cap=60.0,
                 max_events=MAX_BATCH_EVENTS, max_bytes=MAX_BATCH_BYTES, rng=None):
        self.http = http or _Http()
        self.sleep, self.attempts = sleep, attempts
        self.backoff, self.backoff_cap = backoff, backoff_cap
        self.max_events, self.max_bytes = max_events, max_bytes
        self._rng = rng or random.random

    def send(self, events):
        """Deliver all events; returns once every batch is acknowledged."""
        encoded = [self._encode(e) for e in events]
        for batch in make_batches(encoded, self.max_events, self.max_bytes):
            self._deliver(batch)

    def _deliver(self, batch):
        last = "unknown"
        for attempt in range(1, self.attempts + 1):
            try:
                self._post_batch(batch)
                return
            except _Retryable as exc:
                last = str(exc)
                if attempt == self.attempts:
                    break
                delay = min(self.backoff_cap, self.backoff * (2 ** (attempt - 1)))
                delay = exc.retry_after if exc.retry_after is not None else delay * (0.5 + self._rng() / 2)
                self.sleep(min(delay, self.backoff_cap))
        raise SinkError("%s: delivery failed after %d attempts (%s)" % (self.name, self.attempts, last))

    def _classify(self, status, body):
        """Raise for a non-success status. 408/429/5xx are retryable, other 4xx are not."""
        text = body.decode("utf-8", "replace")[:200] if isinstance(body, (bytes, bytearray)) else ""
        if status in (408, 429) or status >= 500:
            raise _Retryable("HTTP %d" % status)
        raise SinkError("%s: rejected with HTTP %d %s" % (self.name, status, text))


class SplunkHecSink(_Sink):
    name = "splunk-hec"

    def __init__(self, url, token, *, index=None, sourcetype=HEC_SOURCETYPE, **kw):
        super().__init__(**kw)
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise SinkError("--hec-url must be an http(s) URL")
        path = parsed.path.rstrip("/")
        if not path.endswith("/services/collector/event") and not path.endswith("/services/collector"):
            path += "/services/collector/event"
        self.url = urllib.parse.urlunparse(parsed._replace(path=path))
        self._token, self.index, self.sourcetype = token, index, sourcetype

    def _encode(self, event):
        rec = {"event": event, "sourcetype": self.sourcetype, "source": "conduct"}
        t = _epoch(event.get("ts"))
        if t is not None:
            rec["time"] = round(t, 3)
        if self.index:
            rec["index"] = self.index
        return json.dumps(rec, separators=(",", ":"), default=str).encode()

    def _post_batch(self, batch):
        status, body, headers = self.http.post(
            self.url, b"".join(batch),
            {"Authorization": "Splunk " + self._token, "Content-Type": "application/json"})
        if status == 200:
            try:
                if json.loads(body or b"{}").get("code", 0) == 0:
                    return
            except ValueError:
                pass
            raise SinkError("%s: unexpected acknowledgement from HEC" % self.name)
        if status in (503, 429):  # HEC: server busy
            raise _Retryable("HTTP %d" % status, _retry_after(headers))
        self._classify(status, body)


class SentinelSink(_Sink):
    """Azure Monitor Logs Ingestion API with Entra client-credential auth."""

    name = "sentinel"

    def __init__(self, dce_url, dcr_id, stream, tenant_id, client_id, client_secret, *,
                 authority="https://login.microsoftonline.com", clock=time.time, **kw):
        super().__init__(**kw)
        parsed = urllib.parse.urlparse(dce_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise SinkError("--dce-url must be an https URL")
        self.url = "%s://%s/dataCollectionRules/%s/streams/%s?api-version=%s" % (
            parsed.scheme, parsed.netloc, urllib.parse.quote(dcr_id, safe=""),
            urllib.parse.quote(stream, safe=""), INGEST_API_VERSION)
        self._token_url = "%s/%s/oauth2/v2.0/token" % (authority.rstrip("/"), urllib.parse.quote(tenant_id, safe=""))
        self._client_id, self._secret, self._clock = client_id, client_secret, clock
        self._access, self._expires = None, 0.0

    def _encode(self, event):
        rec = dict(event)
        if rec.get("ts") and "TimeGenerated" not in rec:
            rec["TimeGenerated"] = rec["ts"]
        return json.dumps(rec, separators=(",", ":"), default=str).encode()

    def _bearer(self, force=False):
        if not force and self._access and self._clock() < self._expires - 60:
            return self._access
        form = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": self._client_id,
                                       "client_secret": self._secret, "scope": MONITOR_SCOPE}).encode()
        status, body, headers = self.http.post(self._token_url, form,
                                               {"Content-Type": "application/x-www-form-urlencoded"})
        if status != 200:
            if status in (408, 429) or status >= 500:
                raise _Retryable("Entra token HTTP %d" % status, _retry_after(headers))
            raise SinkError("sentinel: Entra token request rejected with HTTP %d "
                            "(check tenant, client id and secret)" % status)
        try:
            data = json.loads(body)
            self._access = data["access_token"]
            self._expires = self._clock() + float(data.get("expires_in", 3600))
        except (ValueError, KeyError, TypeError) as exc:
            raise SinkError("sentinel: malformed Entra token response") from exc
        return self._access

    def _post_batch(self, batch):
        payload = b"[" + b",".join(batch) + b"]"
        for refreshed in (False, True):
            status, body, headers = self.http.post(
                self.url, payload,
                {"Authorization": "Bearer " + self._bearer(force=refreshed), "Content-Type": "application/json"})
            if status == 401 and not refreshed:
                continue  # token expired or rotated: fetch a new one once
            break
        if status in (200, 204):
            return
        if status in (429, 503):
            raise _Retryable("HTTP %d" % status, _retry_after(headers))
        self._classify(status, body)


def build_sink(args, environ=None, **kw):
    """Construct the sink chosen by ``--sink``; secrets only from files or env."""
    environ = os.environ if environ is None else environ
    if args.sink == "splunk-hec":
        if not args.hec_url:
            raise SinkError("--sink splunk-hec requires --hec-url")
        token = read_secret(args.hec_token_file, HEC_TOKEN_ENV, environ, "HEC token")
        return SplunkHecSink(args.hec_url, token, index=args.hec_index, **kw)
    if args.sink == "sentinel":
        missing = [f for f, v in (("--dce-url", args.dce_url), ("--dcr-id", args.dcr_id),
                                  ("--stream", args.stream)) if not v]
        if missing:
            raise SinkError("--sink sentinel requires " + ", ".join(missing))
        tenant = args.tenant_id or environ.get("AZURE_TENANT_ID")
        client = args.client_id or environ.get("AZURE_CLIENT_ID")
        if not tenant or not client:
            raise SinkError("--sink sentinel needs a tenant and client id: --tenant-id/--client-id "
                            "or $AZURE_TENANT_ID/$AZURE_CLIENT_ID")
        secret = read_secret(args.client_secret_file, SENTINEL_SECRET_ENV, environ, "client secret")
        return SentinelSink(args.dce_url, args.dcr_id, args.stream, tenant, client, secret, **kw)
    raise SinkError("unknown sink %r" % args.sink)
