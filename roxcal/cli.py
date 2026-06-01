"""Argparse-based CLI: subcommands and main entry point."""

from __future__ import annotations

import argparse
import calendar as _calendar
import json
import re
import shlex
import subprocess
from datetime import date, datetime, timedelta

from .backends import make_backend
from .config import Account, Config, die, load_config
from .events import (
    annotate_past,
    fmt_event_time,
    is_all_day,
    parse_duration,
    parse_event_dt,
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
    args,
    cfg: Config,
    start_dt: datetime,
    end_dt: datetime,
    query: str | None = None,
) -> list[dict]:
    """Gather events for an agenda/calm/calw/search view.

    Handles --calendar parsing and --all vs single-account dispatch. With
    --all, accounts that fail to authenticate are skipped with a note
    instead of aborting the whole call. Returns a list sorted by start.
    """
    calendars = _split_calendars(args.calendar)
    items: list[dict] = []
    accounts = (
        list(cfg.accounts.values())
        if args.all
        else [resolve_account(cfg, args.account)]
    )
    for acc in accounts:
        backend = make_backend(acc)
        try:
            if query is None:
                gen = backend.list_events(
                    start_dt,
                    end_dt,
                    calendars=calendars,
                    all_calendars=args.all_calendars,
                )
            else:
                gen = backend.search(
                    query,
                    start_dt,
                    end_dt,
                    calendars=calendars,
                    all_calendars=args.all_calendars,
                )
            items.extend(gen)
        except SystemExit:
            if not args.all:
                raise
            print(f"  [{acc.name}] skipped (not logged in?)")
    items.sort(key=lambda e: e["start"])
    if args.all and not getattr(args, "no_dedupe", False):
        items = _dedupe_by_ical_uid(items)
    return items


def _dedupe_by_ical_uid(items: list[dict]) -> list[dict]:
    # Events without an iCalUID stay as-is — no way to tell them apart.

    seen: set[str] = set()
    out: list[dict] = []
    for ev in items:
        uid = ev.get("ical_uid") or ""
        if uid and uid in seen:
            continue
        if uid:
            seen.add(uid)
        out.append(ev)
    return out


def cmd_init(args, cfg: Config) -> None:
    account = resolve_account(cfg, args.account)
    make_backend(account).init(port=args.port)


def cmd_list(args, cfg: Config) -> None:
    account = resolve_account(cfg, args.account)
    make_backend(account).list_calendars()


def cmd_agenda(args, cfg: Config) -> None:
    start, end = _resolve_window(args)
    items = _collect_events(args, cfg, start, end)
    annotate_past(items)
    if args.hide_past:
        items = [e for e in items if not e.get("is_past")]
    if args.json:
        print(json.dumps(items, default=str))
        return
    print_events(
        items,
        show_id=args.ids,
        compact=args.compact,
        color=cfg.color,
        colors=cfg.colors,
    )


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


def cmd_colors(args, cfg: Config) -> None:
    del args
    print(json.dumps(cfg.color_overrides))


def _ics_events(path: str):
    """Yield (title, start, end, location, description, attendees) tuples
    from a .ics file. Skips entries without DTSTART or DTEND."""
    from icalendar import Calendar

    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        die(f"could not read {path}: {exc}")
    try:
        cal = Calendar.from_ical(data)
    except ValueError as exc:
        die(f"could not parse {path}: {exc}")
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        dtstart = component.get("DTSTART")
        dtend = component.get("DTEND")
        if dtstart is None or dtend is None:
            continue
        attendees = []
        raw_att = component.get("ATTENDEE", [])
        if not isinstance(raw_att, list):
            raw_att = [raw_att]
        for a in raw_att:
            email = str(a).removeprefix("mailto:").removeprefix("MAILTO:")
            attendees.append(email)
        yield (
            str(component.get("SUMMARY", "(no title)")),
            dtstart.dt,
            dtend.dt,
            str(component.get("LOCATION", "")),
            str(component.get("DESCRIPTION", "")),
            attendees,
        )


def cmd_import(args, cfg: Config) -> None:
    account = resolve_account(cfg, args.account)
    backend = make_backend(account)
    notified: list[str] = []
    for title, start, end, location, description, attendees in _ics_events(args.file):
        body = description
        if attendees and not args.with_attendees:
            # Default: don't re-invite people the organizer already invited.
            # Keep the addresses in the description so the info is not lost.
            tail = "Attendees: " + ", ".join(attendees)
            body = f"{body}\n\n{tail}" if body else tail
        attendee_list = attendees if args.with_attendees else []
        if args.dry_run:
            print(f"Would import: {title}  {fmt_event_time(start.isoformat())}")
            continue
        backend.create_event(
            title=title,
            start=start,
            end=end,
            attendees=attendee_list,
            calendar=args.calendar,
            description=body,
            location=location,
        )
        notified.append(f"{title} ({fmt_event_time(start.isoformat())})")
    if args.notify and notified:
        subprocess.run(
            ["notify-send", "roxcal: imported", "\n".join(notified)],
            check=False,
        )


def cmd_search(args, cfg: Config) -> None:
    if args.start:
        start = parse_when(args.start)
    else:
        start = datetime.now().astimezone() - timedelta(days=args.days)
    end = (
        parse_when(args.end)
        if args.end
        else datetime.now().astimezone() + timedelta(days=args.days)
    )
    items = _collect_events(args, cfg, start, end, query=args.query)
    annotate_past(items)
    if not args.full:
        # Google's server-side q= also matches description and attendees,
        # which surfaces surprising hits. Narrow to title + location so
        # the default behavior matches the non-Google backends.
        q = args.query.lower()
        items = [
            ev
            for ev in items
            if q in ev.get("title", "").lower() or q in ev.get("location", "").lower()
        ]
    if args.json:
        print(json.dumps(items, default=str))
        return
    print_events(
        items,
        show_id=args.ids,
        compact=args.compact,
        color=cfg.color,
        colors=cfg.colors,
    )


def _remind_format_fields(ev: dict, now: datetime) -> dict:
    start_iso = ev.get("start", "")
    dt = parse_event_dt(start_iso)
    if dt is None:
        start_hm = start_iso
        start_full = start_iso
        minutes = 0
    else:
        start_hm = dt.strftime("%H:%M")
        start_full = dt.strftime("%Y-%m-%d %H:%M")
        minutes = max(0, int((dt - now).total_seconds() // 60))
    return {
        "title": ev.get("title", "(no title)"),
        "start": start_hm,
        "start_full": start_full,
        "location": ev.get("location", "") or "",
        "account": ev.get("account", "") or "",
        "minutes": minutes,
    }


def _starts_in_window(ev: dict, now: datetime, end: datetime) -> bool:
    # Backends return events that overlap the window. remind should only
    # fire for ones about to begin, so filter on the actual start time.
    # The lower bound is exclusive so a meeting whose start equals a cron
    # tick (e.g. 10:30 with cron */5 + remind 5) fires once at 10:25 and
    # is skipped at 10:30.
    dt = parse_event_dt(ev.get("start", ""))
    if dt is None:
        return False
    return now < dt <= end


def cmd_remind(args, cfg: Config) -> None:
    now = datetime.now().astimezone()
    end = now + timedelta(minutes=args.minutes)
    items = [
        ev
        for ev in _collect_events(args, cfg, now, end)
        if _starts_in_window(ev, now, end)
    ]

    if not args.template:
        for ev in items:
            print(f"{fmt_event_time(ev['start'])}  {ev.get('title', '')}")
        return

    try:
        tokens = shlex.split(args.template)
    except ValueError as exc:
        die(f"could not parse remind template: {exc}")
    if not tokens:
        die("remind template is empty")

    for ev in items:
        fields = _remind_format_fields(ev, now)
        try:
            filled = [t.format(**fields) for t in tokens]
        except KeyError as exc:
            die(f"unknown placeholder {exc} in remind template")
        if args.dry_run:
            print(" ".join(shlex.quote(t) for t in filled))
        else:
            subprocess.run(filled, check=False)


Cluster = list[tuple[datetime, datetime, dict]]


def _overlap_bounds(cluster: Cluster) -> tuple[datetime, datetime]:
    """Return the (start, end) of the time slice common to every event
    in the cluster — i.e. the actual overlap window."""
    return max(s for s, _, _ in cluster), min(e for _, e, _ in cluster)


def _overlap_clusters(items: list[dict]) -> list[Cluster]:
    """Group events whose time spans overlap into clusters of two or more.
    Back-to-back events (a.end == b.start) do not count as overlapping.
    Assumes `items` is already sorted by start (_collect_events guarantees it).
    """
    clusters: list[Cluster] = []
    current: Cluster = []
    cluster_end: datetime | None = None
    for ev in items:
        s = parse_event_dt(ev.get("start", ""))
        e = parse_event_dt(ev.get("end", ""))
        if s is None or e is None:
            continue
        if current and cluster_end is not None and s < cluster_end:
            current.append((s, e, ev))
            cluster_end = max(cluster_end, e)
            continue
        if len(current) >= 2:
            clusters.append(current)
        current = [(s, e, ev)]
        cluster_end = e
    if len(current) >= 2:
        clusters.append(current)
    return clusters


def _resolve_window(args) -> tuple[datetime, datetime]:
    """Resolve the (start, end) window for agenda/conflicts. Defaults to
    today 00:00 with end = start + args.days when not given on the CLI."""
    if args.start:
        start = parse_when(args.start)
    else:
        start = (
            datetime.now()
            .astimezone()
            .replace(hour=0, minute=0, second=0, microsecond=0)
        )
    end = parse_when(args.end) if args.end else start + timedelta(days=args.days)
    return start, end


def cmd_conflicts(args, cfg: Config) -> None:
    start, end = _resolve_window(args)

    all_events = _collect_events(args, cfg, start, end)
    annotate_past(all_events)
    candidates: list[dict] = []
    for ev in all_events:
        if ev.get("response") == "declined":
            continue
        if args.skip_all_day and is_all_day(ev):
            continue
        candidates.append(ev)

    clusters = _overlap_clusters(candidates)

    if args.json:
        out = []
        for c in clusters:
            ov_start, ov_end = _overlap_bounds(c)
            out.append(
                {
                    "overlap_start": ov_start.isoformat(),
                    "overlap_end": ov_end.isoformat(),
                    "events": [ev for _, _, ev in c],
                }
            )
        print(json.dumps(out, default=str))
        return

    for i, cluster in enumerate(clusters):
        if i > 0:
            print()
        ov_start, ov_end = _overlap_bounds(cluster)
        print(
            f"Overlap {fmt_event_time(ov_start.isoformat())} "
            f"-> {fmt_event_time(ov_end.isoformat())}:"
        )
        print_events([ev for _, _, ev in cluster], color=cfg.color, colors=cfg.colors)


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
    annotate_past(items)
    if args.vertical:
        print_week_grid_vertical(items, start, color=cfg.color, colors=cfg.colors)
    else:
        print_week_grid(
            items,
            start,
            width=args.width,
            color=cfg.color,
            colors=cfg.colors,
        )


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
        "--hide-past",
        action="store_true",
        help="Drop events that have already ended. Past events are dimmed "
        "in the output by default; this skips them entirely.",
    )
    sp.add_argument(
        "--no-dedupe",
        action="store_true",
        help="With --all, keep every copy of an event that appears on "
        "multiple accounts. Default deduplicates by iCalUID.",
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

    sp = sub.add_parser(
        "colors",
        help="Emit the user's [colors] overrides as JSON. Used by the "
        "vim plugin to mirror the CLI palette in roxcal:// buffers.",
    )
    sp.set_defaults(func=cmd_colors)

    sp = sub.add_parser(
        "import",
        help="Add the events in a .ics file to your calendar.",
        description="Useful as a mail-client handler for text/calendar "
        "attachments. By default the original attendees stay in the "
        "description; --with-attendees re-invites them.",
    )
    sp.add_argument("file", help=".ics file path")
    sp.add_argument(
        "--calendar",
        "-c",
        help="Calendar id/name. Default: backend's primary.",
    )
    sp.add_argument(
        "--with-attendees",
        action="store_true",
        help="Re-invite the attendees listed in the .ics.",
    )
    sp.add_argument(
        "--notify",
        action="store_true",
        help="Fire notify-send for each imported event (use from a .desktop).",
    )
    sp.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Print what would be imported, do not create events.",
    )
    sp.set_defaults(func=cmd_import)

    sp = sub.add_parser(
        "search",
        help="Search events by substring across title and location.",
        description="Google uses native server-side q= which also matches "
        "description and attendees. Other backends filter client-side on "
        "title and location.",
    )
    sp.add_argument("query", help="Text to search for")
    sp.add_argument("start", nargs="?", help="Start (default: now - --days)")
    sp.add_argument("end", nargs="?", help="End (default: now + --days)")
    sp.add_argument(
        "--days",
        "-D",
        type=int,
        default=365,
        help="Past and future window in days when start/end are omitted "
        "(default: 365)",
    )
    sp.add_argument(
        "--calendar",
        "-c",
        action="append",
        default=None,
        help="Calendar id/name. Repeat or comma-separate.",
    )
    sp.add_argument("--all", action="store_true", help="Search across all accounts")
    sp.add_argument(
        "--all-calendars",
        action="store_true",
        help="Ignore the per-account calendars filter",
    )
    sp.add_argument("--ids", action="store_true", help="Show event ids")
    sp.add_argument("--compact", action="store_true", help="Compact line format")
    sp.add_argument(
        "--no-dedupe",
        action="store_true",
        help="With --all, keep duplicates of meetings shared across accounts.",
    )
    sp.add_argument(
        "--full",
        action="store_true",
        help="Also match description and attendees (Google only). Default "
        "narrows to title and location to match the non-Google backends.",
    )
    sp.add_argument(
        "--json",
        action="store_true",
        help="Emit raw JSON instead of formatted lines",
    )
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser(
        "conflicts",
        help="Find events whose time spans overlap (double-bookings).",
        description="Most useful with --all to catch overlaps between "
        "accounts. Declined events are always skipped.",
    )
    sp.add_argument("start", nargs="?", help="Start (default: today 00:00)")
    sp.add_argument("end", nargs="?", help="End (default: start + --days)")
    sp.add_argument(
        "--days",
        "-D",
        type=int,
        default=7,
        help="Window size in days when end is omitted (default: 7)",
    )
    sp.add_argument(
        "--calendar",
        "-c",
        action="append",
        default=None,
        help="Calendar id/name. Repeat or comma-separate.",
    )
    sp.add_argument(
        "--all", action="store_true", help="Check events across all accounts"
    )
    sp.add_argument(
        "--all-calendars",
        action="store_true",
        help="Ignore the per-account calendars filter",
    )
    sp.add_argument(
        "--skip-all-day",
        action="store_true",
        help="Do not flag all-day events as conflicting with timed events.",
    )
    sp.add_argument(
        "--no-dedupe",
        action="store_true",
        help="With --all, keep duplicates of meetings shared across accounts.",
    )
    sp.add_argument(
        "--json",
        action="store_true",
        help="Emit clusters as JSON (used by the vim plugin).",
    )
    sp.set_defaults(func=cmd_conflicts)

    sp = sub.add_parser(
        "remind",
        help="Run a command for each event starting within the next N "
        "minutes. Designed for cron or a user systemd timer + notify-send.",
        description="Pick a window equal to your cron/systemd interval to "
        "fire each notification exactly once.",
    )
    sp.add_argument("minutes", type=int, help="Look-ahead window in minutes")
    sp.add_argument(
        "template",
        nargs="?",
        default=None,
        help='Command template, e.g. \'notify-send "{title}" "{start}"\'. '
        "Tokenized with shlex; placeholders inside tokens are filled with "
        "{title}, {start} (HH:MM), {start_full} (YYYY-MM-DD HH:MM), "
        "{location}, {account}, {minutes}. If omitted, prints upcoming "
        "events to stdout.",
    )
    sp.add_argument(
        "--calendar",
        "-c",
        action="append",
        default=None,
        help="Calendar id/name. Repeat or comma-separate.",
    )
    sp.add_argument(
        "--all", action="store_true", help="Check events across all accounts"
    )
    sp.add_argument(
        "--all-calendars",
        action="store_true",
        help="Ignore the per-account calendars filter",
    )
    sp.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Print the command(s) that would run, do not execute them.",
    )
    sp.set_defaults(func=cmd_remind)

    return p


def main() -> None:
    args = build_parser().parse_args()
    cfg = load_config()
    args.func(args, cfg)


if __name__ == "__main__":  # pragma: no cover
    main()
