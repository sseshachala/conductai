import socket

import pytest

from app.modules.auth.federation import network


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1",
                                    "::ffff:8.8.8.8", "239.1.1.1", "2002:7f00:1::"])
def test_non_public_or_mapped_addresses_rejected(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(None, None, None, None, (address, 443))])
    with pytest.raises(network.VerificationUnavailable):
        network.public_addresses("example.com")


def test_mixed_dns_answers_rejected(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [
        (None, None, None, None, ("8.8.8.8", 443)), (None, None, None, None, ("127.0.0.1", 443))])
    with pytest.raises(network.VerificationUnavailable):
        network.public_addresses("example.com")


def test_dns_timeout_is_bounded(monkeypatch):
    import threading
    release = threading.Event()
    finished = threading.Event()
    def stalled(*args, **kwargs):
        release.wait(1)
        finished.set()
        return []
    monkeypatch.setattr(socket, "getaddrinfo", stalled)
    monkeypatch.setattr(network, "TIMEOUT_SECONDS", 0.01)
    try:
        with pytest.raises(network.VerificationUnavailable, match="dns_timeout"):
            network.public_addresses("example.com")
    finally:
        release.set()
        assert finished.wait(1)


class Response:
    status = 200
    payload = b'{"keys": []}'
    def getheader(self, key, default):
        return default
    def read1(self, length):
        chunk, self.payload = self.payload[:length], self.payload[length:]
        return chunk


@pytest.fixture
def transport(monkeypatch):
    response = Response()
    sockets = []
    connections = []
    monkeypatch.setattr(network, "public_addresses", lambda _: ["8.8.8.8"])
    monkeypatch.setattr(socket, "create_connection", lambda address, *args: sockets.append(address))
    class Connection:
        def __init__(self, host, **kwargs):
            self.host, self.closed = host, False
            connections.append(self)
        def request(self, *args, **kwargs):
            self._create_connection((self.host, 443), 5)
        def getresponse(self):
            return response
        def close(self):
            self.closed = True
    monkeypatch.setattr(network.http.client, "HTTPSConnection", Connection)
    return response, sockets, connections


def test_pins_socket_and_preserves_tls_hostname(transport):
    _, sockets, connections = transport
    assert network.fetch_json("https://idp.example/keys") == {"keys": []}
    assert sockets == [("8.8.8.8", 443)]
    assert connections[0].host == "idp.example"
    assert connections[0].closed


@pytest.mark.parametrize("status", [301, 302, 307, 404, 500])
def test_no_redirects_or_error_bodies(transport, status):
    response, _, connections = transport
    response.status = status
    with pytest.raises(network.VerificationUnavailable):
        network.fetch_json("https://idp.example/keys")
    assert len(connections) == 1
    assert connections[0].closed


def test_bounded_response_and_safe_errors(transport):
    response, _, _ = transport
    response.payload = b"secret" * network.MAX_BYTES
    with pytest.raises(network.VerificationUnavailable, match="document_too_large") as error:
        network.fetch_json("https://idp.example/keys")
    assert "secret" not in str(error.value)
