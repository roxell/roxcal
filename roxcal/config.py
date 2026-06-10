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

NAMED_COLORS = {
    "black": 30,
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
    "white": 37,
    "bright_black": 90,
    "bright_red": 91,
    "bright_green": 92,
    "bright_yellow": 93,
    "bright_blue": 94,
    "bright_magenta": 95,
    "bright_cyan": 96,
    "bright_white": 97,
}

DEFAULT_COLORS = {
    "accepted": "\033[32m",
    "declined": "\033[31m",
    "tentative": "\033[33m",
    "needsAction": "\033[36m",
    "organizer": "\033[35m",
    "past": "\033[90m",
}

# TOML keys use snake_case but the events use the camelCase response strings
# from Google/Microsoft. Map between the two.
_COLOR_TOML_KEYS = {
    "accepted": "accepted",
    "declined": "declined",
    "tentative": "tentative",
    "needs_action": "needsAction",
    "organizer": "organizer",
    "past": "past",
}


def die(msg: str, code: int = 1) -> NoReturn:
    print(f"roxcal: {msg}", file=sys.stderr)
    sys.exit(code)


def _resolve_color(key: str, value) -> str:
    """Turn a user-supplied color value into an ANSI escape string.

    Accepts:
      "green" (named, 8/16-color)
      196     (int 0-255, ANSI 256-color palette)
      "#88c070" (truecolor 24-bit)
    """
    if isinstance(value, bool):
        die(f"color {key}: expected string or int 0-255, got bool")
    if isinstance(value, int):
        if not 0 <= value <= 255:
            die(f"color {key}={value}: integer must be 0-255")
        return f"\033[38;5;{value}m"
    if isinstance(value, str):
        if value.startswith("#"):
            hex_part = value[1:]
            if len(hex_part) != 6 or any(
                c not in "0123456789abcdefABCDEF" for c in hex_part
            ):
                die(f"color {key}={value!r}: hex color must be #rrggbb")
            r = int(hex_part[0:2], 16)
            g = int(hex_part[2:4], 16)
            b = int(hex_part[4:6], 16)
            return f"\033[38;2;{r};{g};{b}m"
        if value in NAMED_COLORS:
            return f"\033[{NAMED_COLORS[value]}m"
        die(
            f"color {key}={value!r}: unknown name. Try one of "
            f"{', '.join(sorted(NAMED_COLORS))} or a #rrggbb hex string."
        )
    die(f"color {key}: expected string or int 0-255, " f"got {type(value).__name__}")


@dataclass
class Account:
    name: str
    backend: str
    email: str = ""
    client_id: str = ""
    client_secret: str = ""
    tenant: str = "common"  # outlook
    caldav_url: str = ""  # google_caldav / nextcloud_caldav
    caldav_username: str = ""  # optional CalDAV login when it differs from email
    caldav_password: str = ""  # app password
    calendars: list[str] = field(default_factory=list)  # restrict to these IDs/names


@dataclass
class Config:
    default_account: str
    accounts: dict[str, Account] = field(default_factory=dict)
    color: str = "auto"  # auto | always | never
    colors: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_COLORS))
    # Original [colors] values as written in TOML (snake_case keys, raw
    # str/int). The 'colors' subcommand serializes this so the vim plugin
    # can apply the same palette without re-parsing config.toml.
    color_overrides: dict = field(default_factory=dict)


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
        elif backend == "outlook":
            acc.client_id = raw.get("client_id", "")
            acc.tenant = raw.get("tenant", "common")
        else:
            die(f"unknown backend '{backend}' for account '{name}'")
        acc.calendars = list(raw.get("calendars", []))
        accounts[name] = acc
    default_account = data.get("default_account", next(iter(accounts), ""))
    if default_account and default_account not in accounts:
        die(f"default_account '{default_account}' is not defined")
    color = data.get("color", "auto")
    if color not in ("auto", "always", "never"):
        die(f"color must be auto|always|never, got '{color}'")
    colors = dict(DEFAULT_COLORS)
    color_overrides: dict = {}
    for key, value in data.get("colors", {}).items():
        if key not in _COLOR_TOML_KEYS:
            die(
                f"unknown color key '{key}' in [colors]. "
                f"Known: {', '.join(_COLOR_TOML_KEYS)}"
            )
        colors[_COLOR_TOML_KEYS[key]] = _resolve_color(key, value)
        color_overrides[key] = value
    return Config(
        default_account=default_account,
        accounts=accounts,
        color=color,
        colors=colors,
        color_overrides=color_overrides,
    )


def bootstrap_config() -> None:
    """Create a fresh config.toml with example stanzas."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text("""\
# roxcal config. Edit by hand.

default_account = "roxell"

# Color output for 'agenda' and 'calw': auto | always | never. 'auto'
# colors when stdout is a TTY. NO_COLOR env var also disables color.
# color = "auto"

# Override the per-RSVP color scheme. Each value can be:
#   "green"     - named (black/red/green/yellow/blue/magenta/cyan/white,
#                 also bright_red, bright_green, ...)
#   196         - integer 0-255, ANSI 256-color palette
#   "#88c070"   - "#rrggbb" hex, truecolor (24-bit)
# [colors]
# accepted     = "green"
# declined     = "red"
# tentative    = "yellow"
# needs_action = "cyan"
# organizer    = "magenta"

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

# Outlook account (Azure App Registration: public client + Calendars.ReadWrite).
# [accounts.ms]
# backend = "outlook"
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
