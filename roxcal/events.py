"""Time parsing, duration parsing, and event rendering helpers."""

from __future__ import annotations

import calendar as _calendar
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

from .config import die

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

ANSI_COLOR = {
    "accepted": "\033[32m",
    "declined": "\033[31m",
    "tentative": "\033[33m",
    "needsAction": "\033[36m",
    "organizer": "\033[35m",
}
ANSI_RESET = "\033[0m"


def _should_color(mode: str) -> bool:
    """Decide whether to emit ANSI color escapes.

    'never' off, 'always' on. 'auto' is on only when stdout is a TTY and
    the NO_COLOR env var is unset (https://no-color.org).
    """
    if mode == "never":
        return False
    if mode == "always":
        return True
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def parse_when(s: str, default: datetime | None = None) -> datetime:
    """Parse a date/time string. Accepts ISO, common date formats, and a few
    keywords (today, tomorrow, now, +<n>{d,h,m})."""
    s = s.strip().lower() if s else ""
    if not s:
        if default is not None:
            return default
        die("empty date/time")
    now = datetime.now().astimezone()
    if s == "now":
        return now
    if s == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if s == "tomorrow":
        return (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    m = re.fullmatch(r"(today|tomorrow|yesterday)\s+(\d{1,2}):(\d{2})", s)
    if m:
        hh, mm = int(m.group(2)), int(m.group(3))
        base = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if m.group(1) == "tomorrow":
            base += timedelta(days=1)
        elif m.group(1) == "yesterday":
            base -= timedelta(days=1)
        return base
    m = re.fullmatch(r"\+(\d+)([dhm])", s)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        delta = {
            "d": timedelta(days=n),
            "h": timedelta(hours=n),
            "m": timedelta(minutes=n),
        }[unit]
        return now + delta
    from dateutil import parser as dtparser

    try:
        dt = dtparser.parse(s)
    except (ValueError, OverflowError):
        die(f"could not parse time '{s}'")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=now.tzinfo)
    return dt


def parse_duration(s: str) -> timedelta:
    """Parse '30m', '1h', '90m', '2h30m'."""
    s = s.strip().lower()
    total = timedelta()
    for n, unit in re.findall(r"(\d+)([hm])", s):
        n = int(n)
        total += timedelta(hours=n) if unit == "h" else timedelta(minutes=n)
    if total == timedelta():
        die(f"could not parse duration '{s}' (try 30m, 1h, 2h30m)")
    return total


def fmt_event_time(iso: str) -> str:
    """Render an ISO time stamp short. Falls back to the raw string for all-day."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


RESPONSE_SYMBOL = {
    "accepted": "+",
    "declined": "-",
    "tentative": "~",
    "needsAction": "?",
    "organizer": "*",
    "": " ",
}


def print_event_detail(ev: dict) -> None:
    """Print the full detail dict produced by Backend.get_event()."""
    start = fmt_event_time(ev.get("start", ""))
    end = fmt_event_time(ev.get("end", ""))
    print(f"{ev.get('title', '(no title)')}")
    print(f"  When:        {start}  ->  {end}")
    if ev.get("location"):
        print(f"  Location:    {ev['location']}")
    print(f"  Calendar:    [{ev.get('account', '?')}] {ev.get('calendar', '')}")
    if ev.get("organizer"):
        print(f"  Organizer:   {ev['organizer']}")
    if ev.get("conferencing_link"):
        print(f"  Meet/Teams:  {ev['conferencing_link']}")
    if ev.get("html_link"):
        print(f"  Link:        {ev['html_link']}")
    rem = ev.get("reminder_minutes")
    if rem is not None:
        if rem == 0:
            print("  Reminder:    none")
        else:
            print(f"  Reminder:    {rem} min before")
    attendees = ev.get("attendees", [])
    if attendees:
        print("  Attendees:")
        for a in attendees:
            sym = RESPONSE_SYMBOL.get(a.get("response", ""), " ")
            mark = "  (you)" if a.get("self") else ""
            opt = "  (optional)" if a.get("optional") else ""
            print(f"    [{sym}] {a.get('email', '')}{mark}{opt}")
    if ev.get("description"):
        print("  Description:")
        for line in ev["description"].splitlines():
            print(f"    {line}")


def _event_date(iso: str) -> date | None:
    """Return the local date of an event's start. Returns None if unparseable."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone().date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(iso[:10])
    except (ValueError, TypeError):
        return None


def print_month_grid(events: list[dict], year: int, month: int) -> None:
    """Print a 7-column ASCII month grid with an event count under each day.

    Days outside the target month are blank. The current day is marked with
    a leading '*'. Days with one or more events show '(N)' on the row below
    the day number.
    """
    counts: dict[date, int] = defaultdict(int)
    for ev in events:
        d = _event_date(ev.get("start", ""))
        if d is not None and d.year == year and d.month == month:
            counts[d] += 1

    cal = _calendar.Calendar(firstweekday=0)  # Monday
    weeks = cal.monthdatescalendar(year, month)
    today = date.today()

    cell_w = 5  # " *27 " or "  27 " or " (3) "
    line_w = cell_w * 7

    print()
    print(f"{_calendar.month_name[month]} {year}".center(line_w))
    print()
    print("".join(f"{d:^{cell_w}}" for d in DAY_NAMES))
    print("-" * line_w)

    for week in weeks:
        # day-number row
        day_row = ""
        for d in week:
            if d.month != month:
                day_row += " " * cell_w
            else:
                marker = "*" if d == today else " "
                day_row += f" {marker}{d.day:<2d} "
        print(day_row)
        # event-count row
        cnt_row = ""
        has_any = False
        for d in week:
            n = counts.get(d, 0) if d.month == month else 0
            if n:
                has_any = True
                chip = f"({n})" if n < 10 else "(9+)"
                cnt_row += f"{chip:^{cell_w}}"
            else:
                cnt_row += " " * cell_w
        if has_any:
            print(cnt_row)
        print()

    if counts:
        print("  * today    (N) event count")


def print_week_grid(events: list[dict], start: date, width: int = 14) -> None:
    """Print a 7-day side-by-side grid of events.

    Each day is one column of width 'width'. Events are listed under their
    day with "HH:MM title", truncated to fit. Today's column is marked with
    a leading '*'.
    """
    days = [start + timedelta(days=i) for i in range(7)]
    by_day: dict[date, list[dict]] = {d: [] for d in days}
    for ev in events:
        d = _event_date(ev.get("start", ""))
        if d in by_day:
            by_day[d].append(ev)
    for d in by_day:
        by_day[d].sort(key=lambda e: e.get("start", ""))

    today = date.today()
    line_w = width * 7

    title = f"Week of {start:%a %b %d %Y}"
    print()
    print(title.center(line_w))
    print()

    header = ""
    for d in days:
        marker = "*" if d == today else " "
        cell = f"{marker}{DAY_NAMES[d.weekday()]} {d.day}"
        header += cell.ljust(width)
    print(header)
    print("-" * line_w)

    max_n = max((len(by_day[d]) for d in days), default=0)
    if max_n == 0:
        print("(no events this week)")
        return

    for i in range(max_n):
        row = ""
        for d in days:
            evs = by_day[d]
            if i < len(evs):
                ev = evs[i]
                iso = ev.get("start", "")
                try:
                    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                    time_s = dt.astimezone().strftime("%H:%M")
                except ValueError:
                    time_s = "all "
                content = f"{time_s} {ev.get('title', '')}"
                if len(content) > width - 1:
                    cell = content[: width - 2] + "…" + " "
                else:
                    cell = content.ljust(width)
            else:
                cell = " " * width
            row += cell
        print(row.rstrip())


def print_week_grid_vertical(events: list[dict], start: date) -> None:
    """Print a 7-day week with one day per section, events stacked under it.

    Same data as print_week_grid but one row per event instead of one column
    per day. Better for narrow terminals and for days with many events.
    """
    days = [start + timedelta(days=i) for i in range(7)]
    by_day: dict[date, list[dict]] = {d: [] for d in days}
    for ev in events:
        d = _event_date(ev.get("start", ""))
        if d in by_day:
            by_day[d].append(ev)
    for d in by_day:
        by_day[d].sort(key=lambda e: e.get("start", ""))

    today = date.today()
    title = f"Week of {start:%a %b %d %Y}"
    print()
    print(title)
    print()

    if not any(by_day[d] for d in days):
        print("(no events this week)")
        return

    for d in days:
        marker = "*" if d == today else " "
        header = f"{marker}{DAY_NAMES[d.weekday()]} {d:%Y-%m-%d}"
        print(header)
        evs = by_day[d]
        if not evs:
            print("    -")
            continue
        for ev in evs:
            iso = ev.get("start", "")
            try:
                dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                time_s = dt.astimezone().strftime("%H:%M")
            except ValueError:
                time_s = "all "
            print(f"    {time_s}  {ev.get('title', '')}")


def print_events(
    items: list[dict],
    show_id: bool = False,
    compact: bool = False,
    color: str = "never",
) -> None:
    """Print a list of events with account and calendar columns padded to the
    longest value in this batch, so rows align regardless of name length.

    The response column shows your RSVP status:
        +  accepted          ?  not yet answered
        ~  tentative         -  declined
        *  you are organizer (space) no info / not invited

    With compact=True the [account] and [calendar] columns are dropped from
    each line. Use the show subcommand or the vim plugin's gd/<CR> expand
    to see those for a specific event.

    With color in {auto, always}, the response bracket and the title are
    colorized by RSVP state. 'auto' only colors when stdout is a TTY.
    """
    if not items:
        return
    use_color = _should_color(color)
    acct_w = max(len(e.get("account", "?")) for e in items)
    cal_w = max(len(e.get("calendar_name") or e.get("calendar") or "") for e in items)
    for e in items:
        start = fmt_event_time(e["start"])
        title = e["title"]
        location = f"  @ {e['location']}" if e.get("location") else ""
        acct = e.get("account", "?")
        cal = e.get("calendar_name") or e.get("calendar") or ""
        response = e.get("response", "")
        rsym = RESPONSE_SYMBOL.get(response, " ")
        idpart = f"  [{e['id']}]" if show_id else ""
        sym = f"[{rsym}]"
        if use_color and response in ANSI_COLOR:
            c = ANSI_COLOR[response]
            sym = f"{c}{sym}{ANSI_RESET}"
            title = f"{c}{title}{ANSI_RESET}"
        if compact:
            mid = sym
        else:
            mid = f"{sym}  [{acct:<{acct_w}}]  [{cal:<{cal_w}}]"
        print(f"  {start:<16}  {mid}  {title}{location}{idpart}")
