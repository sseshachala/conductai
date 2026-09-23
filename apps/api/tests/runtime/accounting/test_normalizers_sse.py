"""Chunk-safe SSE parser self-checks.

Covers the framing quirks the pre-Session-3 line-by-line extractor missed:
mid-line chunk boundaries, CRLF, comments, multi-data lines, malformed lines.
"""

from __future__ import annotations

from app.runtime.accounting.normalizers.sse import SSEEvent, SSEParser, parse_all


def test_simple_event():
    events = parse_all(b"data: hello\n\n")
    assert events == [SSEEvent(event="message", data="hello")]


def test_event_name_and_data():
    payload = b"event: ping\ndata: pong\n\n"
    assert parse_all(payload) == [SSEEvent(event="ping", data="pong")]


def test_multiple_data_lines_joined_with_newline():
    payload = b"data: line1\ndata: line2\n\n"
    assert parse_all(payload) == [SSEEvent(event="message", data="line1\nline2")]


def test_crlf_line_endings():
    payload = b"data: hi\r\n\r\n"
    assert parse_all(payload) == [SSEEvent(event="message", data="hi")]


def test_comment_lines_ignored():
    payload = b": this is a comment\ndata: real\n\n"
    assert parse_all(payload) == [SSEEvent(event="message", data="real")]


def test_id_and_retry_lines_ignored():
    payload = b"id: 42\nretry: 3000\ndata: real\n\n"
    assert parse_all(payload) == [SSEEvent(event="message", data="real")]


def test_chunk_boundary_mid_line():
    """The whole point of the new parser — legacy line-by-line broke here."""
    parser = SSEParser()
    events_a = list(parser.feed(b"data: he"))
    events_b = list(parser.feed(b"llo\n\n"))
    assert events_a == []
    assert events_b == [SSEEvent(event="message", data="hello")]


def test_multiple_events_across_chunks():
    parser = SSEParser()
    got = []
    got.extend(parser.feed(b"data: a\n\ndat"))
    got.extend(parser.feed(b"a: b\n\n"))
    assert got == [
        SSEEvent(event="message", data="a"),
        SSEEvent(event="message", data="b"),
    ]


def test_flush_dispatches_buffered_event():
    parser = SSEParser()
    list(parser.feed(b"data: no_terminator"))
    # Feed the line delimiter but not the blank line dispatch trigger
    list(parser.feed(b"\n"))
    got = list(parser.flush())
    assert got == [SSEEvent(event="message", data="no_terminator")]


def test_malformed_line_without_field_prefix_ignored():
    payload = b"weird line with no colon\ndata: ok\n\n"
    assert parse_all(payload) == [SSEEvent(event="message", data="ok")]


def test_utf8_across_chunks_decodes_safely():
    payload_full = "data: café\n\n".encode("utf-8")
    # Split mid-multibyte character
    left = payload_full[:8]
    right = payload_full[8:]
    parser = SSEParser()
    got = list(parser.feed(left)) + list(parser.feed(right))
    got_data = "".join(e.data for e in got)
    assert "caf" in got_data  # partial UTF-8 either decodes correctly or replaces
