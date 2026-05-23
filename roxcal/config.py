"""Paths, account model, config loading."""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "roxcal"
CONFIG_FILE = CONFIG_DIR / "config.toml"
GCALCLI_TOKEN_ROOT = Path.home() / ".gcalcli"


def die(msg: str, code: int = 1) -> NoReturn:
    print(f"roxcal: {msg}", file=sys.stderr)
    sys.exit(code)


@dataclass
class Account:
    name: str
    backend: str
    email: str = ""
    client_id: str = ""
    client_secret: str = ""
    tenant: str = "common"  # microsoft_graph
    caldav_url: str = ""  # google_caldav / nextcloud_caldav
    caldav_username: str = ""  # optional CalDAV login when it differs from email
    caldav_password: str = ""  # app password
    calendars: list[str] = field(default_factory=list)  # restrict to these IDs/names


@dataclass
class Config:
    default_account: str
    accounts: dict[str, Account] = field(default_factory=dict)


def load_config() -> Config:
    if not CONFIG_FILE.exists():
        bootstrap_config()
    data = tomllib.loads(CONFIG_FILE.read_text())
    shared = data.get("google_shared", {})
    accounts: dict[str, Account] = {}
    for name, raw in data.get("accounts", {}).items():
        backend = raw.get("backend", "google_oauth")
        acc = Account(name=name, backend=backend, email=raw.get("email", ""))
        if backend == "google_oauth":
            acc.client_id = raw.get("client_id") or shared.get("client_id", "")
            acc.client_secret = raw.get("client_secret") or shared.get(
                "client_secret", ""
            )
        elif backend == "google_caldav":
            acc.caldav_url = raw.get(
                "caldav_url", "https://apidata.googleusercontent.com/caldav/v2/"
            )
            acc.caldav_username = raw.get("caldav_username", "")
            acc.caldav_password = raw.get("caldav_password", "")
        elif backend == "nextcloud_caldav":
            acc.caldav_url = raw.get("caldav_url", "")
            acc.caldav_username = raw.get("caldav_username", "")
            acc.caldav_password = raw.get("caldav_password", "")
        elif backend == "microsoft_graph":
            acc.client_id = raw.get("client_id", "")
            acc.tenant = raw.get("tenant", "common")
        else:
            die(f"unknown backend '{backend}' for account '{name}'")
        acc.calendars = list(raw.get("calendars", []))
        accounts[name] = acc
    default_account = data.get("default_account", next(iter(accounts), ""))
    if default_account and default_account not in accounts:
        die(f"default_account '{default_account}' is not defined")
    return Config(default_account=default_account, accounts=accounts)


def bootstrap_config() -> None:
    """Create a fresh config.toml with example stanzas."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text("""\
# roxcal config. Edit by hand.

default_account = "roxell"

# Shared Google OAuth client (used by any google_oauth account that does not
# override client_id/client_secret).
[google_shared]
client_id = ""
client_secret = ""

[accounts.roxell]
backend = "google_oauth"
email = "anders@roxell.se"

[accounts.linaro]
backend = "google_oauth"
email = "anders.roxell@linaro.org"
# Uncomment when Linaro IT provides its own OAuth client:
# client_id = ""
# client_secret = ""

# Alternative: CalDAV with a Google app password (read + personal events only,
# no proper invites, no Meet links). Only works if Workspace admin allowed it.
# [accounts.linaro_caldav]
# backend = "google_caldav"
# email = "anders.roxell@linaro.org"
# caldav_password = "xxxx xxxx xxxx xxxx"

# Microsoft Graph account (Azure App Registration: public client + Calendars.ReadWrite).
# [accounts.ms]
# backend = "microsoft_graph"
# email = "you@example.com"
# client_id = ""        # Application (client) ID from Azure
# tenant = "common"     # or your tenant id

# Nextcloud calendar via CalDAV. Generate an app password under
# Settings -> Security -> Devices & sessions.
# [accounts.cloud]
# backend = "nextcloud_caldav"
# email = "anders@example.com"
# caldav_url = "https://cloud.example.com/remote.php/dav/"
# caldav_username = "anders"   # optional; defaults to email if omitted
# caldav_password = "xxxxx-xxxxx-xxxxx-xxxxx-xxxxx"
""")
    os.chmod(CONFIG_FILE, 0o600)
    print(
        f"Wrote {CONFIG_FILE}. Edit it, then run `roxcal --account <name> init`.",
        file=sys.stderr,
    )
