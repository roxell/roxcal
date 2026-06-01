" Syntax for the roxcal:// agenda buffer.

if exists('b:current_syntax')
    finish
endif

" Event lines, colored by RSVP status. Match the whole line if it contains
" a status bracket. The pattern is intentionally loose so it works even if
" the leading column format changes.
syntax match roxcalAccepted  /^.*\[+\].*$/
syntax match roxcalDeclined  /^.*\[-\].*$/
syntax match roxcalTentative /^.*\[\~\].*$/
syntax match roxcalPending   /^.*\[?\].*$/
syntax match roxcalOrganizer /^.*\[\*\].*$/

" Expanded section under an event: organizer line, meet/teams link,
" attendee lines and the | description prefix.
syntax match roxcalExpandLabel   /^\s\+\(Account\|Calendar\|Organizer\|Meet\/Teams\):/
syntax match roxcalDescriptionLn /^\s\+|.*/
syntax match roxcalAttendeeYou   /^\s\+\[.\]\s\+\S\+\s\+(you)/
syntax match roxcalAttendeeMark  /^\s\+\[+\]\s\+/ containedin=roxcalAccepted
syntax match roxcalUrl           /https\?:\/\/\S\+/ containedin=ALL

" Default highlights with explicit colors so they show up regardless of
" the user's colorscheme. Users can override any of these in .vimrc:
"
"   highlight roxcalAccepted ctermfg=Green guifg=#88c070
"
highlight default roxcalAccepted  ctermfg=Green    guifg=#88c070
highlight default roxcalDeclined  ctermfg=Red      guifg=#e07070
highlight default roxcalTentative ctermfg=Yellow   guifg=#d8c068
highlight default roxcalPending   ctermfg=Cyan     guifg=#80c0e0
highlight default roxcalOrganizer ctermfg=Magenta  guifg=#c890e0
highlight default roxcalPast      ctermfg=DarkGrey guifg=#808080

highlight default link roxcalExpandLabel   Label
highlight default link roxcalDescriptionLn Comment
highlight default link roxcalAttendeeYou   Special
highlight default link roxcalUrl           Underlined

let b:current_syntax = 'roxcal'
