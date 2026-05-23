"""Tests for the comment parameter on rsvp across backends."""

from unittest.mock import MagicMock, patch

from roxcal.backends.google_caldav import GoogleCalDAVBackend
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


def _caldav():
    return GoogleCalDAVBackend(
        Account(
            name="t",
            backend="google_caldav",
            email="me@x",
            caldav_password="p",
        )
    )


# -------------------------------- google


def test_google_rsvp_sets_comment_on_self_attendee():
    backend = _google()
    svc = MagicMock()
    svc.events.return_value.get.return_value.execute.return_value = {
        "id": "abc",
        "attendees": [
            {"email": "me@x", "self": True, "responseStatus": "needsAction"},
            {"email": "other@x", "responseStatus": "accepted"},
        ],
    }
    svc.events.return_value.patch.return_value.execute.return_value = {}
    with patch.object(backend, "_service", return_value=svc):
        backend.rsvp("abc", "declined", comment="Conflict")
    body = svc.events.return_value.patch.call_args.kwargs["body"]
    self_attendee = next(a for a in body["attendees"] if a.get("self"))
    assert self_attendee["responseStatus"] == "declined"
    assert self_attendee["comment"] == "Conflict"


def test_google_rsvp_clears_previous_comment_when_empty():
    backend = _google()
    svc = MagicMock()
    svc.events.return_value.get.return_value.execute.return_value = {
        "id": "abc",
        "attendees": [
            {
                "email": "me@x",
                "self": True,
                "responseStatus": "declined",
                "comment": "old",
            }
        ],
    }
    svc.events.return_value.patch.return_value.execute.return_value = {}
    with patch.object(backend, "_service", return_value=svc):
        backend.rsvp("abc", "accepted")
    body = svc.events.return_value.patch.call_args.kwargs["body"]
    self_attendee = next(a for a in body["attendees"] if a.get("self"))
    assert self_attendee["responseStatus"] == "accepted"
    assert "comment" not in self_attendee


# -------------------------------- microsoft


def test_ms_rsvp_includes_comment_in_post_body():
    backend = _ms()
    api = MagicMock()
    with patch.object(backend, "_api", api):
        backend.rsvp("abc", "declined", comment="No room")
    method, path = api.call_args.args
    body = api.call_args.kwargs["json"]
    assert method == "POST"
    assert path == "/me/events/abc/decline"
    assert body["comment"] == "No room"
    assert body["sendResponse"] is True


def test_ms_rsvp_no_comment_omits_field():
    backend = _ms()
    api = MagicMock()
    with patch.object(backend, "_api", api):
        backend.rsvp("abc", "accepted")
    body = api.call_args.kwargs["json"]
    assert "comment" not in body


# -------------------------------- caldav (ignored, but warns)


def test_caldav_rsvp_warns_on_comment(capsys):
    backend = _caldav()
    # Stub the inner workings so the call only exercises the comment branch.
    with patch.object(backend, "_calendar_obj") as cal_obj:
        cal_obj.return_value.event_by_uid.side_effect = Exception("stop")
        try:
            backend.rsvp("evt", "declined", comment="Sorry")
        except Exception:
            pass
    err = capsys.readouterr().err
    assert "CalDAV does not transmit response comments" in err
