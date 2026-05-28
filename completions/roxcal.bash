# bash completion for roxcal
# Source this file from ~/.bashrc or drop it in
# /usr/share/bash-completion/completions/roxcal

_roxcal() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    if [ "${COMP_CWORD}" -eq 1 ]; then
        local subs="add agenda calm calw colors conflicts delete edit import init list quick remind rsvp search show"
        COMPREPLY=($(compgen -W "${subs}" -- "${cur}"))
    fi
}
complete -F _roxcal roxcal
