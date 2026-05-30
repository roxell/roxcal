"""Tests for the CLI argument parser. Subcommand handlers are not invoked
because they hit external APIs; we test only that parsing succeeds and
yields the expected attributes."""

import pytest

from roxcal.cli import build_parser, resolve_account
from roxcal.config import Account, Config


def _parser():
    return build_parser()


def test_all_subcommands_registered():
    parser = _parser()
    subparsers = next(a for a in parser._actions if hasattr(a, "choices") and a.choices)
    expected = {"init", "list", "agenda", "add", "rsvp", "show", "delete"}
    assert expected.issubset(set(subparsers.choices.keys()))


def test_account_flag():
    args = _parser().parse_args(["--account", "work", "agenda"])
    assert args.account == "work"
    assert args.cmd == "agenda"


def test_agenda_default_days():
    args = _parser().parse_args(["agenda"])
    assert args.days == 7


def test_agenda_custom_days():
    args = _parser().parse_args(["agenda", "-D", "14"])
    assert args.days == 14


def test_agenda_calendar_repeatable():
    args = _parser().parse_args(["agenda", "-c", "a", "-c", "b"])
    assert args.calendar == ["a", "b"]


def test_agenda_all_flag():
    args = _parser().parse_args(["agenda", "--all"])
    assert args.all is True
    assert args.all_calendars is False


def test_agenda_all_calendars_flag():
    args = _parser().parse_args(["agenda", "--all-calendars"])
    assert args.all_calendars is True


def test_agenda_json_flag():
    args = _parser().parse_args(["agenda", "--json"])
    assert args.json is True


def test_agenda_compact_default_false():
    args = _parser().parse_args(["agenda"])
    assert args.compact is False


def test_agenda_compact_flag():
    args = _parser().parse_args(["agenda", "--compact"])
    assert args.compact is True


def test_add_requires_title_and_when():
    parser = _parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["add"])
    with pytest.raises(SystemExit):
        parser.parse_args(["add", "--title", "x"])


def test_add_full():
    args = _parser().parse_args(
        [
            "add",
            "--title",
            "T",
            "--when",
            "tomorrow 10:00",
            "--duration",
            "45m",
            "--attendees",
            "a@x,b@x",
            "--meet",
            "--where",
            "Online",
            "--description",
            "body",
        ]
    )
    assert args.title == "T"
    assert args.when == "tomorrow 10:00"
    assert args.duration == "45m"
    assert args.attendees == "a@x,b@x"
    assert args.meet is True
    assert args.where == "Online"
    assert args.description == "body"


def test_rsvp_requires_event_id_and_response():
    parser = _parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["rsvp"])
    with pytest.raises(SystemExit):
        parser.parse_args(["rsvp", "abc"])


def test_rsvp_choices_enforced():
    parser = _parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["rsvp", "abc", "nope"])


def test_rsvp_valid():
    args = _parser().parse_args(["rsvp", "abc", "accepted"])
    assert args.event_id == "abc"
    assert args.response == "accepted"
    assert args.comment is None


def test_rsvp_with_comment():
    args = _parser().parse_args(["rsvp", "abc", "declined", "--comment", "Conflict"])
    assert args.comment == "Conflict"


def test_rsvp_with_short_comment_flag():
    args = _parser().parse_args(["rsvp", "abc", "tentative", "-m", "Maybe"])
    assert args.comment == "Maybe"


def test_show_requires_event_id():
    parser = _parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["show"])


def test_show_with_calendar():
    args = _parser().parse_args(["show", "abc", "-c", "primary"])
    assert args.event_id == "abc"
    assert args.calendar == "primary"


def test_delete_requires_event_id():
    parser = _parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["delete"])


def test_init_port_default_zero():
    args = _parser().parse_args(["init"])
    assert args.port == 0


def test_init_port_custom():
    args = _parser().parse_args(["init", "--port", "8085"])
    assert args.port == 8085


def test_quick_requires_text():
    parser = _parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["quick"])


def test_quick_text():
    args = _parser().parse_args(["quick", "Lunch with Maria tomorrow 12:30"])
    assert args.text == "Lunch with Maria tomorrow 12:30"
    assert args.calendar is None


def test_quick_with_calendar():
    args = _parser().parse_args(["quick", "Lunch", "-c", "anders@x.com"])
    assert args.text == "Lunch"
    assert args.calendar == "anders@x.com"


def test_calm_default_month():
    args = _parser().parse_args(["calm"])
    assert args.month is None


def test_calm_explicit_month():
    args = _parser().parse_args(["calm", "2026-05"])
    assert args.month == "2026-05"


def test_calm_with_calendar_filter():
    args = _parser().parse_args(["calm", "-c", "a", "-c", "b"])
    assert args.calendar == ["a", "b"]


def test_calm_all_accounts():
    args = _parser().parse_args(["calm", "--all"])
    assert args.all is True


def test_resolve_month_current_when_none():
    from datetime import datetime

    from roxcal.cli import _resolve_month

    y, m = _resolve_month(None)
    now = datetime.now()
    assert (y, m) == (now.year, now.month)


def test_resolve_month_parses_yyyy_mm():
    from roxcal.cli import _resolve_month

    assert _resolve_month("2026-05") == (2026, 5)
    assert _resolve_month("2027-12") == (2027, 12)


def test_resolve_month_invalid_format_exits():
    from roxcal.cli import _resolve_month

    with pytest.raises(SystemExit):
        _resolve_month("not-a-month")


def test_resolve_month_out_of_range_exits():
    from roxcal.cli import _resolve_month

    with pytest.raises(SystemExit):
        _resolve_month("2026-13")
    with pytest.raises(SystemExit):
        _resolve_month("2026-0")


def test_calw_default_args():
    args = _parser().parse_args(["calw"])
    assert args.start is None
    assert args.width == 14
    assert args.all is False


def test_calw_with_start_and_width():
    args = _parser().parse_args(["calw", "2026-05-25", "--width", "20"])
    assert args.start == "2026-05-25"
    assert args.width == 20


def test_calw_calendar_repeatable():
    args = _parser().parse_args(["calw", "-c", "a", "-c", "b"])
    assert args.calendar == ["a", "b"]


def test_calw_vertical_default_false():
    args = _parser().parse_args(["calw"])
    assert args.vertical is False


def test_calw_vertical_flag():
    args = _parser().parse_args(["calw", "--vertical"])
    assert args.vertical is True


def test_week_start_default_is_monday_of_current_week():
    from datetime import date, timedelta

    from roxcal.cli import _week_start

    today = date.today()
    expected = today - timedelta(days=today.weekday())
    assert _week_start(None) == expected
    assert _week_start(None).weekday() == 0  # Monday


def test_week_start_with_iso_date_returns_that_week_monday():
    from datetime import date

    from roxcal.cli import _week_start

    # Wed 2026-05-27 -> Mon 2026-05-25
    assert _week_start("2026-05-27") == date(2026, 5, 25)


def test_week_start_with_keyword_today():
    from datetime import date, timedelta

    from roxcal.cli import _week_start

    today = date.today()
    expected = today - timedelta(days=today.weekday())
    assert _week_start("today") == expected


def test_edit_requires_event_id():
    parser = _parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["edit"])


def test_edit_parses_all_flags():
    args = _parser().parse_args(
        [
            "edit",
            "abc",
            "--title",
            "New",
            "--when",
            "tomorrow 14:00",
            "--duration",
            "1h",
            "--attendees",
            "a@x,b@x",
            "--where",
            "Online",
            "--description",
            "body",
        ]
    )
    assert args.event_id == "abc"
    assert args.title == "New"
    assert args.when == "tomorrow 14:00"
    assert args.duration == "1h"
    assert args.attendees == "a@x,b@x"
    assert args.where == "Online"
    assert args.description == "body"


def test_edit_with_no_flags_id_only():
    args = _parser().parse_args(["edit", "abc"])
    assert args.event_id == "abc"
    assert args.title is None
    assert args.when is None
    assert args.duration is None


def test_resolve_account_uses_default():
    cfg = Config(
        default_account="a",
        accounts={"a": Account(name="a", backend="google_oauth")},
    )
    acc = resolve_account(cfg, None)
    assert acc.name == "a"


def test_resolve_account_explicit():
    cfg = Config(
        default_account="a",
        accounts={
            "a": Account(name="a", backend="google_oauth"),
            "b": Account(name="b", backend="google_oauth"),
        },
    )
    acc = resolve_account(cfg, "b")
    assert acc.name == "b"


def test_resolve_account_unknown_exits():
    cfg = Config(
        default_account="a",
        accounts={"a": Account(name="a", backend="google_oauth")},
    )
    with pytest.raises(SystemExit):
        resolve_account(cfg, "no-such-account")


def test_remind_requires_minutes():
    parser = _parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["remind"])


def test_remind_minutes_only():
    args = _parser().parse_args(["remind", "10"])
    assert args.minutes == 10
    assert args.template is None
    assert args.dry_run is False
    assert args.all is False


def test_remind_with_template_and_dry_run():
    args = _parser().parse_args(
        ["remind", "5", 'notify-send "{title}" "{start}"', "--dry-run"]
    )
    assert args.minutes == 5
    assert args.template == 'notify-send "{title}" "{start}"'
    assert args.dry_run is True


def test_conflicts_default_args():
    args = _parser().parse_args(["conflicts"])
    assert args.start is None
    assert args.end is None
    assert args.days == 7
    assert args.all is False
    assert args.skip_all_day is False


def test_conflicts_with_range_and_flags():
    args = _parser().parse_args(
        ["conflicts", "2026-05-23", "2026-05-25", "--all", "--skip-all-day"]
    )
    assert args.start == "2026-05-23"
    assert args.end == "2026-05-25"
    assert args.all is True
    assert args.skip_all_day is True


def test_conflicts_json_flag():
    args = _parser().parse_args(["conflicts", "--json"])
    assert args.json is True


def test_search_requires_query():
    parser = _parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["search"])


def test_search_query_only():
    args = _parser().parse_args(["search", "standup"])
    assert args.query == "standup"
    assert args.start is None
    assert args.end is None
    assert args.days == 365
    assert args.all is False


def test_search_full():
    args = _parser().parse_args(
        ["search", "lunch", "2026-01-01", "2026-12-31", "--all", "--json"]
    )
    assert args.query == "lunch"
    assert args.start == "2026-01-01"
    assert args.end == "2026-12-31"
    assert args.all is True
    assert args.json is True


def test_import_requires_file():
    parser = _parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["import"])


def test_import_with_file_and_flags():
    args = _parser().parse_args(
        ["import", "/tmp/x.ics", "--calendar", "work", "--with-attendees", "-n"]
    )
    assert args.file == "/tmp/x.ics"
    assert args.calendar == "work"
    assert args.with_attendees is True
    assert args.dry_run is True
    assert args.notify is False
