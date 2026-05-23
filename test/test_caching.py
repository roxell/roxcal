"""Tests for the per-instance caching of service objects and calendar lists."""

from unittest.mock import MagicMock, patch

from roxcal.backends.google_oauth import GoogleOAuthBackend
from roxcal.backends.microsoft_graph import MicrosoftGraphBackend
from roxcal.config import Account


def _google():
    return GoogleOAuthBackend(
        Account(name="t", backend="google_oauth", email="me@x", client_id="i")
    )


def _ms():
    return MicrosoftGraphBackend(
        Account(name="t", backend="microsoft_graph", client_id="x")
    )


def test_google_service_is_cached():
    backend = _google()
    fake_service = MagicMock()
    build_calls = {"count": 0}

    def fake_build(*args, **kwargs):
        build_calls["count"] += 1
        return fake_service

    with patch.object(backend, "_load_creds") as load_creds:
        creds = MagicMock()
        creds.valid = True
        load_creds.return_value = creds
        with patch("googleapiclient.discovery.build", side_effect=fake_build):
            backend._service()
            backend._service()
            backend._service()
    assert build_calls["count"] == 1


def test_google_calendar_list_is_cached():
    backend = _google()
    svc = MagicMock()
    svc.calendarList.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "primary", "summary": "Primary"}]
    }
    with patch.object(backend, "_service", return_value=svc):
        first = backend._calendar_list()
        second = backend._calendar_list()
    assert first == {"primary": "Primary"}
    assert first is second
    svc.calendarList.return_value.list.assert_called_once()


def test_ms_token_is_cached():
    backend = _ms()
    app = MagicMock()
    cache = MagicMock()
    cache.has_state_changed = False
    app.get_accounts.return_value = [MagicMock()]
    app.acquire_token_silent.return_value = {"access_token": "TKN"}
    with patch.object(backend, "_msal_app", return_value=(app, cache)):
        a = backend._token()
        b = backend._token()
        c = backend._token()
    assert a == "TKN"
    assert a is b is c
    app.get_accounts.assert_called_once()
    app.acquire_token_silent.assert_called_once()


def test_ms_calendar_list_is_cached():
    backend = _ms()
    api = MagicMock(return_value={"value": [{"id": "AAA", "name": "Calendar"}]})
    with patch.object(backend, "_api", api):
        first = backend._calendar_list()
        second = backend._calendar_list()
    assert first == {"AAA": "Calendar"}
    assert first is second
    api.assert_called_once_with("GET", "/me/calendars")
