"""Backend interface and dispatcher.

Each backend module exposes a single class implementing the Backend protocol.
Backends are loaded on demand so that an account that does not use a backend
never imports its heavy dependencies (msal, caldav, googleapiclient, etc.).
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from ..config import Account, die


class Backend:
    def __init__(self, account: Account) -> None:
        self.account = account

    def _select_calendars(
        self,
        available: dict[str, str],
        requested: list[str] | None,
        all_calendars: bool,
    ) -> dict[str, str]:
        """Apply the calendar-selection precedence and drop entries the
        account cannot see.

        Precedence (highest first):
          1. Explicit `requested` (from --calendar on the CLI)
          2. `account.calendars` (per-account config)  unless `all_calendars`
          3. Everything in `available`

        Calendars not present in `available` are silently skipped to keep
        roxcal agenda --all working when one account doesn't share a
        calendar another account has.
        """
        if requested:
            ids = requested
        elif self.account.calendars and not all_calendars:
            ids = self.account.calendars
        else:
            return dict(available)
        return {cid: available[cid] for cid in ids if cid in available}

    def init(self, port: int = 0) -> None:
        raise NotImplementedError

    def list_calendars(self) -> None:
        raise NotImplementedError

    def list_events(
        self,
        start: datetime,
        end: datetime,
        calendars: list[str] | None = None,
        all_calendars: bool = False,
    ) -> Iterable[dict]:
        raise NotImplementedError

    def create_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        attendees: list[str] | None = None,
        conferencing: bool = False,
        calendar: str | None = None,
        description: str = "",
        location: str = "",
        reminder_minutes: int = 10,
    ) -> None:
        raise NotImplementedError

    def rsvp(
        self,
        event_id: str,
        response: str,
        calendar: str | None = None,
        comment: str = "",
    ) -> None:
        raise NotImplementedError

    def get_event(self, event_id: str, calendar: str | None = None) -> dict:
        raise NotImplementedError

    def delete_event(self, event_id: str, calendar: str | None = None) -> None:
        raise NotImplementedError

    def quick_add(self, text: str, calendar: str | None = None) -> None:
        """Create an event from a natural-language string. Backend-specific:
        Google has events.quickAdd; other backends fail with a clear note."""
        die(f"quick is not supported by the {self.account.backend} backend")

    def update_event(
        self,
        event_id: str,
        calendar: str | None = None,
        *,
        title: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        attendees: list[str] | None = None,
        location: str | None = None,
        description: str | None = None,
        reminder_minutes: int | None = None,
    ) -> None:
        raise NotImplementedError


def make_backend(account: Account) -> Backend:
    if account.backend == "google_oauth":
        from .google_oauth import GoogleOAuthBackend

        return GoogleOAuthBackend(account)
    if account.backend == "google_caldav":
        from .google_caldav import GoogleCalDAVBackend

        return GoogleCalDAVBackend(account)
    if account.backend == "nextcloud_caldav":
        from .nextcloud_caldav import NextcloudCalDAVBackend

        return NextcloudCalDAVBackend(account)
    if account.backend == "microsoft_graph":
        from .microsoft_graph import MicrosoftGraphBackend

        return MicrosoftGraphBackend(account)
    die(f"unknown backend '{account.backend}'")
