# fish completion for roxcal
# Drop this file in ~/.config/fish/completions/ or
# /usr/share/fish/vendor_completions.d/

function __roxcal_no_subcommand
    set -l cmd (commandline -opc)
    test (count $cmd) -le 1
end

complete -c roxcal -f
complete -c roxcal -n __roxcal_no_subcommand -a add -d 'Create an event'
complete -c roxcal -n __roxcal_no_subcommand -a agenda -d 'Show events in a time range'
complete -c roxcal -n __roxcal_no_subcommand -a calm -d 'ASCII month grid'
complete -c roxcal -n __roxcal_no_subcommand -a calw -d 'ASCII week grid'
complete -c roxcal -n __roxcal_no_subcommand -a colors -d 'Emit the [colors] overrides as JSON'
complete -c roxcal -n __roxcal_no_subcommand -a conflicts -d 'Find overlapping events'
complete -c roxcal -n __roxcal_no_subcommand -a delete -d 'Delete an event'
complete -c roxcal -n __roxcal_no_subcommand -a edit -d 'Edit an event'
complete -c roxcal -n __roxcal_no_subcommand -a init -d 'OAuth or verify credentials'
complete -c roxcal -n __roxcal_no_subcommand -a list -d 'List calendars'
complete -c roxcal -n __roxcal_no_subcommand -a quick -d 'Natural-language event create'
complete -c roxcal -n __roxcal_no_subcommand -a remind -d 'Fire a command for upcoming events'
complete -c roxcal -n __roxcal_no_subcommand -a rsvp -d 'Respond to an invite'
complete -c roxcal -n __roxcal_no_subcommand -a search -d 'Search events by substring'
complete -c roxcal -n __roxcal_no_subcommand -a show -d 'Show full event detail'
