"""Keyset ("cursor") paging for newest-first lists ordered by ``(ts DESC, id DESC)``.

Client sends ``before=<iso_ts>|<id>`` taken from the LAST row it holds and gets
rows strictly older in that order. Bad cursor -> HTTP 400.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import Uuid, and_, or_

Cursor = tuple[datetime, str]


def parse_before(before: str | None) -> Cursor | None:
    """Parse ``"<iso_ts>|<id>"``; None/empty -> None; malformed -> 400."""
    if not before:
        return None
    ts_raw, sep, id_raw = before.partition("|")
    if not sep or not ts_raw.strip() or not id_raw.strip():
        raise HTTPException(status_code=400, detail="Invalid 'before' cursor: expected '<iso_ts>|<id>'")
    # An unescaped '+' in a query string arrives as ' ' ("...T10:00:00 00:00").
    ts_raw = ts_raw.strip().replace(" ", "+").replace("Z", "+00:00")
    try:
        ts = datetime.fromisoformat(ts_raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid 'before' cursor: bad timestamp") from None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts, id_raw.strip()


def before_clause(ts_col, id_col, before: str | None):
    """SQLAlchemy predicate for rows strictly older than the cursor, or None.

    Pair with ``.order_by(ts_col.desc(), id_col.desc())``.
    """
    cur = parse_before(before)
    if cur is None:
        return None
    ts, raw_id = cur
    last_id: object = raw_id
    if isinstance(id_col.type, Uuid):
        try:
            last_id = uuid.UUID(raw_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid 'before' cursor: bad id") from None
    return or_(ts_col < ts, and_(ts_col == ts, id_col < last_id))


def before_sql(before: str | None, ts_col: str = "ts", id_col: str = "id") -> tuple[str, dict]:
    """Raw-SQL variant (text ids): returns ``(fragment, params)``; fragment is '' when no cursor."""
    cur = parse_before(before)
    if cur is None:
        return "", {}
    ts, raw_id = cur
    frag = f"({ts_col} < :kb_ts OR ({ts_col} = :kb_ts AND {id_col} < :kb_id))"
    return frag, {"kb_ts": ts, "kb_id": raw_id}
