"""Google Calendar over CalDAV with an app password.

Read access and personal events only. Google does not send invite emails for
events created via CalDAV, and no Meet links can be created here. Use this
backend only when OAuth is blocked but app passwords are allowed.
"""

from __future__ import annotations

import sys

from ..config import CONFIG_FILE, die
from .caldav import CalDAVBackend


class GoogleCalDAVBackend(CalDAVBackend):
    def _resolve_url(self, configured: str) -> str:
        url = configured.rstrip("/")
        if url.endswith("/caldav/v2"):
            if not self.account.email:
                die(
                    f"google_caldav account '{self.account.name}' needs email "
                    f"(used in the CalDAV URL). Edit {CONFIG_FILE}."
                )
            url = f"{url}/{self.account.email}/user"
        return url

    def _create_notices(self, *, conferencing: bool, attendees: bool) -> None:
        if conferencing:
            print(
                "note: Google CalDAV cannot create Meet links. Ignored.",
                file=sys.stderr,
            )
        if attendees:
            print(
                "note: Google CalDAV does not reliably send invite emails. "
                "Attendees added to the .ics but invitees may not be notified.",
                file=sys.stderr,
            )

    def _rsvp_outcome_note(self) -> str:
        return "RSVP via CalDAV (may not propagate to organizer)"

    def _auth_error_hint(self) -> str:
        return (
            "Google has dropped basic auth on CalDAV for personal @gmail.com. "
            "App passwords no longer work here. Use the google_oauth backend "
            "for this account instead."
        )
