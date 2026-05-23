"""Nextcloud Calendar over CalDAV.

Unlike the Google CalDAV path, Nextcloud properly sends iMIP invite emails
to attendees and propagates RSVPs. The user provides an app password
generated under Settings -> Security -> Devices & sessions.
"""

from __future__ import annotations

import sys

from .caldav import CalDAVBackend


class NextcloudCalDAVBackend(CalDAVBackend):
    def _create_notices(self, *, conferencing: bool, attendees: bool) -> None:
        if conferencing:
            print(
                "note: roxcal does not attach Nextcloud Talk links to events.",
                file=sys.stderr,
            )
