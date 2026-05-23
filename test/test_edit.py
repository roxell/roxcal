"""Tests for the update_event backend method and the edit CLI subcommand."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from roxcal.backends.google_oauth import GoogleOAuthBackend
from roxcal.backends.microsoft_graph import MicrosoftGraphBackend
from roxcal.config import Account


def _google():
    return GoogleOAuthBackend(
        Account(name="t", backend="google_oauth", email="me@x", client_id="i")
    )


def test_google_update_event_patches_only_supplied_fields():
    backend = _google()
    svc = MagicMock()
    svc.events.return_value.patch.return_value.execute.return_value = {
        "id": "abc",
        "htmlLink": "https://x/abc",
    }
    with patch.object(backend, "_service", return_value=svc):
        backend.update_event("abc", title="New title")
    call = svc.events.return_value.patch.call_args
    assert call.kwargs["calendarId"] == "primary"
    assert call.kwargs["eventId"] == "abc"
    assert call.kwargs["sendUpdates"] == "all"
    assert call.kwargs["body"] == {"summary": "New title"}


def test_google_update_event_full_patch():
    backend = _google()
    svc = MagicMock()
    svc.events.return_value.patch.return_value.execute.return_value = {
        "id": "abc",
        "htmlLink": "x",
    }
    start = datetime(2026, 6, 1, 10, 0, 0).astimezone()
    end = datetime(2026, 6, 1, 11, 0, 0).astimezone()
    with patch.object(backend, "_service", return_value=svc):
        backend.update_event(
            "abc",
            calendar="cal@x",
            title="T",
            start=start,
            end=end,
            attendees=["a@x", "b@x"],
            location="Room 3",
            description="body",
        )
    body = svc.events.return_value.patch.call_args.kwargs["body"]
    assert body["summary"] == "T"
    assert body["start"] == {"dateTime": start.isoformat()}
    assert body["end"] == {"dateTime": end.isoformat()}
    assert body["location"] == "Room 3"
    assert body["description"] == "body"
    assert body["attendees"] == [{"email": "a@x"}, {"email": "b@x"}]


def test_google_update_event_no_fields_is_noop(capsys):
    backend = _google()
    svc = MagicMock()
    with patch.object(backend, "_service", return_value=svc):
        backend.update_event("abc")
    svc.events.return_value.patch.assert_not_called()
    assert "no changes" in capsys.readouterr().out


def test_microsoft_update_event_patches():
    backend = MicrosoftGraphBackend(
        Account(name="t", backend="microsoft_graph", client_id="x")
    )
    api = MagicMock(return_value={"id": "abc", "webLink": "x"})
    with patch.object(backend, "_api", api):
        backend.update_event("abc", title="New", description="body")
    method, path = api.call_args.args
    body = api.call_args.kwargs["json"]
    assert method == "PATCH"
    assert path == "/me/events/abc"
    assert body["subject"] == "New"
    assert body["body"] == {"contentType": "text", "content": "body"}


def test_base_update_event_raises():
    from roxcal.backends import Backend

    b = Backend(Account(name="t", backend="google_oauth"))
    with pytest.raises(NotImplementedError):
        b.update_event("abc", title="x")
