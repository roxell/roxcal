"""RSVP on an event where you are not an attendee should explain why.

Subscribed info calendars (sunrise/sunset, holidays) give events with no
invite for you. RSVP can never work there. The error must say that, not
just "not an attendee".
"""

from unittest.mock import MagicMock, patch

import pytest

from roxcal.backends.google_caldav import GoogleCalDAVBackend
from roxcal.backends.google_oauth import GoogleOAuthBackend
from roxcal.config import Account


def _google():
    return GoogleOAuthBackend(
        Account(name="t", backend="google_oauth", email="me@x", client_id="i")
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


def test_google_rsvp_not_attendee_explains(capsys):
    backend = _google()
    svc = MagicMock()
    svc.events.return_value.get.return_value.execute.return_value = {
        "id": "sunrise-1",
        "attendees": [{"email": "other@x", "responseStatus": "accepted"}],
    }
    with patch.object(backend, "_service", return_value=svc):
        with pytest.raises(SystemExit):
            backend.rsvp("sunrise-1", "accepted", calendar="cal")
    err = capsys.readouterr().err
    assert "RSVP does not apply" in err
    # No patch should be sent when RSVP can not work.
    svc.events.return_value.patch.assert_not_called()


def test_caldav_rsvp_not_attendee_explains(capsys):
    backend = _caldav()
    ics = (
        "BEGIN:VCALENDAR\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:sunrise-1\r\n"
        "ATTENDEE:mailto:other@x\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    ev = MagicMock()
    ev.data = ics
    with patch.object(backend, "_calendar_obj") as cal_obj:
        cal_obj.return_value.event_by_uid.return_value = ev
        with pytest.raises(SystemExit):
            backend.rsvp("sunrise-1", "accepted")
    err = capsys.readouterr().err
    assert "RSVP does not apply" in err
    ev.save.assert_not_called()
