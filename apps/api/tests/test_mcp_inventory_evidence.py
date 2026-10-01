import json

from app.modules.guard.discovery_inventory import clean_evidence, clean_mcp_servers


def test_only_passive_metadata_survives_scan():
    server = {"id": "a" * 64, "name": "github", "scope": "user", "transport": "http", "disabled": False}
    untrusted = {**server, "headers": {"Authorization": "private"}, "url": "https://private.invalid", "approved": True,
                 "governed": True, "fingerprint": "invented"}
    result = clean_evidence({"mcp_servers": [untrusted], "approved": True})
    assert result == {"signals": [], "mcp_servers": [server]}
    assert "private" not in json.dumps(result)


def test_bounds_types_and_duplicates():
    server = {"id": "a" * 64, "name": "bad/name?secret", "scope": "user", "transport": "stdio", "disabled": "true"}
    assert clean_mcp_servers({}) == []
    assert clean_mcp_servers([None, {}, {**server, "id": "invalid"}]) == []
    result = clean_mcp_servers([server, server])
    assert len(result) == 1
    assert result[0]["name"] == "redacted"
    assert result[0]["disabled"] is False
    assert clean_mcp_servers([{**server, "transport": {}}]) == []
    assert len(clean_mcp_servers([{**server, "id": f"{i:064x}"} for i in range(120)])) == 100
