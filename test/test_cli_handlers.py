"""Tests for the cmd_* dispatch handlers in roxcal/cli.py.

make_backend is patched to a MagicMock so no backend code runs.
"""

import json as _json
from argparse import Namespace
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from roxcal import cli as cli_mod
from roxcal.cli import (
    _collect_events,
    _resolve_month,
    _split_calendars,
    cmd_add,
    cmd_agenda,
    cmd_calm,
    cmd_calw,
    cmd_delete,
    cmd_edit,
    cmd_init,
    cmd_list,
    cmd_quick,
    cmd_rsvp,
    cmd_show,
    main,
)
from roxcal.config import Account, Config


def _cfg(account_name="a"):
    return Config(
        default_account=account_name,
        accounts={account_name: Account(name=account_name, backend="google_oauth")},
    )


def _two_account_cfg():
    return Config(
        default_account="a",
        accounts={
            "a": Account(name="a", backend="google_oauth"),
            "b": Account(name="b", backend="google_oauth"),
        },
    )


# ---------- helpers


def test_split_calendars_none_input():
    assert _split_calendars(None) is None


def test_split_calendars_empty_list():
    assert _split_calendars([]) is None


def test_split_calendars_blanks_only():
    assert _split_calendars(["", " ", ","]) is None


def test_split_calendars_flattens():
    assert _split_calendars(["a,b", "c", "  d "]) == ["a", "b", "c", "d"]


# ---------- _collect_events


def test_collect_events_single_account_uses_resolve():
    cfg = _cfg()
    args = Namespace(account=None, calendar=None, all=False, all_calendars=False)
    backend = MagicMock()
    backend.list_events.return_value = iter(
        [
            {"start": "2026-05-22T10:00", "title": "B"},
            {"start": "2026-05-21T10:00", "title": "A"},
        ]
    )
    with patch.object(cli_mod, "make_backend", return_value=backend):
        items = _collect_events(
            args,
            cfg,
            datetime(2026, 5, 21).astimezone(),
            datetime(2026, 5, 23).astimezone(),
        )
    assert [e["title"] for e in items] == ["A", "B"]


def test_collect_events_all_iterates_all_accounts(capsys):
    cfg = _two_account_cfg()
    args = Namespace(account=None, calendar=None, all=True, all_calendars=False)

    def mk(account):
        backend = MagicMock()
        backend.list_events.return_value = iter(
            [{"start": "2026-05-21T10:00", "title": account.name}]
        )
        return backend

    with patch.object(cli_mod, "make_backend", side_effect=mk):
        items = _collect_events(
            args,
            cfg,
            datetime(2026, 5, 21).astimezone(),
            datetime(2026, 5, 23).astimezone(),
        )
    assert sorted(e["title"] for e in items) == ["a", "b"]


def test_collect_events_all_skips_unauth(capsys):
    cfg = _two_account_cfg()
    args = Namespace(account=None, calendar=None, all=True, all_calendars=False)

    def mk(account):
        backend = MagicMock()
        if account.name == "a":
            backend.list_events.side_effect = SystemExit(1)
        else:
            backend.list_events.return_value = iter(
                [{"start": "2026-05-21T10:00", "title": "B"}]
            )
        return backend

    with patch.object(cli_mod, "make_backend", side_effect=mk):
        items = _collect_events(
            args,
            cfg,
            datetime(2026, 5, 21).astimezone(),
            datetime(2026, 5, 23).astimezone(),
        )
    assert [e["title"] for e in items] == ["B"]
    assert "[a] skipped" in capsys.readouterr().out


# ---------- cmd_init / cmd_list


def test_cmd_init_dispatches():
    backend = MagicMock()
    args = Namespace(account="a", port=8085)
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_init(args, _cfg())
    backend.init.assert_called_once_with(port=8085)


def test_cmd_list_dispatches():
    backend = MagicMock()
    args = Namespace(account="a")
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_list(args, _cfg())
    backend.list_calendars.assert_called_once()


# ---------- cmd_agenda


def _agenda_args(**overrides):
    base = dict(
        account=None,
        start=None,
        end=None,
        days=7,
        calendar=None,
        all=False,
        all_calendars=False,
        ids=False,
        compact=False,
        json=False,
    )
    base.update(overrides)
    return Namespace(**base)


def test_cmd_agenda_default_window(capsys):
    backend = MagicMock()
    backend.list_events.return_value = iter([])
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_agenda(_agenda_args(), _cfg())
    call = backend.list_events.call_args
    start_dt = call.args[0]
    end_dt = call.args[1]
    assert (end_dt - start_dt) == timedelta(days=7)


def test_cmd_agenda_with_explicit_start_end():
    backend = MagicMock()
    backend.list_events.return_value = iter([])
    args = _agenda_args(start="2026-05-21", end="2026-05-25")
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_agenda(args, _cfg())
    start_dt, end_dt = backend.list_events.call_args.args[:2]
    assert start_dt.date() == date(2026, 5, 21)
    assert end_dt.date() == date(2026, 5, 25)


def test_cmd_agenda_json_output(capsys):
    backend = MagicMock()
    backend.list_events.return_value = iter(
        [
            {
                "start": "2026-05-21T14:00:00+02:00",
                "title": "T",
                "id": "x",
                "account": "a",
            }
        ]
    )
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_agenda(_agenda_args(json=True), _cfg())
    out = capsys.readouterr().out
    data = _json.loads(out)
    assert data[0]["title"] == "T"


def test_cmd_agenda_prints_lines(capsys):
    backend = MagicMock()
    backend.list_events.return_value = iter(
        [
            {
                "start": "2026-05-21T14:00:00+02:00",
                "title": "Hello",
                "id": "x",
                "account": "a",
                "response": "accepted",
            }
        ]
    )
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_agenda(_agenda_args(), _cfg())
    assert "Hello" in capsys.readouterr().out


def test_cmd_agenda_config_color_always_emits_ansi(capsys):
    """config.color = 'always' -> output is colored."""
    backend = MagicMock()
    backend.list_events.return_value = iter(
        [
            {
                "start": "2026-05-21T14:00:00+02:00",
                "title": "Standup",
                "id": "x",
                "account": "a",
                "response": "accepted",
            }
        ]
    )
    cfg = _cfg()
    cfg.color = "always"
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_agenda(_agenda_args(), cfg)
    out = capsys.readouterr().out
    assert "\033[32m" in out


def test_cmd_agenda_config_color_never_has_no_ansi(capsys):
    backend = MagicMock()
    backend.list_events.return_value = iter(
        [
            {
                "start": "2026-05-21T14:00:00+02:00",
                "title": "Standup",
                "id": "x",
                "account": "ms",
                "response": "accepted",
            }
        ]
    )
    cfg = _cfg()
    cfg.color = "never"
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_agenda(_agenda_args(), cfg)
    out = capsys.readouterr().out
    assert "\033[" not in out


def test_cmd_agenda_compact_drops_account_and_calendar(capsys):
    backend = MagicMock()
    backend.list_events.return_value = iter(
        [
            {
                "start": "2026-05-21T14:00:00+02:00",
                "title": "Standup",
                "id": "x",
                "account": "ms",
                "calendar_name": "Work",
                "response": "accepted",
            }
        ]
    )
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_agenda(_agenda_args(compact=True), _cfg())
    out = capsys.readouterr().out
    assert "[+]" in out
    assert "Standup" in out
    assert "[ms]" not in out
    assert "[Work]" not in out


# ---------- cmd_add / cmd_rsvp / cmd_show / cmd_delete / cmd_quick


def test_cmd_add():
    backend = MagicMock()
    args = Namespace(
        account=None,
        title="T",
        when="2026-05-21 14:00",
        duration="1h",
        attendees="a@x,b@x",
        meet=True,
        calendar="primary",
        description="body",
        where="Online",
        reminder=15,
    )
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_add(args, _cfg())
    backend.create_event.assert_called_once()
    kwargs = backend.create_event.call_args.kwargs
    assert kwargs["title"] == "T"
    assert kwargs["attendees"] == ["a@x", "b@x"]
    assert kwargs["conferencing"] is True
    assert kwargs["reminder_minutes"] == 15


def test_cmd_add_no_attendees():
    backend = MagicMock()
    args = Namespace(
        account=None,
        title="T",
        when="2026-05-21 14:00",
        duration="30m",
        attendees=None,
        meet=False,
        calendar=None,
        description="",
        where="",
        reminder=10,
    )
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_add(args, _cfg())
    assert backend.create_event.call_args.kwargs["attendees"] == []


def test_cmd_rsvp():
    backend = MagicMock()
    args = Namespace(
        account=None,
        event_id="abc",
        response="declined",
        calendar="cal",
        comment="Sorry",
    )
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_rsvp(args, _cfg())
    backend.rsvp.assert_called_once_with(
        "abc", "declined", calendar="cal", comment="Sorry"
    )


def test_cmd_rsvp_no_comment_passes_empty_string():
    backend = MagicMock()
    args = Namespace(
        account=None, event_id="abc", response="accepted", calendar=None, comment=None
    )
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_rsvp(args, _cfg())
    backend.rsvp.assert_called_once_with("abc", "accepted", calendar=None, comment="")


def test_cmd_show_formatted(capsys):
    backend = MagicMock()
    backend.get_event.return_value = {
        "title": "T",
        "start": "2026-05-21T14:00:00+02:00",
        "end": "2026-05-21T15:00:00+02:00",
        "account": "a",
        "calendar": "c",
    }
    args = Namespace(account=None, event_id="abc", calendar=None, json=False)
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_show(args, _cfg())
    assert "T" in capsys.readouterr().out


def test_cmd_show_json(capsys):
    backend = MagicMock()
    backend.get_event.return_value = {
        "title": "T",
        "start": "2026-05-21T14:00:00+02:00",
    }
    args = Namespace(account=None, event_id="abc", calendar=None, json=True)
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_show(args, _cfg())
    data = _json.loads(capsys.readouterr().out)
    assert data["title"] == "T"


def test_cmd_delete():
    backend = MagicMock()
    args = Namespace(account=None, event_id="abc", calendar="cal")
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_delete(args, _cfg())
    backend.delete_event.assert_called_once_with("abc", calendar="cal")


def test_cmd_quick():
    backend = MagicMock()
    args = Namespace(account=None, text="Lunch tomorrow", calendar="cal")
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_quick(args, _cfg())
    backend.quick_add.assert_called_once_with("Lunch tomorrow", calendar="cal")


# ---------- cmd_edit


def _edit_args(**overrides):
    base = dict(
        account=None,
        event_id="abc",
        calendar=None,
        title=None,
        when=None,
        duration=None,
        attendees=None,
        where=None,
        description=None,
        reminder=None,
    )
    base.update(overrides)
    return Namespace(**base)


def test_cmd_edit_title_only():
    backend = MagicMock()
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_edit(_edit_args(title="New"), _cfg())
    backend.update_event.assert_called_once()
    kwargs = backend.update_event.call_args.kwargs
    assert kwargs == {"calendar": None, "title": "New"}


def test_cmd_edit_all_fields():
    backend = MagicMock()
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_edit(
            _edit_args(
                title="New",
                when="2026-06-01 14:00",
                duration="1h",
                attendees="a@x,b@x",
                where="Online",
                description="body",
                reminder=20,
            ),
            _cfg(),
        )
    kwargs = backend.update_event.call_args.kwargs
    assert kwargs["title"] == "New"
    assert kwargs["attendees"] == ["a@x", "b@x"]
    assert kwargs["location"] == "Online"
    assert kwargs["description"] == "body"
    assert kwargs["reminder_minutes"] == 20
    assert kwargs["start"].hour == 14
    assert (kwargs["end"] - kwargs["start"]) == timedelta(hours=1)


def test_cmd_edit_when_without_duration_preserves_length():
    backend = MagicMock()
    backend.get_event.return_value = {
        "start": "2026-05-21T14:00:00+00:00",
        "end": "2026-05-21T15:30:00+00:00",
    }
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_edit(_edit_args(when="2026-06-01 10:00"), _cfg())
    kwargs = backend.update_event.call_args.kwargs
    assert (kwargs["end"] - kwargs["start"]) == timedelta(minutes=90)


def test_cmd_edit_duration_without_when_uses_existing_start():
    backend = MagicMock()
    backend.get_event.return_value = {
        "start": "2026-05-21T14:00:00+00:00",
        "end": "2026-05-21T15:00:00+00:00",
    }
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_edit(_edit_args(duration="2h"), _cfg())
    kwargs = backend.update_event.call_args.kwargs
    assert kwargs["start"].hour == 14
    assert (kwargs["end"] - kwargs["start"]) == timedelta(hours=2)


def test_cmd_edit_nothing_dies():
    backend = MagicMock()
    with patch.object(cli_mod, "make_backend", return_value=backend):
        with pytest.raises(SystemExit):
            cmd_edit(_edit_args(), _cfg())
    backend.update_event.assert_not_called()


# ---------- cmd_calm


def _calm_args(**overrides):
    base = dict(
        account=None,
        month=None,
        calendar=None,
        all=False,
        all_calendars=False,
    )
    base.update(overrides)
    return Namespace(**base)


def test_cmd_calm_renders(capsys):
    backend = MagicMock()
    backend.list_events.return_value = iter([])
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_calm(_calm_args(month="2026-05"), _cfg())
    out = capsys.readouterr().out
    assert "May 2026" in out


def test_resolve_month_with_keyword_now_uses_today():
    y, m = _resolve_month(None)
    now = datetime.now()
    assert (y, m) == (now.year, now.month)


# ---------- cmd_calw


def _calw_args(**overrides):
    base = dict(
        account=None,
        start=None,
        width=14,
        vertical=False,
        calendar=None,
        all=False,
        all_calendars=False,
    )
    base.update(overrides)
    return Namespace(**base)


def test_cmd_calw_renders(capsys):
    backend = MagicMock()
    backend.list_events.return_value = iter([])
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_calw(_calw_args(start="2026-05-25"), _cfg())
    out = capsys.readouterr().out
    assert "Week of" in out


def test_cmd_calw_keyword_start():
    backend = MagicMock()
    backend.list_events.return_value = iter([])
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_calw(_calw_args(start="tomorrow"), _cfg())
    args_passed = backend.list_events.call_args
    assert args_passed.args[0].weekday() == 0  # Monday


def test_cmd_calw_vertical_uses_vertical_printer(capsys):
    backend = MagicMock()
    backend.list_events.return_value = iter(
        [{"start": "2026-05-26T09:00:00+02:00", "title": "Standup"}]
    )
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_calw(_calw_args(start="2026-05-25", vertical=True), _cfg())
    out = capsys.readouterr().out
    # Vertical layout puts the YYYY-MM-DD into each day header.
    assert "Tue 2026-05-26" in out
    # And the horizontal "----..." separator row never appears.
    assert "--------------" not in out


def test_cmd_calw_config_color_is_used(capsys):
    backend = MagicMock()
    backend.list_events.return_value = iter(
        [
            {
                "start": "2026-05-26T09:00:00+02:00",
                "title": "Standup",
                "response": "accepted",
            }
        ]
    )
    cfg = _cfg()
    cfg.color = "always"
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_calw(_calw_args(start="2026-05-25"), cfg)
    out = capsys.readouterr().out
    assert "\033[32m" in out


def test_cmd_calw_vertical_config_color_is_used(capsys):
    backend = MagicMock()
    backend.list_events.return_value = iter(
        [
            {
                "start": "2026-05-26T09:00:00+02:00",
                "title": "Standup",
                "response": "tentative",
            }
        ]
    )
    cfg = _cfg()
    cfg.color = "always"
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_calw(_calw_args(start="2026-05-25", vertical=True), cfg)
    out = capsys.readouterr().out
    assert "\033[33m" in out


# ---------- main


def test_main_dispatches_to_subcommand_handler(monkeypatch):
    backend = MagicMock()
    backend.list_calendars = MagicMock()
    monkeypatch.setattr("sys.argv", ["roxcal", "list"])
    with (
        patch.object(cli_mod, "make_backend", return_value=backend),
        patch.object(cli_mod, "load_config", return_value=_cfg()),
    ):
        main()
    backend.list_calendars.assert_called_once()
