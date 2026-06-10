"""Tests for the reminder_minutes option on create_event and update_event."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from roxcal.backends.google_oauth import GoogleOAuthBackend
from roxcal.backends.outlook import OutlookBackend
from roxcal.config import Account


def _google():
    return GoogleOAuthBackend(
        Account(name="t", backend="google_oauth", email="me@x", client_id="i")
    )


def _ms():
    return OutlookBackend(Account(name="t", backend="outlook", client_id="x"))


# ---------------- google_oauth create_event reminder


def test_google_create_default_reminder_is_10():
    backend = _google()
    svc = MagicMock()
    svc.events.return_value.insert.return_value.execute.return_value = {"id": "x"}
    start = datetime(2026, 6, 1, 10, 0, 0).astimezone()
    end = datetime(2026, 6, 1, 11, 0, 0).astimezone()
    with patch.object(backend, "_service", return_value=svc):
        backend.create_event(title="T", start=start, end=end)
    body = svc.events.return_value.insert.call_args.kwargs["body"]
    assert body["reminders"] == {
        "useDefault": False,
        "overrides": [{"method": "popup", "minutes": 10}],
    }


def test_google_create_custom_reminder():
    backend = _google()
    svc = MagicMock()
    svc.events.return_value.insert.return_value.execute.return_value = {"id": "x"}
    start = datetime(2026, 6, 1, 10, 0, 0).astimezone()
    end = datetime(2026, 6, 1, 11, 0, 0).astimezone()
    with patch.object(backend, "_service", return_value=svc):
        backend.create_event(title="T", start=start, end=end, reminder_minutes=30)
    body = svc.events.return_value.insert.call_args.kwargs["body"]
    assert body["reminders"]["overrides"] == [{"method": "popup", "minutes": 30}]


def test_google_create_no_reminder():
    backend = _google()
    svc = MagicMock()
    svc.events.return_value.insert.return_value.execute.return_value = {"id": "x"}
    start = datetime(2026, 6, 1, 10, 0, 0).astimezone()
    end = datetime(2026, 6, 1, 11, 0, 0).astimezone()
    with patch.object(backend, "_service", return_value=svc):
        backend.create_event(title="T", start=start, end=end, reminder_minutes=0)
    body = svc.events.return_value.insert.call_args.kwargs["body"]
    assert body["reminders"] == {"useDefault": False, "overrides": []}


# ---------------- google_oauth update_event reminder


def test_google_update_reminder_only():
    backend = _google()
    svc = MagicMock()
    svc.events.return_value.patch.return_value.execute.return_value = {"id": "x"}
    with patch.object(backend, "_service", return_value=svc):
        backend.update_event("evt", reminder_minutes=20)
    body = svc.events.return_value.patch.call_args.kwargs["body"]
    assert body == {
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": 20}],
        }
    }


def test_google_update_disable_reminder():
    backend = _google()
    svc = MagicMock()
    svc.events.return_value.patch.return_value.execute.return_value = {"id": "x"}
    with patch.object(backend, "_service", return_value=svc):
        backend.update_event("evt", reminder_minutes=0)
    body = svc.events.return_value.patch.call_args.kwargs["body"]
    assert body["reminders"]["overrides"] == []


# ---------------- outlook reminder


def test_ms_create_default_reminder():
    backend = _ms()
    start = datetime(2026, 6, 1, 10, 0, 0).astimezone()
    end = datetime(2026, 6, 1, 11, 0, 0).astimezone()
    api = MagicMock(return_value={"id": "x"})
    with patch.object(backend, "_api", api):
        backend.create_event(title="T", start=start, end=end)
    body = api.call_args.kwargs["json"]
    assert body["isReminderOn"] is True
    assert body["reminderMinutesBeforeStart"] == 10


def test_ms_create_custom_reminder():
    backend = _ms()
    start = datetime(2026, 6, 1, 10, 0, 0).astimezone()
    end = datetime(2026, 6, 1, 11, 0, 0).astimezone()
    api = MagicMock(return_value={"id": "x"})
    with patch.object(backend, "_api", api):
        backend.create_event(title="T", start=start, end=end, reminder_minutes=45)
    body = api.call_args.kwargs["json"]
    assert body["reminderMinutesBeforeStart"] == 45


def test_ms_create_no_reminder():
    backend = _ms()
    start = datetime(2026, 6, 1, 10, 0, 0).astimezone()
    end = datetime(2026, 6, 1, 11, 0, 0).astimezone()
    api = MagicMock(return_value={"id": "x"})
    with patch.object(backend, "_api", api):
        backend.create_event(title="T", start=start, end=end, reminder_minutes=0)
    body = api.call_args.kwargs["json"]
    assert body["isReminderOn"] is False


def test_ms_update_reminder():
    backend = _ms()
    api = MagicMock(return_value={"id": "x"})
    with patch.object(backend, "_api", api):
        backend.update_event("evt", reminder_minutes=15)
    body = api.call_args.kwargs["json"]
    assert body["isReminderOn"] is True
    assert body["reminderMinutesBeforeStart"] == 15


# ---------------- CLI parsing


def test_cli_add_default_reminder_is_10():
    from roxcal.cli import build_parser

    args = build_parser().parse_args(["add", "--title", "T", "--when", "now"])
    assert args.reminder == 10


def test_cli_add_custom_reminder():
    from roxcal.cli import build_parser

    args = build_parser().parse_args(
        ["add", "--title", "T", "--when", "now", "--reminder", "30"]
    )
    assert args.reminder == 30


def test_cli_add_no_reminder():
    from roxcal.cli import build_parser

    args = build_parser().parse_args(
        ["add", "--title", "T", "--when", "now", "--reminder", "0"]
    )
    assert args.reminder == 0


def test_cli_edit_reminder_default_is_none():
    from roxcal.cli import build_parser

    args = build_parser().parse_args(["edit", "abc"])
    assert args.reminder is None


def test_cli_edit_reminder_explicit():
    from roxcal.cli import build_parser

    args = build_parser().parse_args(["edit", "abc", "--reminder", "20"])
    assert args.reminder == 20


def test_cli_reminder_accepts_minutes_suffix():
    from roxcal.cli import build_parser

    args = build_parser().parse_args(
        ["add", "--title", "T", "--when", "now", "--reminder", "10m"]
    )
    assert args.reminder == 10


def test_cli_reminder_accepts_hours():
    from roxcal.cli import build_parser

    args = build_parser().parse_args(
        ["add", "--title", "T", "--when", "now", "--reminder", "1h"]
    )
    assert args.reminder == 60


def test_cli_reminder_accepts_days():
    from roxcal.cli import build_parser

    args = build_parser().parse_args(
        ["add", "--title", "T", "--when", "now", "--reminder", "1d"]
    )
    assert args.reminder == 24 * 60


def test_cli_reminder_accepts_combined():
    from roxcal.cli import build_parser

    args = build_parser().parse_args(
        ["add", "--title", "T", "--when", "now", "--reminder", "1d2h30m"]
    )
    assert args.reminder == 24 * 60 + 2 * 60 + 30


def test_cli_reminder_rejects_garbage():
    import pytest

    from roxcal.cli import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["add", "--title", "T", "--when", "now", "--reminder", "bogus"]
        )


# ---------------- print_event_detail reminder line


def test_print_event_detail_shows_reminder(capsys):
    from roxcal.events import print_event_detail

    ev = {
        "title": "T",
        "start": "2026-05-21T14:00:00+02:00",
        "end": "2026-05-21T14:30:00+02:00",
        "account": "a",
        "calendar": "c",
        "reminder_minutes": 15,
    }
    print_event_detail(ev)
    out = capsys.readouterr().out
    assert "Reminder:" in out
    assert "15 min" in out


def test_print_event_detail_shows_no_reminder(capsys):
    from roxcal.events import print_event_detail

    ev = {
        "title": "T",
        "start": "2026-05-21T14:00:00+02:00",
        "end": "2026-05-21T14:30:00+02:00",
        "account": "a",
        "calendar": "c",
        "reminder_minutes": 0,
    }
    print_event_detail(ev)
    out = capsys.readouterr().out
    assert "Reminder:" in out
    assert "none" in out


def test_print_event_detail_omits_reminder_when_unknown(capsys):
    from roxcal.events import print_event_detail

    ev = {
        "title": "T",
        "start": "2026-05-21T14:00:00+02:00",
        "end": "2026-05-21T14:30:00+02:00",
        "account": "a",
        "calendar": "c",
        # no reminder_minutes
    }
    print_event_detail(ev)
    out = capsys.readouterr().out
    assert "Reminder:" not in out
