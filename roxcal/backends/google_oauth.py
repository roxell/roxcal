"""Google Calendar via the REST API with OAuth."""

from __future__ import annotations

import json
import os
import uuid
from datetime import timezone
from pathlib import Path

from ..config import CONFIG_FILE, GCALCLI_TOKEN_ROOT, die
from . import Backend

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleOAuthBackend(Backend):
    def __init__(self, account):
        super().__init__(account)
        self._cached_service = None
        self._cached_calendar_list: dict[str, str] | None = None

    def _token_path(self) -> Path:
        return GCALCLI_TOKEN_ROOT / self.account.name / "oauth_creds"

    def _load_creds(self):
        from google.oauth2.credentials import Credentials

        path = self._token_path()
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
            scopes=data.get("scopes", SCOPES),
        )

    def _save_creds(self, creds) -> None:
        path = self._token_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(creds.to_json())
        os.chmod(path, 0o600)

    def _service(self):
        if self._cached_service is not None:
            return self._cached_service
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = self._load_creds()
        if not creds:
            die(
                f"no token for '{self.account.name}'. "
                f"Run `roxcal --account {self.account.name} init`."
            )
        if not creds.valid:
            if creds.refresh_token:
                creds.refresh(Request())
                self._save_creds(creds)
            else:
                die(
                    f"token for '{self.account.name}' is invalid and cannot be refreshed."
                )
        self._cached_service = build(
            "calendar", "v3", credentials=creds, cache_discovery=False
        )
        return self._cached_service

    def _calendar_list(self) -> dict[str, str]:
        """Cached calendar id->summary map for this backend instance."""
        if self._cached_calendar_list is not None:
            return self._cached_calendar_list
        cal_list = self._service().calendarList().list().execute()
        self._cached_calendar_list = {
            c["id"]: c.get("summary", c["id"]) for c in cal_list.get("items", [])
        }
        return self._cached_calendar_list

    def init(self, port: int = 0) -> None:
        from google_auth_oauthlib.flow import InstalledAppFlow

        if not self.account.client_id or not self.account.client_secret:
            die(
                f"missing client_id/client_secret for '{self.account.name}'. "
                f"Edit {CONFIG_FILE}."
            )
        flow = InstalledAppFlow.from_client_config(
            {
                "installed": {
                    "client_id": self.account.client_id,
                    "client_secret": self.account.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            },
            scopes=SCOPES,
        )
        creds = flow.run_local_server(port=port, open_browser=True)
        self._save_creds(creds)
        print(f"Saved token to {self._token_path()}")

    def list_calendars(self) -> None:
        svc = self._service()
        result = svc.calendarList().list().execute()
        for cal in result.get("items", []):
            marker = " *" if cal.get("primary") else ""
            print(f"{cal['id']:<50}  {cal.get('summary', '')}{marker}")

    def list_events(self, start, end, calendars=None, all_calendars=False):
        svc = self._service()
        time_min = start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        time_max = end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        cal_names = self._select_calendars(
            self._calendar_list(), calendars, all_calendars
        )

        for cal_id, cal_name in cal_names.items():
            result = (
                svc.events()
                .list(
                    calendarId=cal_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=250,
                )
                .execute()
            )
            me = self.account.email.lower()
            for ev in result.get("items", []):
                response = ""
                for a in ev.get("attendees", []):
                    if a.get("self") or a.get("email", "").lower() == me:
                        response = a.get("responseStatus", "")
                        break
                if not response and ev.get("organizer", {}).get("self"):
                    response = "organizer"
                yield {
                    "id": ev["id"],
                    "title": ev.get("summary", "(no title)"),
                    "start": ev["start"].get("dateTime") or ev["start"].get("date"),
                    "end": ev["end"].get("dateTime") or ev["end"].get("date"),
                    "location": ev.get("location", ""),
                    "account": self.account.name,
                    "calendar": cal_id,
                    "calendar_name": cal_name,
                    "response": response,
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
        svc = self._service()
        cal_id = calendar or "primary"
        body: dict = {
            "summary": title,
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
            "reminders": {
                "useDefault": False,
                "overrides": (
                    [{"method": "popup", "minutes": reminder_minutes}]
                    if reminder_minutes > 0
                    else []
                ),
            },
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]
        kwargs = {"calendarId": cal_id, "body": body, "sendUpdates": "all"}
        if conferencing:
            body["conferenceData"] = {
                "createRequest": {
                    "requestId": str(uuid.uuid4()),
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            }
            kwargs["conferenceDataVersion"] = 1
        ev = svc.events().insert(**kwargs).execute()
        print(f"Created: {ev.get('htmlLink', ev['id'])}")
        if ev.get("hangoutLink"):
            print(f"Meet:    {ev['hangoutLink']}")

    def rsvp(self, event_id, response, calendar=None, comment=""):
        svc = self._service()
        cal_id = calendar or "primary"
        ev = svc.events().get(calendarId=cal_id, eventId=event_id).execute()
        me = self.account.email.lower()
        attendees = ev.get("attendees", [])
        for a in attendees:
            if a.get("self") or a.get("email", "").lower() == me:
                a["responseStatus"] = response
                if comment:
                    a["comment"] = comment
                elif "comment" in a:
                    del a["comment"]
                break
        else:
            die(f"you ({self.account.email}) are not an attendee on event {event_id}")
        svc.events().patch(
            calendarId=cal_id,
            eventId=event_id,
            body={"attendees": attendees},
            sendUpdates="all",
        ).execute()
        print(f"RSVP {response} on event {event_id}")

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
        svc = self._service()
        cal_id = calendar or "primary"
        body: dict = {}
        if title is not None:
            body["summary"] = title
        if start is not None:
            body["start"] = {"dateTime": start.isoformat()}
        if end is not None:
            body["end"] = {"dateTime": end.isoformat()}
        if location is not None:
            body["location"] = location
        if description is not None:
            body["description"] = description
        if attendees is not None:
            body["attendees"] = [{"email": a} for a in attendees]
        if reminder_minutes is not None:
            body["reminders"] = {
                "useDefault": False,
                "overrides": (
                    [{"method": "popup", "minutes": reminder_minutes}]
                    if reminder_minutes > 0
                    else []
                ),
            }
        if not body:
            print("(no changes)")
            return
        ev = (
            svc.events()
            .patch(
                calendarId=cal_id,
                eventId=event_id,
                body=body,
                sendUpdates="all",
            )
            .execute()
        )
        print(f"Updated: {ev.get('htmlLink', ev['id'])}")

    def quick_add(self, text, calendar=None):
        svc = self._service()
        cal_id = calendar or "primary"
        ev = (
            svc.events()
            .quickAdd(calendarId=cal_id, text=text, sendUpdates="all")
            .execute()
        )
        print(f"Created: {ev.get('htmlLink', ev['id'])}")
        if ev.get("hangoutLink"):
            print(f"Meet:    {ev['hangoutLink']}")

    def delete_event(self, event_id, calendar=None):
        svc = self._service()
        cal_id = calendar or "primary"
        svc.events().delete(
            calendarId=cal_id, eventId=event_id, sendUpdates="all"
        ).execute()
        print(f"Deleted event {event_id}")

    def get_event(self, event_id, calendar=None):
        from googleapiclient.errors import HttpError

        svc = self._service()
        ev = None
        cal_id = None
        candidates = [calendar] if calendar else None
        if candidates is None:
            candidates = ["primary"] + list(self._calendar_list().keys())
        for cid in candidates:
            try:
                ev = svc.events().get(calendarId=cid, eventId=event_id).execute()
                cal_id = cid
                break
            except HttpError as e:
                if e.resp.status in (404, 410):
                    continue
                raise
        if ev is None:
            die(f"event {event_id} not found on any calendar for '{self.account.name}'")

        me = self.account.email.lower()
        attendees = []
        for a in ev.get("attendees", []):
            email = a.get("email", "")
            attendees.append(
                {
                    "email": email,
                    "response": a.get("responseStatus", ""),
                    "self": bool(a.get("self")) or email.lower() == me,
                    "optional": bool(a.get("optional")),
                }
            )
        reminders = ev.get("reminders", {})
        reminder_min: int | None = None
        if not reminders.get("useDefault", True):
            for override in reminders.get("overrides", []):
                if override.get("method") == "popup":
                    reminder_min = override.get("minutes")
                    break
            else:
                reminder_min = 0  # explicit no-reminder
        return {
            "id": ev["id"],
            "title": ev.get("summary", "(no title)"),
            "start": ev["start"].get("dateTime") or ev["start"].get("date"),
            "end": ev["end"].get("dateTime") or ev["end"].get("date"),
            "location": ev.get("location", ""),
            "description": ev.get("description", ""),
            "organizer": ev.get("organizer", {}).get("email", ""),
            "attendees": attendees,
            "conferencing_link": ev.get("hangoutLink", ""),
            "html_link": ev.get("htmlLink", ""),
            "reminder_minutes": reminder_min,
            "account": self.account.name,
            "calendar": cal_id,
        }
