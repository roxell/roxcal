# roxcal

Python CLI for Google Calendar and Outlook calendar.

Supports multiple accounts and four backends per account:

| Backend | Auth | Read | Create | Invite + email | Online meeting link |
|---|---|---|---|---|---|
| `google_oauth` | OAuth (Cloud Console) | yes | yes | yes | yes (Meet) |
| `google_caldav` | App password | yes | yes | no real invites | no |
| `outlook` | OAuth (Azure App Reg.) | yes | yes | yes | yes (Teams) |
| `nextcloud_caldav` | App password | yes | yes | yes (iMIP) | no |

## Install

### From source (development)

```bash
uv tool install --editable ~/src/roxcal/
```

Editable means source edits take effect immediately. To upgrade dependencies,
`uv tool upgrade roxcal`. To remove, `uv tool uninstall roxcal`.

### From a built wheel (end users)

Build the wheel and sdist:

```bash
cd ~/src/roxcal
make dist
```

Artifacts land in `dist/`:

```
dist/roxcal-<version>-py3-none-any.whl
dist/roxcal-<version>.tar.gz
```

Install the wheel anywhere:

```bash
uv tool install dist/roxcal-0.1.0-py3-none-any.whl
# or
pipx install dist/roxcal-0.1.0-py3-none-any.whl
# or
pip install --user dist/roxcal-0.1.0-py3-none-any.whl
```

The wheel ships only the Python CLI. The vim plugin is **not** in the wheel
(pip is the wrong vehicle for vim plugins); see the [Vim plugin](#vim-plugin)
section below for how to install that.

### Vim plugin only

If you just want the vim integration on a machine that already has `roxcal`
on `$PATH`, point your plugin manager at this repo. With vim-plug:

```vim
Plug 'file:///home/anders/src/roxcal'   " local clone
" or, once published somewhere:
Plug 'aroxell/roxcal'                   " hypothetical github
```

Then `:PlugInstall`. The plugin manager handles vim's runtimepath for you,
which picks up both `plugin/roxcal.vim` and `syntax/roxcal.vim`.

Manual install without a plugin manager:

```bash
mkdir -p ~/.vim/plugin ~/.vim/syntax
ln -s ~/src/roxcal/plugin/roxcal.vim ~/.vim/plugin/roxcal.vim
ln -s ~/src/roxcal/syntax/roxcal.vim ~/.vim/syntax/roxcal.vim
```

### Packages (deb/rpm/Arch)

The Makefile inherits build targets from `tuxpkg`:

```bash
make deb    # debian/.deb
make rpm    # rpm package
make pkg    # Arch Linux .pkg.tar.zst
```

Metadata is already in `debian/`, `roxcal.spec`, and `roxcal.PKGBUILD`. The
defaults assume the wheel from `make dist` and dependencies pulled from each
distro's Python package set. The Arch package also installs the vim plugin
files into `/usr/share/vim/vimfiles/`.

Backends are loaded on demand. An account that does not use a backend
never imports its heavy dependencies (`msal`, `caldav`, etc.).

## Runtime files

| Path | Purpose |
|---|---|
| `~/.local/bin/roxcal` | Installed entry point. |
| `~/.config/roxcal/config.toml` | Account definitions and credentials. Mode 600. |
| `~/.gcalcli/<account>/oauth_creds` | Google OAuth token for an account. |
| `~/.config/roxcal/<account>/msal_cache.json` | Outlook token cache. |

## First-time setup

### Common

The script self-generates `~/.config/roxcal/config.toml` on first run with
example stanzas.

Edit the file. Two account stubs (`roxell` and `linaro`) are pre-defined
with the `google_oauth` backend.

### Google account (OAuth)

1. Create an OAuth client in Google Cloud Console
   (<https://console.cloud.google.com/apis/credentials/oauthclient>,
   Application type = Desktop). Enable the Calendar API and add yourself
   as a test user on the consent screen.
2. Put `client_id` and `client_secret` in `[google_shared]` in
   `config.toml`, or per-account inside `[accounts.<name>]`.
3. Run:
   ```bash
   roxcal --account roxell init
   ```
   Browser opens. Sign in as the matching Google account. You will see
   "Google hasn't verified this app" — click **Advanced → Go to
   `<your app name>` (unsafe) → Allow**. Token is saved to
   `~/.gcalcli/<account>/oauth_creds` (mode 600).

### Google account (CalDAV with app password)

Use this when a Workspace admin blocks OAuth but allows app passwords.
Read access only — Google does not send invite emails for events
created via CalDAV, and no Meet links.

1. Generate an app password at <https://myaccount.google.com/apppasswords>.
   If the page says "not available for your account", admin disabled it.
2. Add an account stanza:
   ```toml
   [accounts.linaro_caldav]
   backend = "google_caldav"
   email = "anders.roxell@linaro.org"
   caldav_password = "xxxx xxxx xxxx xxxx"
   ```
3. Verify:
   ```bash
   roxcal --account linaro_caldav init
   ```

### Microsoft account (Graph API)

1. Register an app at
   <https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/CreateApplicationBlade>:
   - Supported account types: pick what matches (personal, work, or both).
   - Redirect URI: Public client / native → `http://localhost`.
   - API permissions → Microsoft Graph → Delegated →
     `Calendars.ReadWrite` and `User.Read`.
   - No client secret needed (public client).
2. Copy the **Application (client) ID**.
3. Add an account stanza:
   ```toml
   [accounts.ms]
   backend = "outlook"
   email = "you@example.com"
   client_id = "..."
   tenant = "common"     # or your tenant id for a work account
   ```
4. Run:
   ```bash
   roxcal --account ms init
   ```

### Nextcloud account (CalDAV)

Nextcloud Calendar uses CalDAV with an app password. Unlike the Google
CalDAV path, Nextcloud does send proper iMIP invite emails to attendees.

1. In Nextcloud, go to Settings → Security → Devices & sessions →
   **Create new app password**. Copy the 25-character token.
2. Add an account stanza:
   ```toml
   [accounts.cloud]
   backend = "nextcloud_caldav"
   email = "anders@example.com"
   caldav_url = "https://cloud.example.com/remote.php/dav/"
   # caldav_username = "anders"   # optional; defaults to email
   caldav_password = "xxxxx-xxxxx-xxxxx-xxxxx-xxxxx"
   ```
3. Verify:
   ```bash
   roxcal --account cloud init
   ```

## Daily use

```bash
# Default account agenda for today
roxcal agenda

# Specific account
roxcal --account linaro agenda
roxcal --account ms agenda "today" "+7d"

# Merged across all accounts, time-sorted
roxcal agenda --all

# List calendars
roxcal --account roxell list

# Create event
roxcal --account roxell add \
    --title "Sync with Maria" \
    --when "2026-05-21 14:00" \
    --duration 30

# Create a meeting with attendees and a Meet/Teams link
roxcal --account ms add \
    --title "Design review" \
    --when "tomorrow 10:00" \
    --duration 1h \
    --attendees maria@example.com,peter@example.com \
    --meet \
    --where "Online"

# Get event ids to RSVP against
roxcal agenda --ids

# Find overlapping events (double-bookings)
roxcal conflicts --all

# Accept / decline
roxcal --account ms rsvp <event-id> accepted
roxcal --account linaro rsvp <event-id> declined
roxcal --account ms rsvp <event-id> tentative

# Search across all accounts (past year + next year by default)
roxcal search "standup" --all
roxcal search "lunch with maria" 2026-01-01 2026-12-31
```

Time inputs accept:
- ISO: `2026-05-21 14:00`, `2026-05-21T14:00`
- Keywords: `now`, `today`, `tomorrow`
- Offsets: `+30m`, `+2h`, `+3d`
- Anything `python-dateutil` can parse.

Durations: `30m`, `1h`, `2h30m`.

## Reminders (cron / systemd)

`roxcal remind` fires a command for each event starting within a
look-ahead window. Designed to be called from cron or a user systemd
timer to push desktop notifications via `notify-send`.

Quick check (print upcoming events, do nothing else):

```bash
roxcal remind 10
```

Dry-run a notification template (prints the command without running):

```bash
roxcal remind 10 'notify-send "{title}" "{start} — {location}"' --dry-run
```

Available placeholders: `{title}`, `{start}` (HH:MM), `{start_full}`
(YYYY-MM-DD HH:MM), `{location}`, `{account}`, `{minutes}`. Each
token in the template becomes one argv entry (parsed with `shlex`)
so no shell-injection risk.

**Pick a window equal to your trigger interval.** If cron runs every 5
minutes, use `remind 5`; otherwise each event notifies twice.

### user systemd timer (recommended)

The user systemd unit inherits your graphical session env, so
`notify-send` finds `DISPLAY` and `DBUS_SESSION_BUS_ADDRESS`
automatically.

`~/.config/systemd/user/roxcal-remind.service`:

```ini
[Unit]
Description=roxcal upcoming event reminder

[Service]
Type=oneshot
ExecStart=/bin/sh -c '%h/.local/bin/roxcal remind 5 --all "notify-send \"{title}\" \"{start} — {location}\""'
```

Wrapping in `/bin/sh -c` keeps the template (with its `{...}`
placeholders) intact — systemd's own argument parsing would otherwise
split on quotes.

`~/.config/systemd/user/roxcal-remind.timer`:

```ini
[Unit]
Description=roxcal reminder every 5 minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
```

Enable:

```bash
systemctl --user daemon-reload
systemctl --user enable --now roxcal-remind.timer
systemctl --user list-timers roxcal-remind.timer
```

### cron

cron has no graphical session env, so you have to inject it. With
modern systemd-logind:

```cron
*/5 * * * * DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus \
    /home/$(whoami)/.local/bin/roxcal remind 5 --all \
    'notify-send "{title}" "{start} — {location}"'
```

(Use the absolute path to `roxcal` — cron's `$PATH` does not include
`~/.local/bin`.)

The user systemd timer is generally less brittle than cron for desktop
notifications.

## Subcommands

```bash
roxcal --help                  # list of subcommands
roxcal <command> --help        # flags for a specific subcommand
```

## Shell completions

`completions/` ships small completion files for bash, zsh and fish. The
Arch package installs them automatically. Manual install:

```bash
# bash
mkdir -p ~/.local/share/bash-completion/completions
cp completions/roxcal.bash ~/.local/share/bash-completion/completions/roxcal

# zsh (file must be on $fpath, name must be _roxcal)
mkdir -p ~/.zsh/completions
cp completions/roxcal.zsh ~/.zsh/completions/_roxcal
# in ~/.zshrc, before compinit:
#   fpath=(~/.zsh/completions $fpath)

# fish
cp completions/roxcal.fish ~/.config/fish/completions/roxcal.fish
```

After install, `roxcal <Tab>` completes the subcommand name.

## Mail-client handler for .ics attachments

`data/applications/roxcal-import.desktop` registers roxcal as a
handler for `text/calendar` files. Clicking an `.ics` attachment in
Thunderbird, Evolution or any freedesktop-aware mail client then runs
`roxcal import <file> --notify`, which adds the event to your default
account and fires a `notify-send`.

The Arch package installs the `.desktop` file. Manual install:

```bash
mkdir -p ~/.local/share/applications
cp data/applications/roxcal-import.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications
```

Make it the default for `text/calendar`:

```bash
xdg-mime default roxcal-import.desktop text/calendar
xdg-mime default roxcal-import.desktop application/ics
```

Verify:

```bash
xdg-mime query default text/calendar
```

The handler imports to the default account's primary calendar. To pick
a different account or calendar, edit the `Exec=` line in the
`.desktop` file (e.g. `roxcal --account work import %f --calendar Team
--notify`).

## Vim plugin

A vim plugin lives at `plugin/roxcal.vim`. It opens an interactive scratch
buffer with your agenda, expands meeting details inline, and RSVPs without
leaving vim. All heavy lifting goes through the roxcal CLI; the plugin is a
thin wrapper that reads `--json` output.

### `~/.vimrc` setup

Drop this block into your `~/.vimrc`:

```vim
" --- roxcal ------------------------------------------------------------
syntax on
filetype plugin on

" Pick one for the plugin path:
set runtimepath+=~/src/roxcal
" or symlink: ln -s ~/src/roxcal/plugin/roxcal.vim ~/.vim/plugin/
" or vim-plug: Plug '~/src/roxcal'

" Pick one for how the plugin calls the CLI:
let g:roxcal_command = 'roxcal'
" or absolute path:
" let g:roxcal_command = '/home/anders/.local/bin/roxcal'
" or via uv (dev workflow against this repo):
" let g:roxcal_command = ['uv', 'run', '--project', expand('~/src/roxcal'), 'roxcal']

" Optional shortcuts:
nnoremap <silent> <leader>ga :RoxcalAgenda<CR>
nnoremap <silent> <leader>gn :RoxcalAdd<CR>
" -----------------------------------------------------------------------
```

Restart vim. Verify with `:scriptnames | grep roxcal` — both `plugin/roxcal.vim`
and `syntax/roxcal.vim` should be listed.

The `g:roxcal_command` setting may be a string (one binary) or a list
(used as the command prefix verbatim).

### Commands

| Command | Purpose |
|---|---|
| `:RoxcalAgenda [args]` | Open a scratch buffer with events. No args → `agenda --all --json`. Extra args pass through to `roxcal agenda`. |
| `:RoxcalSearch [args]` | Search across all accounts. Without args, prompts with `Search: `. Args pass through to `roxcal search`, so `:RoxcalSearch --full sprint` widens the match to description and attendees. Same buffer mappings as the agenda. |
| `:RoxcalConflicts [args]` | Show overlapping events grouped by cluster. No args → `conflicts --all`. Buffer mappings work on event lines; cluster headers are no-ops. |
| `:RoxcalAdd [account]` | Open a buffer to compose a new event. See [Creating an event](#creating-an-event-from-vim) below. |
| `:RoxcalReload` | Reload the current roxcal buffer. |

Examples:

```vim
:RoxcalAgenda                                  " all accounts, next 7 days
:RoxcalAgenda --account linaro -D 14          " linaro only, 14 days
:RoxcalAgenda --all --all-calendars           " every calendar, all accounts
:RoxcalAgenda --account roxell -c anders@roxell.se
```

### Buffer mappings

Inside the `roxcal://agenda` buffer:

| Key  | Action |
|------|--------|
| `<CR>` | Toggle inline expansion (account, calendar, organizer, Meet/Teams link, attendees with response status, description body). |
| `a`    | RSVP **accepted** on the event under the cursor. Buffer reloads. |
| `d`    | RSVP **declined**. |
| `t`    | RSVP **tentative**. |
| `<leader>a`/`<leader>d`/`<leader>t` | Open a `roxcal://rsvp` buffer where you type a (possibly multi-line) message for the organizer. `:w` sends, `q`/`:bd!` cancels. Equivalent to `:RoxcalReply accepted` / `declined` / `tentative` from the agenda buffer. |
| `D`    | Delete the event (with confirmation). Cancels for all attendees if you organized it. |
| `E`    | Edit the event in a pre-filled buffer. Submit with `:w` or `<leader>cc`. |
| `gd`   | Show full detail in a horizontal split (`q` to close, `E` to switch to edit). |
| `c`    | Toggle compact (hide `[account]` and `[calendar]` columns). Set `g:roxcal_compact = 1` for default-on. |
| `A`    | Toggle hiding all-day events (birthdays, OOO, holidays). Set `g:roxcal_hide_all_day = 1` for default-on. |
| `za` / `zM` / `zR` | Toggle / close all / open all day folds. Each day in the agenda is one fold; each cluster in `:RoxcalConflicts` is one fold. Open by default. |
| `r`    | Reload the buffer from roxcal. |
| `q`    | Close the buffer. |
| `?`    | Show the cheat-sheet in the command line. |

In any vim buffer you can also list every buffer-local mapping with
`:nmap <buffer>`. Inside `roxcal://agenda` that prints the same set of
keys with the underlying function calls.

### Creating an event from vim

```vim
:RoxcalAdd                  " default account
:RoxcalAdd linaro           " linaro account
:RoxcalAdd roxell           " roxell account
```

Opens a `roxcal://add` buffer with a templated form:

```
Account: linaro
Title: 
When: tomorrow 10:00
Duration: 30m
Attendees: 
Calendar: 
Where: 
Meet: no
Description:

```

Edit the fields. Everything after `Description:` (until end of buffer) becomes
the event description, so you can write multiple lines freely.

| Field | Notes |
|---|---|
| Account | Optional override. Defaults to whatever was on the command line. |
| Title | **Required.** |
| When | **Required.** ISO, `tomorrow 10:00`, `+2h`, etc. |
| Duration | `30m`, `1h`, `2h30m`. |
| Attendees | Comma-separated emails. |
| Calendar | Calendar id/name. Leave empty for primary. |
| Where | Location. |
| Meet | `yes` / `no` (or `y` / `1` / `true`) to attach a Google Meet / Teams link. |
| Reminder | Popup reminder N minutes before start. Default `10`. Set `0` for no reminder. |
| Description | Free-form text, can span multiple lines. |

Submit with `:w` (or `:wq`) or the mapping `<leader>cc`. The plugin asks
**`Create event "<title>"? (Y/n)`** before sending anything to roxcal — a
stray `:w` cannot accidentally create an event. Cancel with `q` or `:bd!`.
Press `?` for the in-buffer cheat-sheet. On success the buffer closes and
any open `roxcal://agenda` buffer reloads so you see the new event.

The same confirmation prompt appears when you submit a `:RoxcalEdit`
buffer (`Apply changes to event "<title>"?`).

### Response status symbols

The first column in each line shows your RSVP state:

| Symbol | Meaning |
|---|---|
| `+` | accepted |
| `?` | not yet answered (needsAction) |
| `~` | tentative |
| `-` | declined |
| `*` | you are organizer |
| (space) | no info or you are not invited |

### Colors

Colors work out of the box — no `~/.vimrc` changes needed. The plugin
ships a `syntax/roxcal.vim` that colors each event line by its RSVP state
and links the groups to standard highlight names (`String`, `ErrorMsg`,
`WarningMsg`, …) that every colorscheme defines. Whatever your
colorscheme uses for those names is what the agenda uses too.

Only read the override section below if you actively dislike the
defaults under your colorscheme.

The groups and their default links:

| Group | Default link | What it covers |
|---|---|---|
| `gcalAccepted` | `String` | events with `[+]` |
| `gcalDeclined` | `ErrorMsg` | events with `[-]` |
| `gcalTentative` | `WarningMsg` | events with `[~]` |
| `gcalPending` | `Question` | events with `[?]` |
| `gcalOrganizer` | `Identifier` | events you organize `[*]` |
| `gcalExpandLabel` | `Label` | `Organizer:`, `Meet/Teams:` in expanded view |
| `gcalDescriptionLn` | `Comment` | description body lines (`|` prefix) |
| `gcalAttendeeYou` | `Special` | the attendee line marked `(you)` |
| `gcalUrl` | `Underlined` | http(s) URLs anywhere |

**Override (optional)** — easiest: put a `[colors]` table in
`~/.config/roxcal/config.toml` and the vim plugin will pick it up too.
The first time `:RoxcalAgenda` opens it runs `roxcal colors` and applies
each override as a `highlight` command (int → `ctermfg=N`, `#rrggbb` →
`guifg=#rrggbb`, name → `ctermfg=name`).

If you'd rather keep colors purely vim-side, put `highlight` lines in
`~/.vimrc` instead:

```vim
highlight gcalAccepted   ctermfg=Green   guifg=#88c070
highlight gcalDeclined   ctermfg=Red     guifg=#e07070
highlight gcalTentative  ctermfg=Yellow  guifg=#d8c068
highlight gcalPending    ctermfg=Cyan    guifg=#80c0e0
highlight gcalOrganizer  ctermfg=Magenta guifg=#c890e0
```

Set those *after* sourcing your colorscheme, or wrap them in a
`ColorScheme` autocmd so they survive `:colorscheme` changes.

### Troubleshooting

- **`E492: Not an editor command: RoxcalAgenda`** — plugin not loaded.
  Run `:scriptnames | grep roxcal` to confirm. If empty, check that
  `~/src/roxcal/plugin/roxcal.vim` exists and that `~/src/roxcal` is on vim's
  runtimepath, or that the file is symlinked into `~/.vim/plugin/`.
- **`roxcal failed: ...`** in the echo line — the underlying CLI errored.
  Run the same command in a shell to see the full message.
- **`roxcal returned invalid JSON`** — you may have run a command that
  prints a non-JSON message (e.g., `init`) through the plugin. Stick to
  `agenda` and `show` arguments.

## Troubleshooting

**`unknown account 'foo'`**
The account name is not in `~/.config/roxcal/config.toml`. Add a stanza
or use a defined one.

**`no token for '<account>'`**
You have not run `init` for that account yet.

**`Access blocked: gcalcli has not completed the Google verification process`**
The Workspace admin disabled third-party OAuth. Either ask IT for an
internal client (put it in per-account `client_id`/`client_secret`) or
switch that account to the `google_caldav` backend if app passwords
are allowed.

**Token broken / want to re-login**
Delete the token file and re-run init:
```bash
rm ~/.gcalcli/<account>/oauth_creds            # Google
rm ~/.config/roxcal/<account>/msal_cache.json    # Microsoft
roxcal --account <account> init
```

**Upgrade dependencies**
`uv` caches the script's venv. To force a refresh:
```bash
uv cache clean
```

## Development

Install the dev tools once:

```bash
uv sync --group dev
```

Then:

```bash
uv run make            # typecheck (mypy) + style (black) + lint (flake8)
uv run make test       # pytest with coverage report
make dist              # build wheel + sdist into dist/
```

The test suite mocks every backend and the OAuth flow so no live API
call is made. Coverage gates can be raised by setting
`TUXPKG_MIN_COVERAGE` in the `Makefile`.

## Removing the setup

```bash
rm -rf ~/.gcalcli ~/.config/roxcal ~/src/roxcal ~/.local/bin/roxcal
```

You can also revoke the OAuth client in Google Cloud Console / Azure
Entra if you do not plan to use it again.
