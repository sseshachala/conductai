"""Extract only protocol response IDs, never request text or arbitrary metadata."""
import json
import re

from .normalizers.sse import SSEParser


def response_id(value):
    return value if isinstance(value, str) and len(value) <= 160 and re.fullmatch(
        r"(?:msg[_-]|resp[_-]|chatcmpl-)[A-Za-z0-9_-]+", value) else None


def recorded_response_id(payload):
    if not payload:
        return None
    def identity(obj):
        if not isinstance(obj, dict):
            return None
        values = {response_id(obj.get("id"))}
        values.update(response_id(obj[key].get("id")) for key in ("message", "response")
                      if isinstance(obj.get(key), dict))
        values.discard(None)
        return next(iter(values)) if len(values) == 1 else None
    try:
        return identity(json.loads(payload))
    except (ValueError, UnicodeDecodeError):
        pass
    parser = SSEParser()
    found = set()
    for chunk in range(0, len(payload), 16384):
        for event in parser.feed(payload[chunk:chunk + 16384]):
            try:
                value = identity(json.loads(event.data))
            except ValueError:
                continue
            if value:
                found.add(value)
                if len(found) > 1:
                    return None
    return next(iter(found)) if len(found) == 1 else None
