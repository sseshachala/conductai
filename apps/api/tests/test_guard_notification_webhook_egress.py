"""Notification webhooks only reach public URLs and never follow redirects."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.modules.guard.routers import notifications
from app.modules.guard.routers.events_notify import _fanout_webhook


def _ch(url: str):
    return SimpleNamespace(id="c1", channel_type="webhook", channel_ref=url)


@pytest.fixture
def posted(monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append((url, kw))
        return MagicMock(status_code=200)

    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)
    return calls


@pytest.mark.parametrize("url", [
    "https://169.254.169.254/latest/meta-data/",
    "https://127.0.0.1/hook",
    "https://10.0.0.5/hook",
    "https://[::ffff:127.0.0.1]/hook",
    "file:///etc/passwd",
])
def test_fanout_skips_non_public_urls(posted, url):
    _fanout_webhook([_ch(url)], {"event": "x"})
    assert posted == []


def test_fanout_posts_public_url_without_redirects(posted):
    _fanout_webhook([_ch("https://93.184.216.34/hook")], {"event": "x"})
    assert len(posted) == 1
    assert posted[0][1]["follow_redirects"] is False


def test_fanout_bad_channel_does_not_stop_others(posted):
    _fanout_webhook([_ch("https://127.0.0.1/a"), _ch("https://93.184.216.34/b")], {"event": "x"})
    assert [u for u, _ in posted] == ["https://93.184.216.34/b"]


def test_allowlisted_host_is_posted(posted, monkeypatch):
    monkeypatch.setattr(settings, "egress_allowed_hosts", ["10.0.0.5"])
    _fanout_webhook([_ch("https://10.0.0.5/hook")], {"event": "x"})
    assert len(posted) == 1


def test_save_time_check_rejects_private_webhook():
    with pytest.raises(HTTPException) as exc:
        notifications._check_webhook_ref("webhook", "https://169.254.169.254/")
    assert exc.value.status_code == 422


def test_save_time_check_allows_public_and_ignores_other_types():
    notifications._check_webhook_ref("webhook", "https://93.184.216.34/hook")
    notifications._check_webhook_ref("slack", "#general")
    notifications._check_webhook_ref("email", "ops@example.com")
