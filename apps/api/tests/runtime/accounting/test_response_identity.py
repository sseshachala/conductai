import json

import pytest

from app.runtime.accounting.response_identity import recorded_response_id


@pytest.mark.parametrize("payload,expected", [
    ({"id": "msg_fixture"}, "msg_fixture"), ({"id": "resp_fixture"}, "resp_fixture"),
    ({"id": "chatcmpl-fixture"}, "chatcmpl-fixture"), ({"id": "private text"}, None),
    ({"id": "sk-private"}, None), ({"id": "msg_" + "x" * 161}, None),
    ({"id": 3}, None), ({"content": "msg_not-an-id"}, None),
])
def test_only_protocol_identifiers_are_retained(payload, expected):
    assert recorded_response_id(json.dumps(payload).encode()) == expected


@pytest.mark.parametrize("key", ["message", "response"])
def test_stream_identity_is_chunk_safe_and_conflicts_are_not_matched(key):
    one = f'data: {json.dumps({key: {"id": "msg_fixture"}})}\r\n\r\n'.encode()
    assert recorded_response_id(one) == "msg_fixture"
    assert recorded_response_id(one + one) == "msg_fixture"
    two = b'data: {"id":"resp_other"}\n\n'
    assert recorded_response_id(one + two) is None
