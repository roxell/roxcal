"""Microsoft Outlook calendar via the Graph API with OAuth."""

from __future__ import annotations

import os
from datetime import timezone
from pathlib import Path

from ..config import CONFIG_DIR, CONFIG_FILE, die
from . import Backend

SCOPES = ["Calendars.ReadWrite", "User.Read"]
GRAPH = "https://graph.microsoft.com/v1.0"


class MicrosoftGraphBackend(Backend):
    def __init__(self, account):
        super().__init__(account)
        self._cached_token: str | None = None
        self._cached_calendar_list: dict[str, str] | None = None

    def _cache_path(self) -> Path:
        return CONFIG_DIR / self.account.name / "msal_cache.json"

    def _msal_app(self):
        import msal

        cache = msal.SerializableTokenCache()
        path = self._cache_path()
        if path.exists():
            cache.deserialize(path.read_text())
        app = msal.PublicClientApplication(
            self.account.client_id,
            authority=f"https://login.microsoftonline.com/{self.account.tenant}",
            token_cache=cache,
        )
        return app, cache

    def _save_cache(self, cache) -> None:
        if not cache.has_state_changed:
            return
        path = self._cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(cache.serialize())
        os.chmod(path, 0o600)

    def _token(self) -> str:
        if self._cached_token is not None:
            return self._cached_token
        app, cache = self._msal_app()
        accounts = app.get_accounts()
        result = None
        if accounts:
            result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if not result or "access_token" not in result:
            die(
                f"no token for '{self.account.name}'. "
                f"Run `roxcal --account {self.account.name} init`."
            )
        self._save_cache(cache)
        self._cached_token = result["access_token"]
        return self._cached_token

    def _calendar_list(self) -> dict[str, str]:
        """Cached calendar id->name map for this backend instance."""
        if self._cached_calendar_list is not None:
            return self._cached_calendar_list
        data = self._api("GET", "/me/calendars")
        self._cached_calendar_list = {
            c["id"]: c.get("name", c["id"]) for c in data.get("value", [])
        }
        return self._cached_calendar_list

    def _api(self, method: str, path: str, **kwargs):
        import requests

        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._token()}"
        if "json" in kwargs:
            headers.setdefault("Content-Type", "application/json")
        url = f"{GRAPH}{path}" if path.startswith("/") else path
        r = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        if r.status_code >= 400:
            die(f"Graph API {r.status_code}: {r.text}")
        if r.status_code == 204 or not r.content:
            return None
        return r.json()

    def init(self, port: int = 0) -> None:
        if not self.account.client_id:
            die(f"missing client_id for '{self.account.name}'. Edit {CONFIG_FILE}.")
        app, cache = self._msal_app()
        kwargs: dict = {"prompt": "select_account"}
        if port:
            kwargs["port"] = port
        result = app.acquire_token_interactive(SCOPES, **kwargs)
        if "access_token" not in result:
            die(f"OAuth failed: {result.get('error_description', result)}")
        self._save_cache(cache)
        print(f"Saved token cache to {self._cache_path()}")

    def list_calendars(self) -> None:
        data = self._api("GET", "/me/calendars")
        for cal in data.get("value", []):
            marker = " *" if cal.get("isDefaultCalendar") else ""
            print(f"{cal['id']:<60}  {cal.get('name', '')}{marker}")

    def list_events(self, start, end, calendars=None, all_calendars=False):
        from urllib.parse import urlencode

        params = {
            "startDateTime": start.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "endDateTime": end.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "$orderby": "start/dateTime",
            "$top": "100",
        }

        cal_names = self._select_calendars(
            self._calendar_list(), calendars, all_calendars
        )

        for cal_id, cal_name in cal_names.items():
            data = self._api(
                "GET",
                f"/me/calendars/{cal_id}/calendarView?{urlencode(params)}",
                headers={"Prefer": 'outlook.timezone="UTC"'},
            )
            response_map = {
                "none": "",
                "organizer": "organizer",
                "tentativelyAccepted": "tentative",
                "accepted": "accepted",
                "declined": "declined",
                "notResponded": "needsAction",
            }
            for ev in data.get("value", []):
                start_dt = ev["start"]["dateTime"]
                if not start_dt.endswith("Z"):
                    start_dt += "Z"
                raw_resp = ev.get("responseStatus", {}).get("response", "")
                yield {
                    "id": ev["id"],
                    "ical_uid": ev.get("iCalUId", ""),
                    "title": ev.get("subject", "(no subject)"),
                    "start": start_dt,
                    "end": ev["end"]["dateTime"],
                    "location": ev.get("location", {}).get("displayName", ""),
                    "account": self.account.name,
                    "calendar": cal_id,
                    "calendar_name": cal_name,
                    "response": response_map.get(raw_resp, raw_resp),
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
        body: dict = {
            "subject": title,
            "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
            "isReminderOn": reminder_minutes > 0,
            "reminderMinutesBeforeStart": max(reminder_minutes, 0),
        }
        if description:
            body["body"] = {"contentType": "text", "content": description}
        if location:
            body["location"] = {"displayName": location}
        if attendees:
            body["attendees"] = [
                {"emailAddress": {"address": a}, "type": "required"} for a in attendees
            ]
        if conferencing:
            body["isOnlineMeeting"] = True
            body["onlineMeetingProvider"] = "teamsForBusiness"
        path = f"/me/calendars/{calendar}/events" if calendar else "/me/events"
        ev = self._api("POST", path, json=body)
        print(f"Created: {ev.get('webLink', ev['id'])}")
        if conferencing and ev.get("onlineMeeting", {}).get("joinUrl"):
            print(f"Teams:   {ev['onlineMeeting']['joinUrl']}")

    def rsvp(self, event_id, response, calendar=None, comment=""):
        action = {
            "accepted": "accept",
            "declined": "decline",
            "tentative": "tentativelyAccept",
        }.get(response)
        if not action:
            die(f"unknown rsvp response '{response}'")
        body: dict = {"sendResponse": True}
        if comment:
            body["comment"] = comment
        path = f"/me/events/{event_id}/{action}"
        self._api("POST", path, json=body)
        print(f"RSVP {response} on event {event_id}")

    def delete_event(self, event_id, calendar=None):
        self._api("DELETE", f"/me/events/{event_id}")
        print(f"Deleted event {event_id}")

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
        body: dict = {}
        if title is not None:
            body["subject"] = title
        if start is not None:
            body["start"] = {"dateTime": start.isoformat(), "timeZone": "UTC"}
        if end is not None:
            body["end"] = {"dateTime": end.isoformat(), "timeZone": "UTC"}
        if location is not None:
            body["location"] = {"displayName": location}
        if description is not None:
            body["body"] = {"contentType": "text", "content": description}
        if attendees is not None:
            body["attendees"] = [
                {"emailAddress": {"address": a}, "type": "required"} for a in attendees
            ]
        if reminder_minutes is not None:
            body["isReminderOn"] = reminder_minutes > 0
            body["reminderMinutesBeforeStart"] = max(reminder_minutes, 0)
        if not body:
            print("(no changes)")
            return
        ev = self._api("PATCH", f"/me/events/{event_id}", json=body)
        print(f"Updated: {ev.get('webLink', ev['id'])}")

    def get_event(self, event_id, calendar=None):
        ev = self._api("GET", f"/me/events/{event_id}")
        response_map = {
            "none": "",
            "organizer": "organizer",
            "tentativelyAccepted": "tentative",
            "accepted": "accepted",
            "declined": "declined",
            "notResponded": "needsAction",
        }
        me = self.account.email.lower()
        attendees = []
        for a in ev.get("attendees", []):
            addr = a.get("emailAddress", {}).get("address", "")
            raw = a.get("status", {}).get("response", "")
            attendees.append(
                {
                    "email": addr,
                    "response": response_map.get(raw, raw),
                    "self": addr.lower() == me,
                    "optional": a.get("type") == "optional",
                }
            )
        start_dt = ev["start"]["dateTime"]
        if not start_dt.endswith("Z"):
            start_dt += "Z"
        end_dt = ev["end"]["dateTime"]
        return {
            "id": ev["id"],
            "title": ev.get("subject", "(no subject)"),
            "start": start_dt,
            "end": end_dt,
            "location": ev.get("location", {}).get("displayName", ""),
            "description": (ev.get("body") or {}).get("content", ""),
            "organizer": ev.get("organizer", {})
            .get("emailAddress", {})
            .get("address", ""),
            "attendees": attendees,
            "conferencing_link": (ev.get("onlineMeeting") or {}).get("joinUrl", ""),
            "html_link": ev.get("webLink", ""),
            "reminder_minutes": (
                ev.get("reminderMinutesBeforeStart") if ev.get("isReminderOn") else 0
            ),
            "account": self.account.name,
            "calendar": calendar or "",
        }
