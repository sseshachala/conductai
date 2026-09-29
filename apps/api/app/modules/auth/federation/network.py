"""Public HTTPS JSON fetch with DNS address pinning and no redirects/proxies."""
import http.client
import ipaddress
import json
import socket
import ssl
import time
import threading
from queue import Queue
from urllib.parse import urlsplit

from .config import https_endpoint

MAX_BYTES = 128 * 1024
TIMEOUT_SECONDS = 5
_DNS_SLOTS = threading.BoundedSemaphore(8)


class VerificationUnavailable(Exception):
    """Safe error: never includes URLs, token contents or upstream response bodies."""


def public_addresses(host: str) -> list[str]:
    if not _DNS_SLOTS.acquire(blocking=False):
        raise VerificationUnavailable("federation_dns_busy")
    result = Queue(maxsize=1)
    done = threading.Event()
    def resolve():
        try:
            result.put(socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM))
        except OSError:
            result.put(None)
        finally:
            _DNS_SLOTS.release()
            done.set()
    try:
        threading.Thread(target=resolve, daemon=True).start()
    except RuntimeError:
        _DNS_SLOTS.release()
        raise VerificationUnavailable("federation_dns_busy") from None
    if not done.wait(TIMEOUT_SECONDS):
        raise VerificationUnavailable("federation_dns_timeout")
    answers = result.get()
    if answers is None:
        raise VerificationUnavailable("federation_dns_failed")
    addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
    if not addresses or len(addresses) > 32:
        raise VerificationUnavailable("federation_endpoint_unavailable")
    for value in addresses:
        address = ipaddress.ip_address(value)
        if (not address.is_global or address.is_multicast
                or getattr(address, "ipv4_mapped", None) is not None
                or getattr(address, "sixtofour", None) is not None
                or getattr(address, "teredo", None) is not None):
            raise VerificationUnavailable("federation_endpoint_not_public")
    return addresses


def fetch_json(url: str) -> dict:
    connection = None
    try:
        parsed = urlsplit(https_endpoint(url))
        addresses = public_addresses(parsed.hostname)
        connection = http.client.HTTPSConnection(
            parsed.hostname, timeout=TIMEOUT_SECONDS, context=ssl.create_default_context(),
        )
        # TLS still authenticates the original hostname; the TCP socket cannot
        # perform a second DNS lookup to a private address (DNS rebinding).
        connection._create_connection = lambda _address, timeout, source_address=None: socket.create_connection(
            (addresses[0], 443), timeout, source_address,
        )
        deadline = time.monotonic() + TIMEOUT_SECONDS
        connection.request("GET", parsed.path or "/", headers={"Accept": "application/json", "Accept-Encoding": "identity"})
        response = connection.getresponse()
        if response.status != 200 or response.getheader("Content-Encoding", "identity") != "identity":
            raise VerificationUnavailable("federation_endpoint_unavailable")
        body = bytearray()
        while True:
            if time.monotonic() >= deadline:
                raise VerificationUnavailable("federation_endpoint_timeout")
            chunk = response.read1(min(8192, MAX_BYTES + 1 - len(body)))
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                raise VerificationUnavailable("federation_document_too_large")
            if not chunk:
                break
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError
        return data
    except VerificationUnavailable:
        raise
    except (OSError, ValueError, RecursionError, http.client.HTTPException):
        raise VerificationUnavailable("federation_endpoint_unavailable") from None
    finally:
        if connection:
            connection.close()
