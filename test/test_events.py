"""Tests for the time/duration parsers and event-render helpers."""

from datetime import date, datetime, timedelta

import pytest

from roxcal.events import (
    RESPONSE_SYMBOL,
    _event_date,
    fmt_event_time,
    parse_duration,
    parse_when,
    print_event_detail,
    print_events,
    print_month_grid,
    print_week_grid,
    print_week_grid_vertical,
)

# -------------------------------------------------------------- parse_when


def test_parse_when_now_is_close_to_real_now():
    before = datetime.now().astimezone()
    result = parse_when("now")
    after = datetime.now().astimezone()
    assert before <= result <= after


def test_parse_when_today_is_midnight():
    today = parse_when("today")
    now = datetime.now().astimezone()
    assert today.year == now.year
    assert today.month == now.month
    assert today.day == now.day
    assert (today.hour, today.minute, today.second) == (0, 0, 0)


def test_parse_when_tomorrow_is_next_midnight():
    tomorrow = parse_when("tomorrow")
    expected_day = (datetime.now() + timedelta(days=1)).day
    assert tomorrow.day == expected_day
    assert (tomorrow.hour, tomorrow.minute) == (0, 0)


def test_parse_when_today_with_time():
    dt = parse_when("today 14:30")
    today = datetime.now().astimezone()
    assert dt.day == today.day
    assert (dt.hour, dt.minute) == (14, 30)


def test_parse_when_tomorrow_with_time():
    dt = parse_when("tomorrow 09:15")
    expected_day = (datetime.now() + timedelta(days=1)).day
    assert dt.day == expected_day
    assert (dt.hour, dt.minute) == (9, 15)


def test_parse_when_yesterday_with_time():
    dt = parse_when("yesterday 23:00")
    expected_day = (datetime.now() - timedelta(days=1)).day
    assert dt.day == expected_day
    assert (dt.hour, dt.minute) == (23, 0)


def test_parse_when_offset_hours():
    before = datetime.now().astimezone()
    dt = parse_when("+2h")
    delta = dt - (before + timedelta(hours=2))
    assert abs(delta.total_seconds()) < 2


def test_parse_when_offset_minutes():
    before = datetime.now().astimezone()
    dt = parse_when("+30m")
    delta = dt - (before + timedelta(minutes=30))
    assert abs(delta.total_seconds()) < 2


def test_parse_when_offset_days():
    before = datetime.now().astimezone()
    dt = parse_when("+3d")
    delta = dt - (before + timedelta(days=3))
    assert abs(delta.total_seconds()) < 2


def test_parse_when_iso_with_time():
    dt = parse_when("2026-05-21 14:00")
    assert (dt.year, dt.month, dt.day) == (2026, 5, 21)
    assert (dt.hour, dt.minute) == (14, 0)


def test_parse_when_invalid_exits():
    with pytest.raises(SystemExit):
        parse_when("totally not a date")


def test_parse_when_empty_exits():
    with pytest.raises(SystemExit):
        parse_when("")


def test_parse_when_empty_with_default_returns_default():
    default = datetime(2026, 1, 1).astimezone()
    assert parse_when("", default=default) == default


# ----------------------------------------------------------- parse_duration


def test_parse_duration_minutes():
    assert parse_duration("30m") == timedelta(minutes=30)


def test_parse_duration_hours():
    assert parse_duration("1h") == timedelta(hours=1)


def test_parse_duration_combined():
    assert parse_duration("1h30m") == timedelta(hours=1, minutes=30)
    assert parse_duration("2h15m") == timedelta(hours=2, minutes=15)


def test_parse_duration_minutes_over_60():
    # 90m should equal 1h30m
    assert parse_duration("90m") == timedelta(minutes=90)


def test_parse_duration_invalid_exits():
    with pytest.raises(SystemExit):
        parse_duration("nope")


def test_parse_duration_empty_exits():
    with pytest.raises(SystemExit):
        parse_duration("")


# ----------------------------------------------------------- fmt_event_time


def test_fmt_event_time_iso_timezone():
    out = fmt_event_time("2026-05-21T14:00:00+02:00")
    assert out.startswith("2026-05-21")


def test_fmt_event_time_zulu():
    out = fmt_event_time("2026-05-21T14:00:00Z")
    # 14:00 UTC in Europe/Stockholm is 16:00 in summer time; just check the date.
    assert "2026-05-21" in out


def test_fmt_event_time_all_day_string_passthrough():
    # An "all-day" date string with no time. fromisoformat accepts plain dates
    # in 3.11+, so this returns a formatted version.
    out = fmt_event_time("2026-05-21")
    assert "2026-05-21" in out


# -------------------------------------------------------------- print helpers


def test_print_events_outputs_each_line(capsys):
    items = [
        {
            "id": "x",
            "title": "Hello",
            "start": "2026-05-21T14:00:00+02:00",
            "account": "test",
            "calendar_name": "Personal",
            "response": "accepted",
        },
        {
            "id": "y",
            "title": "World",
            "start": "2026-05-22T09:00:00+02:00",
            "account": "test",
            "calendar_name": "Personal",
            "response": "declined",
        },
    ]
    print_events(items)
    out = capsys.readouterr().out
    assert "Hello" in out
    assert "World" in out
    assert "[+]" in out
    assert "[-]" in out


def test_print_events_empty_prints_nothing(capsys):
    print_events([])
    assert capsys.readouterr().out == ""


def test_print_events_show_id_includes_id(capsys):
    items = [
        {
            "id": "abc123",
            "title": "T",
            "start": "2026-05-21T14:00:00+02:00",
            "account": "a",
            "response": "accepted",
        }
    ]
    print_events(items, show_id=True)
    assert "abc123" in capsys.readouterr().out


def test_print_event_detail_includes_attendees(capsys):
    ev = {
        "title": "Sync",
        "start": "2026-05-21T14:00:00+02:00",
        "end": "2026-05-21T14:30:00+02:00",
        "location": "Online",
        "description": "Weekly catch-up.",
        "organizer": "me@example.com",
        "attendees": [
            {"email": "a@x.com", "response": "accepted", "self": True},
            {"email": "b@x.com", "response": "needsAction", "self": False},
        ],
        "conferencing_link": "https://meet.google.com/abc",
        "html_link": "",
        "account": "work",
        "calendar": "primary",
    }
    print_event_detail(ev)
    out = capsys.readouterr().out
    assert "Sync" in out
    assert "Online" in out
    assert "a@x.com" in out
    assert "b@x.com" in out
    assert "Weekly catch-up" in out
    assert "https://meet.google.com/abc" in out


def test_response_symbol_table():
    assert RESPONSE_SYMBOL["accepted"] == "+"
    assert RESPONSE_SYMBOL["declined"] == "-"
    assert RESPONSE_SYMBOL["tentative"] == "~"
    assert RESPONSE_SYMBOL["needsAction"] == "?"
    assert RESPONSE_SYMBOL["organizer"] == "*"
    assert RESPONSE_SYMBOL[""] == " "


# --------------------------------------------------------- print_month_grid


def test_event_date_iso_with_tz():
    d = _event_date("2026-05-21T14:00:00+02:00")
    assert d.year == 2026 and d.month == 5 and d.day == 21


def test_event_date_all_day_string():
    assert _event_date("2026-05-21") == date(2026, 5, 21)


def test_event_date_invalid_returns_none():
    assert _event_date("") is None
    assert _event_date("not a date") is None


def test_print_month_grid_shows_title(capsys):
    print_month_grid([], 2026, 5)
    assert "May 2026" in capsys.readouterr().out


def test_print_month_grid_lists_days(capsys):
    print_month_grid([], 2026, 5)
    out = capsys.readouterr().out
    # All seven day-of-week headers should appear
    for h in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
        assert h in out
    # First and last day of May 2026 (1 and 31) should appear
    assert " 1 " in out or " 1\n" in out
    assert "31" in out


def test_print_month_grid_counts_events(capsys):
    events = [
        {"start": "2026-05-26T09:00:00+02:00"},
        {"start": "2026-05-26T14:00:00+02:00"},
        {"start": "2026-05-27T10:00:00+02:00"},
    ]
    print_month_grid(events, 2026, 5)
    out = capsys.readouterr().out
    assert "(2)" in out
    assert "(1)" in out


def test_print_month_grid_ignores_events_outside_month(capsys):
    events = [
        {"start": "2026-04-30T09:00:00+02:00"},
        {"start": "2026-06-01T09:00:00+02:00"},
    ]
    print_month_grid(events, 2026, 5)
    out = capsys.readouterr().out
    # No event counts at all for an empty May
    assert "(1)" not in out
    assert "(2)" not in out


def test_print_month_grid_caps_at_nine(capsys):
    events = [{"start": f"2026-05-26T0{h}:00:00+02:00"} for h in range(0, 10)] + [
        {"start": "2026-05-26T11:00:00+02:00"},
        {"start": "2026-05-26T12:00:00+02:00"},
    ]
    print_month_grid(events, 2026, 5)
    out = capsys.readouterr().out
    assert "(9+)" in out


# ---------------------------------------------------------- print_week_grid


def test_print_week_grid_title(capsys):
    print_week_grid([], date(2026, 5, 25))
    out = capsys.readouterr().out
    assert "Week of" in out
    assert "May 25 2026" in out


def test_print_week_grid_all_days_in_header(capsys):
    print_week_grid([], date(2026, 5, 25))
    out = capsys.readouterr().out
    for d in ["Mon 25", "Tue 26", "Wed 27", "Thu 28", "Fri 29", "Sat 30", "Sun 31"]:
        assert d in out


def test_print_week_grid_empty_says_no_events(capsys):
    print_week_grid([], date(2026, 5, 25))
    assert "no events" in capsys.readouterr().out


def test_print_week_grid_shows_events(capsys):
    events = [
        {"start": "2026-05-26T09:30:00+02:00", "title": "Standup"},
        {"start": "2026-05-28T14:00:00+02:00", "title": "Review"},
    ]
    print_week_grid(events, date(2026, 5, 25))
    out = capsys.readouterr().out
    assert "09:30" in out
    assert "Standup" in out
    assert "14:00" in out
    assert "Review" in out


def test_print_week_grid_truncates_long_title(capsys):
    events = [
        {
            "start": "2026-05-26T09:00:00+02:00",
            "title": "This title is way too long to fit",
        }
    ]
    print_week_grid(events, date(2026, 5, 25), width=14)
    out = capsys.readouterr().out
    # ellipsis is used when content overflows
    assert "…" in out


def test_print_week_grid_respects_width(capsys):
    events = [{"start": "2026-05-26T09:00:00+02:00", "title": "Standup"}]
    print_week_grid(events, date(2026, 5, 25), width=20)
    out = capsys.readouterr().out
    sep_line = next(line for line in out.splitlines() if line and set(line) == {"-"})
    assert len(sep_line) == 140


def test_fmt_event_time_unparseable_returns_input():
    assert fmt_event_time("not a date") == "not a date"


def test_print_event_detail_shows_html_link(capsys):
    ev = {
        "title": "T",
        "start": "2026-05-21T14:00:00+02:00",
        "end": "2026-05-21T14:30:00+02:00",
        "account": "a",
        "calendar": "c",
        "html_link": "https://calendar.google.com/event?eid=ABC",
    }
    print_event_detail(ev)
    out = capsys.readouterr().out
    assert "Link:" in out
    assert "https://calendar.google.com/event?eid=ABC" in out


def test_print_week_grid_handles_unparseable_start(capsys):
    events = [{"start": "2026-05-26 not iso", "title": "All-day"}]
    print_week_grid(events, date(2026, 5, 25))
    out = capsys.readouterr().out
    assert "all" in out


# ------------------------------------------------- print_week_grid_vertical


def test_print_week_grid_vertical_title(capsys):
    print_week_grid_vertical([], date(2026, 5, 25))
    out = capsys.readouterr().out
    assert "Week of" in out
    assert "May 25 2026" in out


def test_print_week_grid_vertical_empty_says_no_events(capsys):
    print_week_grid_vertical([], date(2026, 5, 25))
    assert "no events" in capsys.readouterr().out


def test_print_week_grid_vertical_lists_all_days(capsys):
    events = [{"start": "2026-05-26T09:00:00+02:00", "title": "Standup"}]
    print_week_grid_vertical(events, date(2026, 5, 25))
    out = capsys.readouterr().out
    for day in [
        "Mon 2026-05-25",
        "Tue 2026-05-26",
        "Wed 2026-05-27",
        "Thu 2026-05-28",
        "Fri 2026-05-29",
        "Sat 2026-05-30",
        "Sun 2026-05-31",
    ]:
        assert day in out


def test_print_week_grid_vertical_groups_events_under_day(capsys):
    events = [
        {"start": "2026-05-26T09:30:00+02:00", "title": "Standup"},
        {"start": "2026-05-26T15:00:00+02:00", "title": "Review"},
        {"start": "2026-05-28T14:00:00+02:00", "title": "Demo"},
    ]
    print_week_grid_vertical(events, date(2026, 5, 25))
    lines = capsys.readouterr().out.splitlines()
    # Standup and Review both appear after the Tue header and before Wed
    tue_idx = next(i for i, ln in enumerate(lines) if "Tue 2026-05-26" in ln)
    wed_idx = next(i for i, ln in enumerate(lines) if "Wed 2026-05-27" in ln)
    tue_block = lines[tue_idx + 1 : wed_idx]  # noqa: E203
    block = "\n".join(tue_block)
    assert "09:30" in block
    assert "Standup" in block
    assert "15:00" in block
    assert "Review" in block
    # Demo is under Thu, not Tue
    assert "Demo" not in block


def test_print_week_grid_vertical_marks_empty_day(capsys):
    events = [{"start": "2026-05-26T09:00:00+02:00", "title": "Standup"}]
    print_week_grid_vertical(events, date(2026, 5, 25))
    out = capsys.readouterr().out
    # Days without events get a dash placeholder
    assert "\n    -" in out


def test_print_week_grid_vertical_handles_unparseable_start(capsys):
    events = [{"start": "2026-05-26 not iso", "title": "All-day"}]
    print_week_grid_vertical(events, date(2026, 5, 25))
    out = capsys.readouterr().out
    assert "all" in out
    assert "All-day" in out
