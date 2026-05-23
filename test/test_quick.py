"""Tests for the quick_add backend method on each backend."""

from unittest.mock import MagicMock, patch

import pytest

from roxcal.backends.google_caldav import GoogleCalDAVBackend
from roxcal.backends.google_oauth import GoogleOAuthBackend
from roxcal.backends.microsoft_graph import MicrosoftGraphBackend
from roxcal.config import Account


def _google_backend():
    return GoogleOAuthBackend(
        Account(
            name="t",
            backend="google_oauth",
            email="me@example.com",
            client_id="cid",
            client_secret="cs",
        )
    )


def _make_quickadd_mock(returned_event):
    """Build a MagicMock that walks
    svc.events().quickAdd(...).execute() and returns the dict."""
    svc = MagicMock()
    svc.events.return_value.quickAdd.return_value.execute.return_value = returned_event
    return svc


def test_google_quick_add_calls_quickadd_with_primary_default(capsys):
    backend = _google_backend()
    svc = _make_quickadd_mock({"id": "evt1", "htmlLink": "https://example.com/evt1"})
    with patch.object(backend, "_service", return_value=svc):
        backend.quick_add("Lunch with Maria tomorrow 12:30")
    svc.events.return_value.quickAdd.assert_called_once_with(
        calendarId="primary",
        text="Lunch with Maria tomorrow 12:30",
        sendUpdates="all",
    )
    out = capsys.readouterr().out
    assert "https://example.com/evt1" in out


def test_google_quick_add_uses_supplied_calendar():
    backend = _google_backend()
    svc = _make_quickadd_mock({"id": "evt2", "htmlLink": "http://x"})
    with patch.object(backend, "_service", return_value=svc):
        backend.quick_add("Coffee tomorrow", calendar="work@x.com")
    svc.events.return_value.quickAdd.assert_called_once_with(
        calendarId="work@x.com",
        text="Coffee tomorrow",
        sendUpdates="all",
    )


def test_google_quick_add_prints_meet_link_when_present(capsys):
    backend = _google_backend()
    svc = _make_quickadd_mock(
        {
            "id": "evt3",
            "htmlLink": "http://x",
            "hangoutLink": "https://meet.google.com/abc-defg-hij",
        }
    )
    with patch.object(backend, "_service", return_value=svc):
        backend.quick_add("Sync with team tomorrow 14:00")
    out = capsys.readouterr().out
    assert "https://meet.google.com/abc-defg-hij" in out


def test_caldav_quick_add_refuses(capsys):
    backend = GoogleCalDAVBackend(
        Account(
            name="t",
            backend="google_caldav",
            email="a@b",
            caldav_password="x",
        )
    )
    with pytest.raises(SystemExit):
        backend.quick_add("Anything")
    err = capsys.readouterr().err
    assert "not supported" in err
    assert "google_caldav" in err


def test_microsoft_quick_add_refuses(capsys):
    backend = MicrosoftGraphBackend(
        Account(name="t", backend="microsoft_graph", client_id="x")
    )
    with pytest.raises(SystemExit):
        backend.quick_add("Anything")
    err = capsys.readouterr().err
    assert "not supported" in err
    assert "microsoft_graph" in err
