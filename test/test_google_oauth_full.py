"""Mocked unit tests for GoogleOAuthBackend.

The tests patch out _service, _load_creds, _save_creds and the OAuth flow,
so no live Google API call is made. They cover every public method plus
the credential loading / token refresh / OAuth bootstrap branches.
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from roxcal.backends.google_oauth import GoogleOAuthBackend
from roxcal.config import Account


def _backend(**overrides):
    defaults = {
        "name": "t",
        "backend": "google_oauth",
        "email": "me@example.com",
        "client_id": "cid",
        "client_secret": "csec",
    }
    defaults.update(overrides)
    return GoogleOAuthBackend(Account(**defaults))


def _http_error(status):
    err = MagicMock()
    err.resp.status = status
    return err


def _http_error_class():
    from googleapiclient.errors import HttpError

    return HttpError


def _make_http_error(status):
    cls = _http_error_class()
    resp = MagicMock()
    resp.status = status
    return cls(resp, b"")


# ---------- _token_path / _load_creds / _save_creds


def test_token_path_uses_account_name(tmp_path, monkeypatch):
    import roxcal.backends.google_oauth as g

    monkeypatch.setattr(g, "GCALCLI_TOKEN_ROOT", tmp_path)
    backend = _backend(name="acct1")
    assert backend._token_path() == tmp_path / "acct1" / "oauth_creds"


def test_load_creds_returns_none_when_missing(tmp_path, monkeypatch):
    import roxcal.backends.google_oauth as g

    monkeypatch.setattr(g, "GCALCLI_TOKEN_ROOT", tmp_path)
    backend = _backend(name="acct1")
    assert backend._load_creds() is None


def test_load_creds_reads_token_file(tmp_path, monkeypatch):
    import roxcal.backends.google_oauth as g

    monkeypatch.setattr(g, "GCALCLI_TOKEN_ROOT", tmp_path)
    backend = _backend(name="acct1")
    path = backend._token_path()
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "token": "tok",
                "refresh_token": "ref",
                "client_id": "cid",
                "client_secret": "cs",
                "scopes": ["https://example/scope"],
            }
        )
    )
    creds = backend._load_creds()
    assert creds is not None
    assert creds.token == "tok"


def test_save_creds_writes_mode_600(tmp_path, monkeypatch):
    import roxcal.backends.google_oauth as g

    monkeypatch.setattr(g, "GCALCLI_TOKEN_ROOT", tmp_path)
    backend = _backend(name="acct1")
    fake = MagicMock()
    fake.to_json.return_value = "{}"
    backend._save_creds(fake)
    path = backend._token_path()
    assert path.exists()
    assert path.stat().st_mode & 0o777 == 0o600


# ---------- _service


def test_service_dies_when_no_token():
    backend = _backend()
    with patch.object(backend, "_load_creds", return_value=None):
        with pytest.raises(SystemExit):
            backend._service()


def test_service_refreshes_expired_token():
    backend = _backend()
    creds = MagicMock()
    creds.valid = False
    creds.refresh_token = "ref"
    fake_service = MagicMock()
    with (
        patch.object(backend, "_load_creds", return_value=creds),
        patch.object(backend, "_save_creds"),
        patch("googleapiclient.discovery.build", return_value=fake_service) as build,
    ):
        result = backend._service()
    creds.refresh.assert_called_once()
    build.assert_called_once()
    assert result is fake_service


def test_service_dies_when_invalid_and_no_refresh_token():
    backend = _backend()
    creds = MagicMock()
    creds.valid = False
    creds.refresh_token = None
    with patch.object(backend, "_load_creds", return_value=creds):
        with pytest.raises(SystemExit):
            backend._service()


# ---------- init (OAuth flow)


def test_init_dies_when_missing_client_id():
    backend = _backend(client_id="")
    with pytest.raises(SystemExit):
        backend.init()


def test_init_runs_oauth_and_saves(capsys):
    backend = _backend()
    flow = MagicMock()
    creds = MagicMock()
    flow.run_local_server.return_value = creds
    with (
        patch(
            "google_auth_oauthlib.flow.InstalledAppFlow.from_client_config",
            return_value=flow,
        ),
        patch.object(backend, "_save_creds") as save,
    ):
        backend.init(port=8085)
    flow.run_local_server.assert_called_once_with(port=8085, open_browser=True)
    save.assert_called_once_with(creds)
    assert "Saved token" in capsys.readouterr().out


# ---------- list_calendars


def test_list_calendars_prints_with_primary_marker(capsys):
    backend = _backend()
    svc = MagicMock()
    svc.calendarList.return_value.list.return_value.execute.return_value = {
        "items": [
            {"id": "primary", "summary": "Main", "primary": True},
            {"id": "extra@x", "summary": "Other"},
        ]
    }
    with patch.object(backend, "_service", return_value=svc):
        backend.list_calendars()
    out = capsys.readouterr().out
    assert "primary" in out
    assert "Main *" in out
    assert "extra@x" in out
    assert "Other" in out


# ---------- list_events


def _events_response(items):
    return {"items": items}


def test_list_events_yields_basic_fields():
    backend = _backend()
    svc = MagicMock()
    svc.events.return_value.list.return_value.execute.return_value = _events_response(
        [
            {
                "id": "e1",
                "summary": "T1",
                "start": {"dateTime": "2026-05-21T14:00:00Z"},
                "end": {"dateTime": "2026-05-21T15:00:00Z"},
                "location": "Room",
            }
        ]
    )
    with (
        patch.object(backend, "_service", return_value=svc),
        patch.object(
            backend,
            "_calendar_list",
            return_value={"primary": "Primary"},
        ),
    ):
        events = list(
            backend.list_events(
                datetime(2026, 5, 21, 0, 0).astimezone(),
                datetime(2026, 5, 22, 0, 0).astimezone(),
            )
        )
    assert len(events) == 1
    ev = events[0]
    assert ev["id"] == "e1"
    assert ev["title"] == "T1"
    assert ev["calendar"] == "primary"
    assert ev["calendar_name"] == "Primary"
    assert ev["location"] == "Room"


def test_list_events_response_from_self_attendee():
    backend = _backend()
    svc = MagicMock()
    svc.events.return_value.list.return_value.execute.return_value = _events_response(
        [
            {
                "id": "e1",
                "summary": "T",
                "start": {"dateTime": "2026-05-21T14:00:00Z"},
                "end": {"dateTime": "2026-05-21T15:00:00Z"},
                "attendees": [
                    {"email": "other@x", "responseStatus": "accepted"},
                    {"self": True, "responseStatus": "tentative"},
                ],
            }
        ]
    )
    with (
        patch.object(backend, "_service", return_value=svc),
        patch.object(backend, "_calendar_list", return_value={"primary": "P"}),
    ):
        ev = next(
            backend.list_events(
                datetime(2026, 5, 21).astimezone(),
                datetime(2026, 5, 22).astimezone(),
            )
        )
    assert ev["response"] == "tentative"


def test_list_events_response_from_email_fallback():
    backend = _backend(email="me@x")
    svc = MagicMock()
    svc.events.return_value.list.return_value.execute.return_value = _events_response(
        [
            {
                "id": "e1",
                "summary": "T",
                "start": {"dateTime": "2026-05-21T14:00:00Z"},
                "end": {"dateTime": "2026-05-21T15:00:00Z"},
                "attendees": [
                    {"email": "ME@X", "responseStatus": "declined"},
                ],
            }
        ]
    )
    with (
        patch.object(backend, "_service", return_value=svc),
        patch.object(backend, "_calendar_list", return_value={"primary": "P"}),
    ):
        ev = next(
            backend.list_events(
                datetime(2026, 5, 21).astimezone(),
                datetime(2026, 5, 22).astimezone(),
            )
        )
    assert ev["response"] == "declined"


def test_list_events_response_organizer():
    backend = _backend()
    svc = MagicMock()
    svc.events.return_value.list.return_value.execute.return_value = _events_response(
        [
            {
                "id": "e1",
                "summary": "T",
                "start": {"dateTime": "2026-05-21T14:00:00Z"},
                "end": {"dateTime": "2026-05-21T15:00:00Z"},
                "organizer": {"self": True},
            }
        ]
    )
    with (
        patch.object(backend, "_service", return_value=svc),
        patch.object(backend, "_calendar_list", return_value={"primary": "P"}),
    ):
        ev = next(
            backend.list_events(
                datetime(2026, 5, 21).astimezone(),
                datetime(2026, 5, 22).astimezone(),
            )
        )
    assert ev["response"] == "organizer"


def test_list_events_all_day_uses_date_field():
    backend = _backend()
    svc = MagicMock()
    svc.events.return_value.list.return_value.execute.return_value = _events_response(
        [
            {
                "id": "e1",
                "summary": "All",
                "start": {"date": "2026-05-21"},
                "end": {"date": "2026-05-22"},
            }
        ]
    )
    with (
        patch.object(backend, "_service", return_value=svc),
        patch.object(backend, "_calendar_list", return_value={"primary": "P"}),
    ):
        ev = next(
            backend.list_events(
                datetime(2026, 5, 21).astimezone(),
                datetime(2026, 5, 22).astimezone(),
            )
        )
    assert ev["start"] == "2026-05-21"
    assert ev["end"] == "2026-05-22"


# ---------- create_event


def test_create_event_minimal(capsys):
    backend = _backend()
    svc = MagicMock()
    svc.events.return_value.insert.return_value.execute.return_value = {
        "id": "e1",
        "htmlLink": "https://x/e1",
    }
    start = datetime(2026, 6, 1, 10, 0).astimezone()
    end = datetime(2026, 6, 1, 11, 0).astimezone()
    with patch.object(backend, "_service", return_value=svc):
        backend.create_event(title="T", start=start, end=end)
    body = svc.events.return_value.insert.call_args.kwargs["body"]
    assert body["summary"] == "T"
    assert "description" not in body
    assert "location" not in body
    assert "attendees" not in body
    assert "conferenceData" not in body
    assert "https://x/e1" in capsys.readouterr().out


def test_create_event_with_description_and_location():
    backend = _backend()
    svc = MagicMock()
    svc.events.return_value.insert.return_value.execute.return_value = {"id": "e1"}
    start = datetime(2026, 6, 1, 10, 0).astimezone()
    end = datetime(2026, 6, 1, 11, 0).astimezone()
    with patch.object(backend, "_service", return_value=svc):
        backend.create_event(
            title="T",
            start=start,
            end=end,
            description="body",
            location="Online",
        )
    body = svc.events.return_value.insert.call_args.kwargs["body"]
    assert body["description"] == "body"
    assert body["location"] == "Online"


def test_create_event_with_attendees():
    backend = _backend()
    svc = MagicMock()
    svc.events.return_value.insert.return_value.execute.return_value = {"id": "e1"}
    start = datetime(2026, 6, 1, 10, 0).astimezone()
    end = datetime(2026, 6, 1, 11, 0).astimezone()
    with patch.object(backend, "_service", return_value=svc):
        backend.create_event(
            title="T",
            start=start,
            end=end,
            attendees=["a@x", "b@x"],
        )
    body = svc.events.return_value.insert.call_args.kwargs["body"]
    assert body["attendees"] == [{"email": "a@x"}, {"email": "b@x"}]


def test_create_event_with_conferencing(capsys):
    backend = _backend()
    svc = MagicMock()
    svc.events.return_value.insert.return_value.execute.return_value = {
        "id": "e1",
        "hangoutLink": "https://meet.google.com/abc",
    }
    start = datetime(2026, 6, 1, 10, 0).astimezone()
    end = datetime(2026, 6, 1, 11, 0).astimezone()
    with patch.object(backend, "_service", return_value=svc):
        backend.create_event(title="T", start=start, end=end, conferencing=True)
    call = svc.events.return_value.insert.call_args
    assert call.kwargs["conferenceDataVersion"] == 1
    body = call.kwargs["body"]
    assert body["conferenceData"]["createRequest"]["conferenceSolutionKey"] == {
        "type": "hangoutsMeet"
    }
    out = capsys.readouterr().out
    assert "Meet:" in out
    assert "https://meet.google.com/abc" in out


# ---------- rsvp


def test_rsvp_dies_when_user_not_attendee():
    backend = _backend(email="me@x")
    svc = MagicMock()
    svc.events.return_value.get.return_value.execute.return_value = {
        "id": "abc",
        "attendees": [{"email": "someoneelse@x"}],
    }
    with patch.object(backend, "_service", return_value=svc):
        with pytest.raises(SystemExit):
            backend.rsvp("abc", "declined")


# ---------- delete_event


def test_delete_event(capsys):
    backend = _backend()
    svc = MagicMock()
    with patch.object(backend, "_service", return_value=svc):
        backend.delete_event("abc")
    svc.events.return_value.delete.assert_called_once_with(
        calendarId="primary", eventId="abc", sendUpdates="all"
    )
    assert "Deleted event abc" in capsys.readouterr().out


# ---------- get_event


def test_get_event_with_explicit_calendar():
    backend = _backend(email="me@x")
    svc = MagicMock()
    svc.events.return_value.get.return_value.execute.return_value = {
        "id": "abc",
        "summary": "T",
        "start": {"dateTime": "2026-05-21T14:00:00Z"},
        "end": {"dateTime": "2026-05-21T15:00:00Z"},
        "attendees": [{"email": "me@x", "responseStatus": "accepted"}],
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": 30}],
        },
    }
    with patch.object(backend, "_service", return_value=svc):
        result = backend.get_event("abc", calendar="cal@x")
    assert result["id"] == "abc"
    assert result["reminder_minutes"] == 30
    assert result["attendees"][0]["self"] is True


def test_get_event_searches_calendars_on_404():
    backend = _backend()
    svc = MagicMock()

    call_count = {"n": 0}

    def get_side_effect(calendarId, eventId):
        call_count["n"] += 1
        mock = MagicMock()
        if calendarId == "good@x":
            mock.execute.return_value = {
                "id": eventId,
                "summary": "T",
                "start": {"dateTime": "2026-05-21T14:00:00Z"},
                "end": {"dateTime": "2026-05-21T15:00:00Z"},
            }
        else:
            mock.execute.side_effect = _make_http_error(404)
        return mock

    svc.events.return_value.get.side_effect = get_side_effect
    with (
        patch.object(backend, "_service", return_value=svc),
        patch.object(
            backend,
            "_calendar_list",
            return_value={"good@x": "Good"},
        ),
    ):
        result = backend.get_event("evt123")
    assert result["id"] == "evt123"
    assert result["calendar"] == "good@x"


def test_get_event_propagates_non_404_http_error():
    backend = _backend()
    svc = MagicMock()
    svc.events.return_value.get.return_value.execute.side_effect = _make_http_error(500)
    with (
        patch.object(backend, "_service", return_value=svc),
        patch.object(backend, "_calendar_list", return_value={}),
    ):
        with pytest.raises(Exception):
            backend.get_event("evt", calendar="cal@x")


def test_get_event_dies_when_not_found():
    backend = _backend()
    svc = MagicMock()
    svc.events.return_value.get.return_value.execute.side_effect = _make_http_error(404)
    with (
        patch.object(backend, "_service", return_value=svc),
        patch.object(backend, "_calendar_list", return_value={}),
    ):
        with pytest.raises(SystemExit):
            backend.get_event("nope")


def test_get_event_reminder_use_default_returns_none():
    backend = _backend(email="me@x")
    svc = MagicMock()
    svc.events.return_value.get.return_value.execute.return_value = {
        "id": "abc",
        "summary": "T",
        "start": {"dateTime": "2026-05-21T14:00:00Z"},
        "end": {"dateTime": "2026-05-21T15:00:00Z"},
        "reminders": {"useDefault": True},
    }
    with patch.object(backend, "_service", return_value=svc):
        result = backend.get_event("abc", calendar="cal@x")
    assert result["reminder_minutes"] is None


def test_get_event_reminder_no_popup_override_returns_zero():
    backend = _backend(email="me@x")
    svc = MagicMock()
    svc.events.return_value.get.return_value.execute.return_value = {
        "id": "abc",
        "summary": "T",
        "start": {"dateTime": "2026-05-21T14:00:00Z"},
        "end": {"dateTime": "2026-05-21T15:00:00Z"},
        "reminders": {"useDefault": False, "overrides": []},
    }
    with patch.object(backend, "_service", return_value=svc):
        result = backend.get_event("abc", calendar="cal@x")
    assert result["reminder_minutes"] == 0
