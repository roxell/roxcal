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
    cmd_colors,
    cmd_conflicts,
    cmd_delete,
    cmd_edit,
    cmd_import,
    cmd_init,
    cmd_list,
    cmd_quick,
    cmd_remind,
    cmd_rsvp,
    cmd_search,
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


# ---------- cmd_remind


def _remind_args(**overrides):
    base = dict(
        account=None,
        minutes=10,
        template=None,
        calendar=None,
        all=False,
        all_calendars=False,
        dry_run=False,
    )
    base.update(overrides)
    return Namespace(**base)


def _future_iso(minutes_ahead: int) -> str:
    dt = datetime.now().astimezone() + timedelta(minutes=minutes_ahead)
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z")


def test_cmd_remind_no_template_prints_upcoming(capsys):
    backend = MagicMock()
    backend.list_events.return_value = iter(
        [{"start": _future_iso(5), "title": "Standup", "account": "a"}]
    )
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_remind(_remind_args(), _cfg())
    out = capsys.readouterr().out
    assert "Standup" in out


def test_cmd_remind_no_template_silent_when_no_events(capsys):
    backend = MagicMock()
    backend.list_events.return_value = iter([])
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_remind(_remind_args(), _cfg())
    assert capsys.readouterr().out == ""


def test_cmd_remind_template_runs_command():
    backend = MagicMock()
    backend.list_events.return_value = iter(
        [{"start": _future_iso(5), "title": "Standup", "account": "a"}]
    )
    with (
        patch.object(cli_mod, "make_backend", return_value=backend),
        patch.object(cli_mod.subprocess, "run") as mock_run,
    ):
        cmd_remind(
            _remind_args(template='notify-send "{title}" "{start}"'),
            _cfg(),
        )
    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert call_args[0] == "notify-send"
    assert call_args[1] == "Standup"
    # call_args[2] is the HH:MM start time -- just check format roughly
    assert ":" in call_args[2]


def test_cmd_remind_dry_run_prints_command(capsys):
    backend = MagicMock()
    backend.list_events.return_value = iter(
        [{"start": _future_iso(5), "title": "Standup", "account": "a"}]
    )
    with (
        patch.object(cli_mod, "make_backend", return_value=backend),
        patch.object(cli_mod.subprocess, "run") as mock_run,
    ):
        cmd_remind(
            _remind_args(template='notify-send "{title}"', dry_run=True),
            _cfg(),
        )
    mock_run.assert_not_called()
    out = capsys.readouterr().out
    assert "notify-send" in out
    assert "Standup" in out


def test_cmd_remind_unknown_placeholder_exits():
    backend = MagicMock()
    backend.list_events.return_value = iter(
        [{"start": _future_iso(5), "title": "T", "account": "a"}]
    )
    with patch.object(cli_mod, "make_backend", return_value=backend):
        with pytest.raises(SystemExit):
            cmd_remind(_remind_args(template="echo {nope}"), _cfg())


def test_cmd_remind_window_passed_to_backend():
    backend = MagicMock()
    backend.list_events.return_value = iter([])
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_remind(_remind_args(minutes=7), _cfg())
    start_dt, end_dt = backend.list_events.call_args.args[:2]
    delta = end_dt - start_dt
    # Allow a few seconds of jitter from the now() call inside cmd_remind.
    assert abs(delta.total_seconds() - 7 * 60) < 5


def test_cmd_remind_empty_template_exits():
    backend = MagicMock()
    backend.list_events.return_value = iter(
        [{"start": _future_iso(5), "title": "T", "account": "a"}]
    )
    with patch.object(cli_mod, "make_backend", return_value=backend):
        with pytest.raises(SystemExit):
            cmd_remind(_remind_args(template="   "), _cfg())


def test_cmd_remind_skips_events_started_in_past(capsys):
    """All-day or in-progress events overlap the window but did not just
    start, so remind must not notify for them."""
    backend = MagicMock()
    backend.list_events.return_value = iter(
        [
            {"start": _future_iso(-30), "title": "Sunrise/Sunset", "account": "a"},
            {"start": _future_iso(5), "title": "Standup", "account": "a"},
        ]
    )
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_remind(_remind_args(), _cfg())
    out = capsys.readouterr().out
    assert "Sunrise" not in out
    assert "Standup" in out


def test_cmd_remind_skips_events_after_window(capsys):
    backend = MagicMock()
    backend.list_events.return_value = iter(
        [
            {"start": _future_iso(60), "title": "Far future", "account": "a"},
            {"start": _future_iso(5), "title": "Soon", "account": "a"},
        ]
    )
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_remind(_remind_args(), _cfg())
    out = capsys.readouterr().out
    assert "Far future" not in out
    assert "Soon" in out


def test_cmd_remind_template_does_not_fire_for_past_events():
    backend = MagicMock()
    backend.list_events.return_value = iter(
        [{"start": _future_iso(-10), "title": "Started already", "account": "a"}]
    )
    with (
        patch.object(cli_mod, "make_backend", return_value=backend),
        patch.object(cli_mod.subprocess, "run") as mock_run,
    ):
        cmd_remind(_remind_args(template='notify-send "{title}"'), _cfg())
    mock_run.assert_not_called()


def test_cmd_remind_lower_bound_exclusive(capsys):
    """An event whose start exactly equals 'now' should not fire — it
    fired on the previous tick whose upper bound was 'now'."""
    now_iso = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    backend = MagicMock()
    backend.list_events.return_value = iter(
        [{"start": now_iso, "title": "Just starting", "account": "a"}]
    )
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_remind(_remind_args(), _cfg())
    assert "Just starting" not in capsys.readouterr().out


# ---------- cmd_colors


def test_cmd_colors_emits_json(capsys):
    cfg = _cfg()
    cfg.color_overrides = {"accepted": "bright_green", "declined": 196}
    cmd_colors(Namespace(), cfg)
    out = capsys.readouterr().out
    assert _json.loads(out) == {"accepted": "bright_green", "declined": 196}


def test_cmd_colors_empty_when_no_overrides(capsys):
    cmd_colors(Namespace(), _cfg())
    assert _json.loads(capsys.readouterr().out) == {}


# ---------- cmd_conflicts


def _conflicts_args(**overrides):
    base = dict(
        account=None,
        start="2026-05-23",
        end=None,
        days=7,
        calendar=None,
        all=False,
        all_calendars=False,
        skip_all_day=False,
    )
    base.update(overrides)
    return Namespace(**base)


def _ev(start, end, title, **extra):
    base = {"start": start, "end": end, "title": title, "account": "a"}
    base.update(extra)
    return base


def _run_conflicts(events, capsys, **arg_overrides) -> str:
    backend = MagicMock()
    backend.list_events.return_value = iter(events)
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_conflicts(_conflicts_args(**arg_overrides), _cfg())
    return capsys.readouterr().out


def test_cmd_conflicts_no_events_no_output(capsys):
    assert _run_conflicts([], capsys) == ""


def test_cmd_conflicts_single_event_no_output(capsys):
    out = _run_conflicts(
        [_ev("2026-05-23T10:00:00+02:00", "2026-05-23T11:00:00+02:00", "Alone")],
        capsys,
    )
    assert out == ""


def test_cmd_conflicts_back_to_back_not_a_conflict(capsys):
    out = _run_conflicts(
        [
            _ev("2026-05-23T10:00:00+02:00", "2026-05-23T11:00:00+02:00", "A"),
            _ev("2026-05-23T11:00:00+02:00", "2026-05-23T12:00:00+02:00", "B"),
        ],
        capsys,
    )
    assert out == ""


def test_cmd_conflicts_two_overlapping(capsys):
    out = _run_conflicts(
        [
            _ev("2026-05-23T10:00:00+02:00", "2026-05-23T11:00:00+02:00", "Standup"),
            _ev("2026-05-23T10:30:00+02:00", "2026-05-23T11:30:00+02:00", "Sync"),
        ],
        capsys,
    )
    assert "Overlap" in out
    assert "Standup" in out
    assert "Sync" in out


def test_cmd_conflicts_cluster_of_three(capsys):
    out = _run_conflicts(
        [
            _ev("2026-05-23T10:00:00+02:00", "2026-05-23T11:30:00+02:00", "A"),
            _ev("2026-05-23T10:30:00+02:00", "2026-05-23T11:00:00+02:00", "B"),
            _ev("2026-05-23T11:00:00+02:00", "2026-05-23T12:00:00+02:00", "C"),
        ],
        capsys,
    )
    assert out.count("Overlap") == 1
    for title in ("A", "B", "C"):
        assert title in out


def test_cmd_conflicts_skips_declined(capsys):
    out = _run_conflicts(
        [
            _ev(
                "2026-05-23T10:00:00+02:00",
                "2026-05-23T11:00:00+02:00",
                "Mine",
                response="accepted",
            ),
            _ev(
                "2026-05-23T10:30:00+02:00",
                "2026-05-23T11:30:00+02:00",
                "DontCare",
                response="declined",
            ),
        ],
        capsys,
    )
    assert out == ""


def test_cmd_conflicts_all_day_flagged_by_default(capsys):
    out = _run_conflicts(
        [
            _ev("2026-05-23", "2026-05-24", "OOO"),
            _ev("2026-05-23T10:00:00+02:00", "2026-05-23T11:00:00+02:00", "Standup"),
        ],
        capsys,
    )
    assert "OOO" in out
    assert "Standup" in out


def test_cmd_conflicts_skip_all_day_flag(capsys):
    out = _run_conflicts(
        [
            _ev("2026-05-23", "2026-05-24", "OOO"),
            _ev("2026-05-23T10:00:00+02:00", "2026-05-23T11:00:00+02:00", "Standup"),
        ],
        capsys,
        skip_all_day=True,
    )
    assert out == ""


def test_cmd_conflicts_two_clusters_blank_line_between(capsys):
    out = _run_conflicts(
        [
            _ev("2026-05-23T10:00:00+02:00", "2026-05-23T11:00:00+02:00", "A1"),
            _ev("2026-05-23T10:30:00+02:00", "2026-05-23T11:00:00+02:00", "A2"),
            _ev("2026-05-23T14:00:00+02:00", "2026-05-23T15:00:00+02:00", "B1"),
            _ev("2026-05-23T14:30:00+02:00", "2026-05-23T15:30:00+02:00", "B2"),
        ],
        capsys,
    )
    assert out.count("Overlap") == 2
    assert "A1" in out and "A2" in out
    assert "B1" in out and "B2" in out


# ---------- cmd_search


def _search_args(**overrides):
    base = dict(
        account=None,
        query="standup",
        start=None,
        end=None,
        days=365,
        calendar=None,
        all=False,
        all_calendars=False,
        ids=False,
        compact=False,
        json=False,
    )
    base.update(overrides)
    return Namespace(**base)


def test_cmd_search_calls_backend_search(capsys):
    backend = MagicMock()
    backend.search.return_value = iter(
        [
            {
                "start": "2026-05-21T14:00:00+02:00",
                "title": "Standup",
                "id": "x",
                "account": "a",
            }
        ]
    )
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_search(_search_args(), _cfg())
    backend.search.assert_called_once()
    assert backend.search.call_args.args[0] == "standup"
    assert "Standup" in capsys.readouterr().out


def test_cmd_search_default_window_is_days_back_and_forward():
    backend = MagicMock()
    backend.search.return_value = iter([])
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_search(_search_args(days=30), _cfg())
    _, start_dt, end_dt = backend.search.call_args.args[:3]
    span = end_dt - start_dt
    assert abs(span.days - 60) <= 1


def test_cmd_search_json_output(capsys):
    backend = MagicMock()
    backend.search.return_value = iter(
        [{"start": "2026-05-21T14:00:00+02:00", "title": "X", "id": "1"}]
    )
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_search(_search_args(json=True), _cfg())
    data = _json.loads(capsys.readouterr().out)
    assert data[0]["title"] == "X"


# ---------- cmd_import


_ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:1@test
SUMMARY:Standup
DTSTART:20260530T080000Z
DTEND:20260530T083000Z
LOCATION:Online
DESCRIPTION:Daily standup
ORGANIZER:mailto:lead@example.com
ATTENDEE;CN=Maria:mailto:maria@example.com
ATTENDEE;CN=Peter:mailto:peter@example.com
END:VEVENT
END:VCALENDAR
"""


def _import_args(file, **overrides):
    base = dict(
        account=None,
        file=file,
        calendar=None,
        with_attendees=False,
        notify=False,
        dry_run=False,
    )
    base.update(overrides)
    return Namespace(**base)


def _write_ics(tmp_path, body=_ICS):
    path = tmp_path / "invite.ics"
    path.write_bytes(body)
    return str(path)


def test_cmd_import_creates_event(tmp_path):
    path = _write_ics(tmp_path)
    backend = MagicMock()
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_import(_import_args(path), _cfg())
    backend.create_event.assert_called_once()
    kwargs = backend.create_event.call_args.kwargs
    assert kwargs["title"] == "Standup"
    assert kwargs["location"] == "Online"
    # Default: attendees moved to description, not re-invited.
    assert kwargs["attendees"] == []
    assert "maria@example.com" in kwargs["description"]
    assert "peter@example.com" in kwargs["description"]


def test_cmd_import_with_attendees_reinvites(tmp_path):
    path = _write_ics(tmp_path)
    backend = MagicMock()
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_import(_import_args(path, with_attendees=True), _cfg())
    kwargs = backend.create_event.call_args.kwargs
    assert set(kwargs["attendees"]) == {"maria@example.com", "peter@example.com"}


def test_cmd_import_dry_run_does_not_call_backend(tmp_path, capsys):
    path = _write_ics(tmp_path)
    backend = MagicMock()
    with patch.object(cli_mod, "make_backend", return_value=backend):
        cmd_import(_import_args(path, dry_run=True), _cfg())
    backend.create_event.assert_not_called()
    out = capsys.readouterr().out
    assert "Would import: Standup" in out


def test_cmd_import_missing_file_exits(tmp_path):
    with pytest.raises(SystemExit):
        cmd_import(_import_args(str(tmp_path / "nope.ics")), _cfg())


def test_cmd_import_invalid_ics_exits(tmp_path):
    path = tmp_path / "bad.ics"
    path.write_bytes(b"this is not an ics file at all")
    with pytest.raises(SystemExit):
        cmd_import(_import_args(str(path)), _cfg())


def test_cmd_import_calls_notify_send_when_flag_set(tmp_path):
    path = _write_ics(tmp_path)
    backend = MagicMock()
    with (
        patch.object(cli_mod, "make_backend", return_value=backend),
        patch.object(cli_mod.subprocess, "run") as mock_run,
    ):
        cmd_import(_import_args(path, notify=True), _cfg())
    assert mock_run.called
    call_args = mock_run.call_args[0][0]
    assert call_args[0] == "notify-send"
    assert "Standup" in call_args[2]


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
