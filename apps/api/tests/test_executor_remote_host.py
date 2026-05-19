"""
Tests for the executor's _resolve_remote_host helper. Pure function: takes
a block + state + credentials dict, returns a connection-ready remote_host
dict (or None).
"""
from app.runtime import executor


def _brain_block_with_remote(ip_ref: str, credentials_from: str = "digitalocean") -> dict:
    return {
        "id": "impl",
        "data": {
            "type": "brain",
            "isAgentic": True,
            "config": {
                "remote_host": {
                    "ip_ref": ip_ref,
                    "credentials_from": credentials_from,
                },
            },
        },
    }


def test_returns_none_when_no_remote_host_configured():
    block = {"id": "b", "data": {"type": "brain", "config": {}}}
    assert executor._resolve_remote_host(block, state={}, credentials={}) is None


def test_returns_none_when_ip_ref_unresolvable():
    block = _brain_block_with_remote("{{missing.ip}}")
    out = executor._resolve_remote_host(
        block,
        state={},  # no `missing` key — ref stays unresolved
        credentials={"digitalocean": {"ssh_private_key": "k"}},
    )
    assert out is None


def test_returns_none_when_credentials_missing_ssh_key():
    block = _brain_block_with_remote("{{wait.ip}}")
    out = executor._resolve_remote_host(
        block,
        state={"wait": {"ip": "10.0.0.1"}},
        credentials={"digitalocean": {"token": "t"}},  # no ssh_private_key
    )
    assert out is None


def test_returns_resolved_host_when_all_present():
    block = _brain_block_with_remote("{{wait.ip}}")
    out = executor._resolve_remote_host(
        block,
        state={"wait": {"ip": "10.0.0.1"}},
        credentials={"digitalocean": {"ssh_private_key": "key", "token": "t"}},
    )
    assert out is not None
    assert out["ip"] == "10.0.0.1"
    assert out["username"] == "root"
    assert out["port"] == 22
    assert out["private_key"] == "key"


def test_respects_explicit_username_and_port():
    block = {
        "id": "impl",
        "data": {
            "type": "brain",
            "config": {
                "remote_host": {
                    "ip_ref": "{{wait.ip}}",
                    "credentials_from": "digitalocean",
                    "username": "ubuntu",
                    "port": 2222,
                },
            },
        },
    }
    out = executor._resolve_remote_host(
        block,
        state={"wait": {"ip": "10.0.0.1"}},
        credentials={"digitalocean": {"ssh_private_key": "key"}},
    )
    assert out is not None
    assert out["username"] == "ubuntu"
    assert out["port"] == 2222
