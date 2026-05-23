"""Argparse-based CLI: subcommands and main entry point."""

from __future__ import annotations

import argparse
import calendar as _calendar
import json
import re
from datetime import date, datetime, timedelta

from .backends import make_backend
from .config import Account, Config, die, load_config
from .events import (
    parse_duration,
    parse_when,
    print_event_detail,
    print_events,
    print_month_grid,
    print_week_grid,
    print_week_grid_vertical,
)


def _parse_reminder(s: str) -> int:
    """Reminder lead time in minutes. Accepts a bare number of minutes
    ('10', '0') or a duration-style string with d/h/m components
    ('10m', '1h', '1d', '2h30m', '1d2h')."""
    s = s.strip().lower()
    if s.isdigit():
        return int(s)
    m = re.fullmatch(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?", s)
    if m and (m.group(1) or m.group(2) or m.group(3)):
        d = int(m.group(1) or 0)
        h = int(m.group(2) or 0)
        mn = int(m.group(3) or 0)
        return d * 24 * 60 + h * 60 + mn
    raise argparse.ArgumentTypeError(
        f"reminder must be like 10, 10m, 1h, 1d, 2h30m or 1d2h, got {s!r}"
    )


def resolve_account(cfg: Config, name: str | None) -> Account:
    name = name or cfg.default_account
    if name not in cfg.accounts:
        die(f"unknown account '{name}'. Known: {', '.join(cfg.accounts) or '(none)'}")
    return cfg.accounts[name]


def _split_calendars(raw: list[str] | None) -> list[str] | None:
    """Flatten the repeatable+comma-separated --calendar argument into a list."""
    if not raw:
        return None
    out: list[str] = []
    for c in raw:
        out.extend(p.strip() for p in c.split(",") if p.strip())
    return out or None


def _collect_events(
    args, cfg: Config, start_dt: datetime, end_dt: datetime
) -> list[dict]:
    """Gather events for an agenda/calm/calw view.

    Handles --calendar parsing, --all vs single-account dispatch and the
    "skip account that has no token" path. Returns a list sorted by start.
    """
    calendars = _split_calendars(args.calendar)
    items: list[dict] = []
    if args.all:
        for acc in cfg.accounts.values():
            try:
                items.extend(
                    make_backend(acc).list_events(
                        start_dt,
                        end_dt,
                        calendars=calendars,
                        all_calendars=args.all_calendars,
                    )
                )
            except SystemExit:
                print(f"  [{acc.name}] skipped (not logged in?)")
    else:
        account = resolve_account(cfg, args.account)
        items.extend(
            make_backend(account).list_events(
                start_dt,
                end_dt,
                calendars=calendars,
                all_calendars=args.all_calendars,
            )
        )
    items.sort(key=lambda e: e["start"])
    return items


def cmd_init(args, cfg: Config) -> None:
    account = resolve_account(cfg, args.account)
    make_backend(account).init(port=args.port)


def cmd_list(args, cfg: Config) -> None:
    account = resolve_account(cfg, args.account)
    make_backend(account).list_calendars()


def cmd_agenda(args, cfg: Config) -> None:
    if args.start:
        start = parse_when(args.start)
    else:
        start = (
            datetime.now()
            .astimezone()
            .replace(hour=0, minute=0, second=0, microsecond=0)
        )
    end = parse_when(args.end) if args.end else start + timedelta(days=args.days)
    items = _collect_events(args, cfg, start, end)
    if args.json:
        print(json.dumps(items, default=str))
        return
    print_events(items, show_id=args.ids, compact=args.compact)


def cmd_add(args, cfg: Config) -> None:
    account = resolve_account(cfg, args.account)
    start = parse_when(args.when)
    end = start + parse_duration(args.duration)
    attendees = (
        [a.strip() for a in args.attendees.split(",") if a.strip()]
        if args.attendees
        else []
    )
    make_backend(account).create_event(
        title=args.title,
        start=start,
        end=end,
        attendees=attendees,
        conferencing=args.meet,
        calendar=args.calendar,
        description=args.description,
        location=args.where,
        reminder_minutes=args.reminder,
    )


def cmd_rsvp(args, cfg: Config) -> None:
    account = resolve_account(cfg, args.account)
    make_backend(account).rsvp(
        args.event_id,
        args.response,
        calendar=args.calendar,
        comment=args.comment or "",
    )


def cmd_show(args, cfg: Config) -> None:
    account = resolve_account(cfg, args.account)
    ev = make_backend(account).get_event(args.event_id, calendar=args.calendar)
    if args.json:
        print(json.dumps(ev, default=str))
        return
    print_event_detail(ev)


def cmd_delete(args, cfg: Config) -> None:
    account = resolve_account(cfg, args.account)
    make_backend(account).delete_event(args.event_id, calendar=args.calendar)


def cmd_quick(args, cfg: Config) -> None:
    account = resolve_account(cfg, args.account)
    make_backend(account).quick_add(args.text, calendar=args.calendar)


def cmd_edit(args, cfg: Config) -> None:
    account = resolve_account(cfg, args.account)
    backend = make_backend(account)

    fields: dict = {}
    if args.title is not None:
        fields["title"] = args.title
    if args.where is not None:
        fields["location"] = args.where
    if args.description is not None:
        fields["description"] = args.description
    if args.attendees is not None:
        fields["attendees"] = [
            a.strip() for a in args.attendees.split(",") if a.strip()
        ]
    if args.reminder is not None:
        fields["reminder_minutes"] = args.reminder

    if args.when is not None or args.duration is not None:
        current = None
        if args.when is not None:
            new_start = parse_when(args.when)
        else:
            current = backend.get_event(args.event_id, calendar=args.calendar)
            new_start = datetime.fromisoformat(current["start"].replace("Z", "+00:00"))

        if args.duration is not None:
            duration = parse_duration(args.duration)
        else:
            current = current or backend.get_event(
                args.event_id, calendar=args.calendar
            )
            cs = datetime.fromisoformat(current["start"].replace("Z", "+00:00"))
            ce = datetime.fromisoformat(current["end"].replace("Z", "+00:00"))
            duration = ce - cs

        fields["start"] = new_start
        fields["end"] = new_start + duration

    if not fields:
        die(
            "nothing to update; specify at least one of "
            "--title, --when, --duration, --where, --description, --attendees"
        )
    backend.update_event(args.event_id, calendar=args.calendar, **fields)


def _resolve_month(spec: str | None) -> tuple[int, int]:
    if not spec:
        now = datetime.now()
        return now.year, now.month
    try:
        y, m = spec.split("-")
        year, month = int(y), int(m)
    except (ValueError, AttributeError):
        die(f"could not parse month '{spec}' (expected YYYY-MM)")
    if not 1 <= month <= 12:
        die(f"month out of range in '{spec}'")
    return year, month


def cmd_calm(args, cfg: Config) -> None:
    year, month = _resolve_month(args.month)
    last_day = _calendar.monthrange(year, month)[1]
    first = date(year, month, 1)
    last = date(year, month, last_day)
    grid_start = first - timedelta(days=first.weekday())
    grid_end = last + timedelta(days=7 - last.weekday())
    start_dt = datetime.combine(grid_start, datetime.min.time()).astimezone()
    end_dt = datetime.combine(grid_end, datetime.min.time()).astimezone()
    items = _collect_events(args, cfg, start_dt, end_dt)
    print_month_grid(items, year, month)


def _week_start(spec: str | None) -> date:
    if not spec:
        today = date.today()
        return today - timedelta(days=today.weekday())
    parsed = parse_when(spec)
    d = parsed.date()
    return d - timedelta(days=d.weekday())


def cmd_calw(args, cfg: Config) -> None:
    start = _week_start(args.start)
    end = start + timedelta(days=7)
    start_dt = datetime.combine(start, datetime.min.time()).astimezone()
    end_dt = datetime.combine(end, datetime.min.time()).astimezone()
    items = _collect_events(args, cfg, start_dt, end_dt)
    if args.vertical:
        print_week_grid_vertical(items, start)
    else:
        print_week_grid(items, start, width=args.width)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="roxcal", description="Unified calendar CLI.")
    p.add_argument("--account", "-a", help="Account name (default from config)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="Run OAuth or verify credentials for the account")
    sp.add_argument(
        "--port",
        type=int,
        default=0,
        help="Fixed local port for the OAuth callback (default: random). "
        "Use a fixed port together with `ssh -L PORT:localhost:PORT host` to "
        "run init on a remote host and complete the browser login on your laptop.",
    )
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("list", help="List calendars on the account")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("agenda", help="Show events in a time range")
    sp.add_argument("start", nargs="?", help="Start (e.g. 'today', '2026-05-21')")
    sp.add_argument("end", nargs="?", help="End (default: start + --days)")
    sp.add_argument(
        "--days",
        "-D",
        type=int,
        default=7,
        help="Default window size in days when end is not given (default: 7)",
    )
    sp.add_argument(
        "--calendar",
        "-c",
        action="append",
        default=None,
        help="Calendar id/name. Repeat (-c a -c b) or comma-separate (-c a,b) "
        "to pick multiple. Overrides the per-account calendars filter.",
    )
    sp.add_argument("--all", action="store_true", help="Merge events from all accounts")
    sp.add_argument(
        "--all-calendars",
        action="store_true",
        help="Ignore the per-account calendars filter and show every calendar",
    )
    sp.add_argument("--ids", action="store_true", help="Show event ids")
    sp.add_argument(
        "--compact",
        action="store_true",
        help="Drop the [account] and [calendar] columns. Use 'show' or the "
        "vim plugin's gd/<CR> expand to see them for a specific event.",
    )
    sp.add_argument(
        "--json",
        action="store_true",
        help="Emit raw JSON instead of formatted lines (for vim/fzf/scripts)",
    )
    sp.set_defaults(func=cmd_agenda)

    sp = sub.add_parser("add", help="Create an event")
    sp.add_argument("--title", "-t", required=True)
    sp.add_argument(
        "--when", "-w", required=True, help="Start time, e.g. '2026-05-21 14:00'"
    )
    sp.add_argument("--duration", "-d", default="30m", help="e.g. 30m, 1h, 2h30m")
    sp.add_argument("--attendees", help="Comma-separated emails")
    sp.add_argument(
        "--meet", action="store_true", help="Add a Google Meet / Teams link"
    )
    sp.add_argument("--calendar", "-c", help="Target calendar id/name")
    sp.add_argument("--description", default="")
    sp.add_argument("--where", default="", help="Location")
    sp.add_argument(
        "--reminder",
        type=_parse_reminder,
        default=10,
        help="Popup reminder lead time. Accepts 10, 10m, 1h, 1d, 2h30m. "
        "0 to disable. Default: 10 (i.e. 10 minutes).",
    )
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("rsvp", help="Respond to an invite")
    sp.add_argument("event_id")
    sp.add_argument("response", choices=["accepted", "declined", "tentative"])
    sp.add_argument("--calendar", "-c", help="Calendar the event lives on")
    sp.add_argument(
        "--comment",
        "-m",
        help='Optional response comment (e.g. "Conflict with another meeting"). '
        "Sent to the organizer with the RSVP. Ignored on CalDAV.",
    )
    sp.set_defaults(func=cmd_rsvp)

    sp = sub.add_parser("show", help="Show full detail of one event")
    sp.add_argument("event_id")
    sp.add_argument(
        "--calendar",
        "-c",
        help="Calendar the event lives on (default: search the account's calendars)",
    )
    sp.add_argument(
        "--json",
        action="store_true",
        help="Emit raw JSON instead of a formatted block",
    )
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser(
        "delete",
        help="Delete an event. If you are the organizer this cancels it for "
        "all attendees and sends cancellation emails.",
    )
    sp.add_argument("event_id")
    sp.add_argument("--calendar", "-c", help="Calendar the event lives on")
    sp.set_defaults(func=cmd_delete)

    sp = sub.add_parser(
        "quick",
        help="Create an event from a natural-language phrase "
        '(e.g. "Lunch with Maria tomorrow 12:30"). Google only.',
    )
    sp.add_argument(
        "text",
        help='Event description, e.g. "Lunch with Maria tomorrow 12:30"',
    )
    sp.add_argument(
        "--calendar",
        "-c",
        help="Target calendar (default: primary)",
    )
    sp.set_defaults(func=cmd_quick)

    sp = sub.add_parser(
        "calm",
        help="ASCII month grid with event counts per day",
    )
    sp.add_argument(
        "month",
        nargs="?",
        help="Target month as YYYY-MM (default: current month)",
    )
    sp.add_argument(
        "--calendar",
        "-c",
        action="append",
        default=None,
        help="Calendar id/name. Repeat or comma-separate for multiple.",
    )
    sp.add_argument(
        "--all",
        action="store_true",
        help="Merge events from all accounts",
    )
    sp.add_argument(
        "--all-calendars",
        action="store_true",
        help="Ignore the per-account calendars filter",
    )
    sp.set_defaults(func=cmd_calm)

    sp = sub.add_parser(
        "calw",
        help="ASCII 7-day side-by-side week grid",
    )
    sp.add_argument(
        "start",
        nargs="?",
        help="Any day in the target week (default: this week, Monday-start)",
    )
    sp.add_argument(
        "--width",
        type=int,
        default=14,
        help="Per-column width in characters (default: 14)",
    )
    sp.add_argument(
        "--vertical",
        action="store_true",
        help="Stack days top-to-bottom instead of side-by-side",
    )
    sp.add_argument(
        "--calendar",
        "-c",
        action="append",
        default=None,
        help="Calendar id/name. Repeat or comma-separate for multiple.",
    )
    sp.add_argument(
        "--all",
        action="store_true",
        help="Merge events from all accounts",
    )
    sp.add_argument(
        "--all-calendars",
        action="store_true",
        help="Ignore the per-account calendars filter",
    )
    sp.set_defaults(func=cmd_calw)

    sp = sub.add_parser(
        "edit",
        help="Update fields of an existing event. Any subset of flags can be given.",
    )
    sp.add_argument("event_id")
    sp.add_argument("--calendar", "-c", help="Calendar the event lives on")
    sp.add_argument("--title", "-t")
    sp.add_argument("--when", "-w", help="New start time")
    sp.add_argument(
        "--duration",
        "-d",
        help="New duration (e.g. 30m, 1h, 2h30m). Combined with --when, or "
        "applied to the existing start when --when is omitted.",
    )
    sp.add_argument("--attendees", help="Comma-separated emails (replaces list)")
    sp.add_argument("--where", help="Location")
    sp.add_argument("--description")
    sp.add_argument(
        "--reminder",
        type=_parse_reminder,
        default=None,
        help="New popup reminder lead time (10, 10m, 1h, 1d, 2h30m). " "0 to disable.",
    )
    sp.set_defaults(func=cmd_edit)

    return p


def main() -> None:
    args = build_parser().parse_args()
    cfg = load_config()
    args.func(args, cfg)


if __name__ == "__main__":  # pragma: no cover
    main()
