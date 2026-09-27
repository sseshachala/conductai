from datetime import datetime, timedelta, timezone

from app.modules.glens.platform_evidence import PlatformEvidenceQuery


def test_today_ignores_stale_model_dates(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 27, 12, 45, tzinfo=timezone.utc)

    monkeypatch.setattr("app.modules.glens.platform_evidence.datetime", Clock)
    query = PlatformEvidenceQuery(surface="gateway", intent="spend", period="today",
        since="2026-09-26T00:00:00Z", until="2026-09-27T00:00:00Z")
    assert query.since == datetime(2026, 9, 27, tzinfo=timezone.utc)
    assert query.until == query.since + timedelta(days=1)


def test_explicit_historical_window_stays_fixed():
    query = PlatformEvidenceQuery(surface="gateway", intent="spend",
        since="2026-09-26T00:00:00Z", until="2026-09-27T00:00:00Z")
    assert query.since == datetime(2026, 9, 26, tzinfo=timezone.utc)
