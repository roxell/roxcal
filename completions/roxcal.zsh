#compdef roxcal
# zsh completion for roxcal
# Drop this file in any directory on your $fpath as _roxcal, e.g.
#   /usr/share/zsh/site-functions/_roxcal

_roxcal() {
    local -a subs
    subs=(
        'add:Create an event'
        'agenda:Show events in a time range'
        'calm:ASCII month grid'
        'calw:ASCII week grid'
        'colors:Emit the user [colors] overrides as JSON'
        'conflicts:Find overlapping events (double-bookings)'
        'delete:Delete an event'
        'edit:Update fields of an event'
        'import:Add events from a .ics file'
        'init:Run OAuth or verify credentials for the account'
        'list:List calendars on the account'
        'quick:Create an event from a natural-language string'
        'remind:Fire a command for events about to start'
        'rsvp:Respond to an invite'
        'search:Search events by substring'
        'show:Show full detail of one event'
    )
    if (( CURRENT == 2 )); then
        _describe 'roxcal subcommand' subs
    fi
}

_roxcal "$@"
