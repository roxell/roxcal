"""Shared CalDAV backend. Subclasses override _resolve_url and the
notice hooks; everything else is generic."""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone

from ..config import CONFIG_FILE, die
from . import Backend


def _to_vevent(ev):
    # caldav 2.x dropped vobject; parse ev.data with icalendar instead.
    from icalendar import Calendar as ICalendar

    ical = ICalendar.from_ical(ev.data)
    for comp in ical.walk("VEVENT"):
        return comp
    return None


def _iso_or_str(field):
    if field is None:
        return ""
    dt = field.dt
    return dt.isoformat() if isinstance(dt, datetime) else str(dt)


def _text(comp, key):
    val = comp.get(key)
    return str(val) if val is not None else ""


class CalDAVBackend(Backend):
    def __init__(self, account):
        super().__init__(account)
        self._cached_client = None
        self._cached_calendars: list | None = None

    # -- hooks for subclasses --

    def _resolve_url(self, configured: str) -> str:
        return configured

    def _create_notices(self, *, conferencing: bool, attendees: bool) -> None:
        pass

    def _rsvp_outcome_note(self) -> str:
        return "RSVP via CalDAV"

    # -- connection --

    def _client(self):
        if self._cached_client is not None:
            return self._cached_client
        import caldav

        if not self.account.caldav_password:
            die(
                f"missing caldav_password for '{self.account.name}'. "
                f"Edit {CONFIG_FILE}."
            )
        if not self.account.caldav_username and not self.account.email:
            die(
                f"set caldav_username or email for '{self.account.name}'. "
                f"Edit {CONFIG_FILE}."
            )
        if not self.account.caldav_url:
            die(
                f"missing caldav_url for '{self.account.name}'. " f"Edit {CONFIG_FILE}."
            )
        username = self.account.caldav_username or self.account.email
        self._cached_client = caldav.DAVClient(
            url=self._resolve_url(self.account.caldav_url),
            username=username,
            password=self.account.caldav_password,
        )
        return self._cached_client

    def _all_calendars(self) -> list:
        if self._cached_calendars is not None:
            return self._cached_calendars
        self._cached_calendars = self._client().principal().calendars()
        return self._cached_calendars

    def _calendar_obj(self, name: str | None):
        cals = self._all_calendars()
        if not cals:
            die("no calendars visible via CalDAV")
        if not name:
            return cals[0]
        for cal in cals:
            if name in (cal.name, str(cal.url)):
                return cal
        die(f"calendar '{name}' not found via CalDAV")

    # -- commands --

    def init(self, port: int = 0) -> None:
        del port
        cals = self._all_calendars()
        print(f"CalDAV connection OK. {len(cals)} calendars visible.")

    def list_calendars(self) -> None:
        for cal in self._all_calendars():
            print(f"{cal.url}  {cal.name or ''}")

    def list_events(self, start, end, calendars=None, all_calendars=False):
        all_cals = self._all_calendars()

        if calendars:
            wanted = set(calendars)
            cals = [c for c in all_cals if c.name in wanted or str(c.url) in wanted]
        elif self.account.calendars and not all_calendars:
            wanted = set(self.account.calendars)
            cals = [c for c in all_cals if c.name in wanted or str(c.url) in wanted]
        else:
            cals = all_cals

        for cal in cals:
            cal_id = str(cal.url)
            cal_name = cal.name or cal_id.rstrip("/").rsplit("/", 1)[-1]
            events = cal.date_search(start=start, end=end, expand=True)
            for ev in events:
                vevent = _to_vevent(ev)
                if vevent is None:
                    continue
                start_iso = _iso_or_str(vevent.get("DTSTART"))
                title = _text(vevent, "SUMMARY") or "(no title)"
                end_iso = _iso_or_str(vevent.get("DTEND"))
                location = _text(vevent, "LOCATION")
                # CalDAV's event id IS the iCalendar UID, so id and
                # ical_uid are the same string. Google and Graph expose
                # them as separate fields.
                uid = _text(vevent, "UID")
                yield {
                    "id": uid,
                    "ical_uid": uid,
                    "title": title,
                    "start": start_iso,
                    "end": end_iso,
                    "location": location,
                    "account": self.account.name,
                    "calendar": cal_id,
                    "calendar_name": cal_name,
                }

    def create_event(
        self,
        *,
        title,
        start,
        end,
        attendees=None,
        conferencing=False,
        calendar=None,
        description="",
        location="",
        reminder_minutes=10,
    ):
        self._create_notices(conferencing=conferencing, attendees=bool(attendees))
        from icalendar import Alarm, Calendar as ICalendar, Event as IEvent

        cal_obj = self._calendar_obj(calendar)
        cal = ICalendar()
        cal.add("prodid", "-//roxcal//local//EN")
        cal.add("version", "2.0")
        ev = IEvent()
        ev.add("uid", str(uuid.uuid4()) + "@roxcal.local")
        ev.add("summary", title)
        ev.add("dtstart", start)
        ev.add("dtend", end)
        ev.add("dtstamp", datetime.now(timezone.utc))
        if description:
            ev.add("description", description)
        if location:
            ev.add("location", location)
        if attendees:
            for a in attendees:
                ev.add("attendee", f"mailto:{a}", parameters={"RSVP": "TRUE"})
        if reminder_minutes > 0:
            alarm = Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("trigger", timedelta(minutes=-reminder_minutes))
            alarm.add("description", "Reminder")
            ev.add_component(alarm)
        cal.add_component(ev)
        cal_obj.save_event(cal.to_ical().decode())
        print(f"Created event via CalDAV: {ev['uid']}")

    def delete_event(self, event_id, calendar=None):
        if calendar:
            cals = [self._calendar_obj(calendar)]
        else:
            cals = self._all_calendars()
        for cal in cals:
            try:
                ev = cal.event_by_uid(event_id)
            except Exception:
                continue
            ev.delete()
            print(f"Deleted event {event_id}")
            return
        die(f"event {event_id} not found via CalDAV on '{self.account.name}'")

    def update_event(
        self,
        event_id,
        calendar=None,
        *,
        title=None,
        start=None,
        end=None,
        attendees=None,
        location=None,
        description=None,
        reminder_minutes=None,
    ):
        from icalendar import Alarm, Calendar as ICalendar

        if calendar:
            cals = [self._calendar_obj(calendar)]
        else:
            cals = self._all_calendars()
        ev_obj = None
        for cal in cals:
            try:
                ev_obj = cal.event_by_uid(event_id)
                break
            except Exception:
                continue
        if ev_obj is None:
            die(f"event {event_id} not found via CalDAV on '{self.account.name}'")
        ical = ICalendar.from_ical(ev_obj.data)
        changed = False
        for component in ical.walk():
            if component.name != "VEVENT":
                continue
            if title is not None:
                component["SUMMARY"] = title
                changed = True
            if start is not None:
                component["DTSTART"] = start
                changed = True
            if end is not None:
                component["DTEND"] = end
                changed = True
            if location is not None:
                component["LOCATION"] = location
                changed = True
            if description is not None:
                component["DESCRIPTION"] = description
                changed = True
            if attendees is not None:
                if "ATTENDEE" in component:
                    del component["ATTENDEE"]
                for a in attendees:
                    component.add(
                        "attendee", f"mailto:{a}", parameters={"RSVP": "TRUE"}
                    )
                changed = True
            if reminder_minutes is not None:
                component.subcomponents = [
                    sc for sc in component.subcomponents if sc.name != "VALARM"
                ]
                if reminder_minutes > 0:
                    alarm = Alarm()
                    alarm.add("action", "DISPLAY")
                    alarm.add("trigger", timedelta(minutes=-reminder_minutes))
                    alarm.add("description", "Reminder")
                    component.add_component(alarm)
                changed = True
            break
        if not changed:
            print("(no changes)")
            return
        ev_obj.data = ical.to_ical().decode()
        ev_obj.save()
        print(f"Updated event via CalDAV: {event_id}")

    def get_event(self, event_id, calendar=None):
        if calendar:
            cals = [self._calendar_obj(calendar)]
        else:
            cals = self._all_calendars()
        ev = None
        cal_used = ""
        for cal in cals:
            try:
                ev = cal.event_by_uid(event_id)
                cal_used = cal.name or str(cal.url)
                break
            except Exception:
                continue
        if ev is None:
            die(f"event {event_id} not found via CalDAV on '{self.account.name}'")
        vevent = _to_vevent(ev)
        if vevent is None:
            die(f"event {event_id} has no VEVENT in its iCalendar data")
        start_iso = _iso_or_str(vevent.get("DTSTART"))
        end_iso = _iso_or_str(vevent.get("DTEND"))
        title = _text(vevent, "SUMMARY") or "(no title)"
        location = _text(vevent, "LOCATION")
        description = _text(vevent, "DESCRIPTION")
        organizer = _text(vevent, "ORGANIZER").removeprefix("mailto:")
        partstat_map = {
            "ACCEPTED": "accepted",
            "DECLINED": "declined",
            "TENTATIVE": "tentative",
            "NEEDS-ACTION": "needsAction",
        }
        me = self.account.email.lower()
        raw_attendees = vevent.get("ATTENDEE", [])
        if not isinstance(raw_attendees, list):
            raw_attendees = [raw_attendees]
        attendees = []
        for entry in raw_attendees:
            addr = str(entry).removeprefix("mailto:")
            partstat = entry.params.get("PARTSTAT", "")
            attendees.append(
                {
                    "email": addr,
                    "response": partstat_map.get(partstat.upper(), ""),
                    "self": addr.lower() == me,
                    "optional": False,
                }
            )
        reminder_min: int | None = None
        for sub in vevent.subcomponents:
            if sub.name != "VALARM":
                continue
            trigger = sub.get("TRIGGER")
            if trigger is None:
                continue
            if isinstance(trigger.dt, timedelta):
                reminder_min = -int(trigger.dt.total_seconds() // 60)
                break
        return {
            "id": event_id,
            "title": title,
            "start": start_iso,
            "end": end_iso,
            "location": location,
            "description": description,
            "organizer": organizer,
            "attendees": attendees,
            "conferencing_link": "",
            "html_link": "",
            "reminder_minutes": reminder_min,
            "account": self.account.name,
            "calendar": cal_used,
        }

    def rsvp(self, event_id, response, calendar=None, comment=""):
        if comment:
            print(
                "note: CalDAV does not transmit response comments; ignored.",
                file=sys.stderr,
            )
        from icalendar import Calendar as ICalendar

        partstat = {
            "accepted": "ACCEPTED",
            "declined": "DECLINED",
            "tentative": "TENTATIVE",
        }.get(response)
        if not partstat:
            die(f"unknown rsvp response '{response}'")
        if not self.account.email:
            die(
                f"set email for '{self.account.name}' before you can RSVP. "
                f"Edit {CONFIG_FILE}."
            )
        cal_obj = self._calendar_obj(calendar)
        ev = cal_obj.event_by_uid(event_id)
        ical = ICalendar.from_ical(ev.data)
        me = self.account.email.lower()
        found = False
        for component in ical.walk():
            if component.name != "VEVENT":
                continue
            for attendee in component.get("attendee", []):
                addr = str(attendee).removeprefix("mailto:").lower()
                if addr == me:
                    attendee.params["PARTSTAT"] = partstat
                    found = True
        if not found:
            die(f"you ({self.account.email}) are not an attendee on event {event_id}")
        ev.data = ical.to_ical().decode()
        ev.save()
        print(f"{self._rsvp_outcome_note()}: {response} on event {event_id}")
