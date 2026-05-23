" roxcal.vim - vim integration for the roxcal CLI.
"
" Commands:
"   :RoxcalAgenda [agenda args]   open a scratch buffer with the agenda.
"                                 No args  ->  'agenda --all --json'.
"                                 Extra args are passed to roxcal verbatim, e.g.
"                                   :RoxcalAgenda --account linaro -D 14
"   :RoxcalAdd [account]          compose a new event in a buffer.
"   :RoxcalReload                 reload the current roxcal buffer.
"
" Buffer-local mappings (inside the roxcal://agenda buffer):
"   <CR>   toggle inline expansion (organizer, meet link, attendees, body)
"   a      RSVP accepted
"   d      RSVP declined
"   t      RSVP tentative
"   D      delete event (asks first)
"   gd     show full detail in a horizontal split
"   r      reload
"   q      close
"   ?      this help
"
" The roxcal command is resolved via g:roxcal_command. It may be either:
"   - a string with the binary name or absolute path:
"       let g:roxcal_command = 'roxcal'
"       let g:roxcal_command = '/home/anders/.local/bin/roxcal'
"   - a list, used as the command prefix (passed verbatim with each call):
"       let g:roxcal_command = ['uv', 'run', '--project', '/home/anders/src/gcal', 'roxcal']

if exists('g:loaded_roxcal_plugin')
    finish
endif
let g:loaded_roxcal_plugin = 1

if !exists('g:roxcal_command')
    let g:roxcal_command = 'roxcal'
endif

let s:response_symbol = {'accepted': '+', 'declined': '-', 'tentative': '~', 'needsAction': '?', 'organizer': '*'}

function! s:shellcmd(args) abort
    let prefix = type(g:roxcal_command) == v:t_list ? copy(g:roxcal_command) : [g:roxcal_command]
    return join(map(prefix + a:args, 'shellescape(v:val)'), ' ')
endfunction

function! s:run_json(args) abort
    let out = system(s:shellcmd(a:args))
    if v:shell_error
        echohl ErrorMsg
        echom 'roxcal failed: ' . out
        echohl None
        return v:null
    endif
    try
        return json_decode(out)
    catch
        echohl ErrorMsg
        echom 'roxcal returned invalid JSON'
        echohl None
        return v:null
    endtry
endfunction

function! s:run_action(args) abort
    let out = system(s:shellcmd(a:args))
    if v:shell_error
        echohl ErrorMsg
        echom 'roxcal failed: ' . out
        echohl None
        return 0
    endif
    return 1
endfunction

function! s:fmt_event(ev) abort
    let r = get(s:response_symbol, get(a:ev, 'response', ''), ' ')
    let start = strpart(get(a:ev, 'start', ''), 0, 16)
    let acct = get(a:ev, 'account', '?')
    let cal = !empty(get(a:ev, 'calendar_name', '')) ? a:ev.calendar_name : get(a:ev, 'calendar', '')
    let title = get(a:ev, 'title', '(no title)')
    let location = get(a:ev, 'location', '')
    let loc = !empty(location) ? '  @ ' . location : ''
    return printf('  %-16s  [%s]  [%s]  [%s]  %s%s', start, r, acct, cal, title, loc)
endfunction

function! s:render(events) abort
    setlocal modifiable
    silent %delete _
    let b:roxcal_events = a:events
    let b:roxcal_expanded = {}
    let b:roxcal_line_to_idx = {}
    let lines = []
    let line_no = 1
    let idx = 0
    for ev in a:events
        call add(lines, s:fmt_event(ev))
        let b:roxcal_line_to_idx[line_no] = idx
        let line_no += 1
        let idx += 1
    endfor
    if empty(lines)
        let lines = ['  (no events)']
    endif
    call setline(1, lines)
    setlocal nomodifiable nomodified
    call cursor(1, 1)
endfunction

" Walk up to the nearest event header line; return the index into
" b:roxcal_events or -1.
function! s:idx_under_cursor() abort
    if !exists('b:roxcal_line_to_idx')
        return -1
    endif
    let line = line('.')
    while line > 0 && !has_key(b:roxcal_line_to_idx, line)
        let line -= 1
    endwhile
    if line == 0
        return -1
    endif
    return b:roxcal_line_to_idx[line]
endfunction

function! s:rsvp(response) abort
    let idx = s:idx_under_cursor()
    if idx < 0
        return
    endif
    let ev = b:roxcal_events[idx]
    if !s:run_action(['--account', ev.account, 'rsvp', ev.id, a:response])
        return
    endif
    call s:reload()
endfunction

function! s:rsvp_in_buffer(response) abort
    let idx = s:idx_under_cursor()
    if idx < 0
        return
    endif
    let ev = b:roxcal_events[idx]
    let verb = a:response ==# 'accepted'   ? 'Accept'
        \   : a:response ==# 'declined'   ? 'Decline'
        \   : a:response ==# 'tentative'  ? 'Tentatively accept'
        \   :                                'Reply to'
    let title = get(ev, 'title', '(no title)')

    new
    silent file roxcal://rsvp
    setlocal buftype=acwrite bufhidden=wipe nowrap noswapfile
    setlocal filetype=roxcal-rsvp
    let b:roxcal_rsvp_account = ev.account
    let b:roxcal_rsvp_event_id = ev.id
    let b:roxcal_rsvp_calendar = get(ev, 'calendar', '')
    let b:roxcal_rsvp_response = a:response
    let b:roxcal_rsvp_verb = verb
    let b:roxcal_rsvp_title = title

    let lines = [
        \ '# ' . verb . ' event "' . title . '"',
        \ '# Type your message below. Multi-line OK.',
        \ '# Save with :w to send. Cancel with q or :bd!.',
        \ '# Lines starting with # are ignored.',
        \ '',
        \ ]
    call setline(1, lines)
    setlocal nomodified
    autocmd BufWriteCmd <buffer> call <SID>submit_rsvp()
    nnoremap <buffer> <silent> <leader>cc :call <SID>submit_rsvp()<CR>
    nnoremap <buffer> <silent> q :bd!<CR>
    call cursor(5, 1)
    startinsert
endfunction

function! s:submit_rsvp() abort
    let comment_lines = []
    for line in getline(1, '$')
        if line =~ '^#'
            continue
        endif
        call add(comment_lines, line)
    endfor
    while !empty(comment_lines) && trim(comment_lines[0]) ==# ''
        call remove(comment_lines, 0)
    endwhile
    while !empty(comment_lines) && trim(comment_lines[-1]) ==# ''
        call remove(comment_lines, -1)
    endwhile
    let comment = join(comment_lines, "\n")

    let prompt = printf('Send %s response to "%s"?',
        \ tolower(b:roxcal_rsvp_verb), b:roxcal_rsvp_title)
    if confirm(prompt, "&Yes\n&No", 1) != 1
        echom 'Cancelled.'
        return
    endif

    let args = ['--account', b:roxcal_rsvp_account, 'rsvp',
        \ b:roxcal_rsvp_event_id, b:roxcal_rsvp_response]
    if !empty(b:roxcal_rsvp_calendar)
        let args += ['-c', b:roxcal_rsvp_calendar]
    endif
    if !empty(comment)
        let args += ['--comment', comment]
    endif

    if !s:run_action(args)
        return
    endif
    echom 'Response sent.'
    setlocal nomodified
    bdelete!
    let bufnr = bufnr('roxcal://agenda')
    if bufnr >= 0
        execute 'buffer' bufnr
        call s:reload()
    endif
endfunction

function! s:delete_event() abort
    let idx = s:idx_under_cursor()
    if idx < 0
        return
    endif
    let ev = b:roxcal_events[idx]
    let title = get(ev, 'title', '(no title)')
    let answer = confirm('Delete "' . title . '"? Cancellation emails go out '
        \ . 'to attendees if you organized it.', "&Yes\n&No", 2)
    if answer != 1
        return
    endif
    let args = ['--account', ev.account, 'delete', ev.id]
    if !empty(get(ev, 'calendar', ''))
        let args += ['-c', ev.calendar]
    endif
    if !s:run_action(args)
        return
    endif
    call s:reload()
endfunction

function! s:reload() abort
    let args = get(b:, 'roxcal_args', ['agenda', '--all', '--json'])
    let events = s:run_json(args)
    if type(events) == v:t_list
        call s:render(events)
    endif
endfunction

function! s:show_split() abort
    let idx = s:idx_under_cursor()
    if idx < 0
        return
    endif
    let ev = b:roxcal_events[idx]
    let args = ['--account', ev.account, 'show', ev.id]
    if !empty(get(ev, 'calendar', ''))
        let args += ['-c', ev.calendar]
    endif
    let out = system(s:shellcmd(args))
    if v:shell_error
        echohl ErrorMsg
        echom 'roxcal show failed'
        echohl None
        return
    endif
    new
    setlocal buftype=nofile bufhidden=wipe nowrap
    call setline(1, split(out, "\n"))
    setlocal nomodifiable nomodified
    let b:roxcal_detail_ev = ev
    nnoremap <buffer> <silent> q :bd<CR>
    nnoremap <buffer> <silent> E :call <SID>edit_from_detail()<CR>
endfunction

function! s:edit_from_detail() abort
    if !exists('b:roxcal_detail_ev')
        return
    endif
    let ev = b:roxcal_detail_ev
    let args = ['--account', ev.account, 'show', ev.id, '--json']
    if !empty(get(ev, 'calendar', ''))
        let args += ['-c', ev.calendar]
    endif
    let detail = s:run_json(args)
    if type(detail) != v:t_dict
        return
    endif
    " Close the split before opening the edit buffer
    bdelete!
    call s:open_edit(ev.account, ev.id, get(ev, 'calendar', ''), detail)
endfunction

function! s:detail_lines(detail) abort
    let lines = []
    if !empty(get(a:detail, 'organizer', ''))
        call add(lines, '       Organizer: ' . a:detail.organizer)
    endif
    if !empty(get(a:detail, 'conferencing_link', ''))
        call add(lines, '       Meet/Teams: ' . a:detail.conferencing_link)
    endif
    for a in get(a:detail, 'attendees', [])
        let r = get(s:response_symbol, get(a, 'response', ''), ' ')
        let mark = get(a, 'self', 0) ? '  (you)' : ''
        let opt = get(a, 'optional', 0) ? '  (optional)' : ''
        call add(lines, '       [' . r . '] ' . get(a, 'email', '') . mark . opt)
    endfor
    if !empty(get(a:detail, 'description', ''))
        for line in split(a:detail.description, "\n")
            call add(lines, '       | ' . line)
        endfor
    endif
    return lines
endfunction

function! s:toggle_expand() abort
    let idx = s:idx_under_cursor()
    if idx < 0
        return
    endif
    " Find the event header line for this idx
    let header_line = 0
    for [k, v] in items(b:roxcal_line_to_idx)
        if v == idx
            let header_line = str2nr(k)
            break
        endif
    endfor
    if header_line == 0
        return
    endif
    setlocal modifiable
    if has_key(b:roxcal_expanded, idx)
        let n = b:roxcal_expanded[idx]
        execute (header_line + 1) . ',' . (header_line + n) . 'delete _'
        unlet b:roxcal_expanded[idx]
        let shift = -n
    else
        let ev = b:roxcal_events[idx]
        let args = ['--account', ev.account, 'show', ev.id, '--json']
        if !empty(get(ev, 'calendar', ''))
            let args += ['-c', ev.calendar]
        endif
        let detail = s:run_json(args)
        if type(detail) != v:t_dict
            setlocal nomodifiable
            return
        endif
        let extra = s:detail_lines(detail)
        if empty(extra)
            setlocal nomodifiable
            return
        endif
        call append(header_line, extra)
        let b:roxcal_expanded[idx] = len(extra)
        let shift = len(extra)
    endif
    " Re-map header line -> idx so subsequent toggles still work.
    let new_map = {}
    for [k, v] in items(b:roxcal_line_to_idx)
        let ki = str2nr(k)
        if ki <= header_line
            let new_map[ki] = v
        else
            let new_map[ki + shift] = v
        endif
    endfor
    let b:roxcal_line_to_idx = new_map
    setlocal nomodifiable nomodified
endfunction

function! s:show_agenda_help() abort
    echo  "roxcal://agenda  mappings"
    echo  "  <CR>        toggle inline expansion (organizer, attendees, body)"
    echo  "  a / d / t   RSVP accepted / declined / tentative (no comment, fast)"
    echo  "  <leader>a   accept with a message buffer (:w to send)"
    echo  "  <leader>d   decline with a message buffer (:w to send)"
    echo  "  <leader>t   tentative with a message buffer (:w to send)"
    echo  "  D           delete the event (asks first)"
    echo  "  E           edit the event in a buffer (submit with :w)"
    echo  "  gd          show full detail in a split (E to edit, q to close)"
    echo  "  r           reload from roxcal"
    echo  "  q           close this buffer"
    echo  "  ?           this help"
    echo  ""
    echo  "Commands (also work from anywhere)"
    echo  "  :RoxcalAgenda [args]                    reopen with passthrough args"
    echo  "  :RoxcalAdd [account]                    compose a new event"
    echo  "  :RoxcalReply accepted|declined|tentative   open the rsvp message buffer"
    echo  "  :RoxcalReload                           reload"
endfunction

function! s:show_add_help() abort
    echo  "roxcal://add  mappings"
    echo  "  :w / :wq     submit (create the event)"
    echo  "  <leader>cc   submit (same as :w)"
    echo  "  q            cancel"
    echo  "  ?            this help"
endfunction

function! s:open_agenda(...) abort
    if a:0 > 0
        let args = ['agenda'] + copy(a:000) + ['--json']
    else
        let args = ['agenda', '--all', '--json']
    endif
    let events = s:run_json(args)
    if type(events) != v:t_list
        return
    endif

    let bufnr = bufnr('roxcal://agenda')
    if bufnr < 0
        enew
        silent file roxcal://agenda
        setlocal buftype=nofile bufhidden=hide nowrap noswapfile
        setlocal filetype=roxcal
    else
        execute 'buffer' bufnr
    endif
    let b:roxcal_args = args
    call s:render(events)

    nnoremap <buffer> <silent> <CR> :call <SID>toggle_expand()<CR>
    nnoremap <buffer> <silent> a    :call <SID>rsvp('accepted')<CR>
    nnoremap <buffer> <silent> d    :call <SID>rsvp('declined')<CR>
    nnoremap <buffer> <silent> t    :call <SID>rsvp('tentative')<CR>
    nnoremap <buffer> <silent> <leader>a :call <SID>rsvp_in_buffer('accepted')<CR>
    nnoremap <buffer> <silent> <leader>d :call <SID>rsvp_in_buffer('declined')<CR>
    nnoremap <buffer> <silent> <leader>t :call <SID>rsvp_in_buffer('tentative')<CR>
    nnoremap <buffer> <silent> gd   :call <SID>show_split()<CR>
    nnoremap <buffer> <silent> r    :call <SID>reload()<CR>
    nnoremap <buffer> <silent> q    :bd<CR>
    nnoremap <buffer> <silent> D    :call <SID>delete_event()<CR>
    nnoremap <buffer> <silent> E    :call <SID>edit_under_cursor()<CR>
    nnoremap <buffer> <silent> ?    :call <SID>show_agenda_help()<CR>
endfunction

function! s:edit_under_cursor() abort
    let idx = s:idx_under_cursor()
    if idx < 0
        return
    endif
    let ev = b:roxcal_events[idx]
    " Fetch full detail so we can pre-fill the form
    let args = ['--account', ev.account, 'show', ev.id, '--json']
    if !empty(get(ev, 'calendar', ''))
        let args += ['-c', ev.calendar]
    endif
    let detail = s:run_json(args)
    if type(detail) != v:t_dict
        return
    endif
    call s:open_edit(ev.account, ev.id, get(ev, 'calendar', ''), detail)
endfunction

function! s:fmt_iso_local(iso) abort
    " Trim to 'YYYY-MM-DD HH:MM' for display in the form
    if empty(a:iso)
        return ''
    endif
    let s = substitute(a:iso, 'T', ' ', '')
    return strpart(s, 0, 16)
endfunction

function! s:diff_seconds(start_iso, end_iso) abort
    " Rough difference between two ISO strings, returns seconds as int.
    " We only use this to format a 'Duration: 30m' line for the user.
    let s = strpart(a:start_iso, 0, 19)
    let e = strpart(a:end_iso, 0, 19)
    if empty(s) || empty(e)
        return 0
    endif
    let sec_s = system("date -d '" . s . "' +%s")
    let sec_e = system("date -d '" . e . "' +%s")
    if v:shell_error
        return 0
    endif
    return str2nr(sec_e) - str2nr(sec_s)
endfunction

function! s:fmt_duration(secs) abort
    if a:secs <= 0
        return ''
    endif
    let h = a:secs / 3600
    let m = (a:secs % 3600) / 60
    if h > 0 && m > 0
        return printf('%dh%dm', h, m)
    elseif h > 0
        return printf('%dh', h)
    else
        return printf('%dm', m)
    endif
endfunction

function! s:open_edit(account, event_id, calendar, detail) abort
    new
    silent file roxcal://edit
    setlocal buftype=acwrite bufhidden=wipe nowrap noswapfile
    setlocal filetype=roxcal-edit
    let b:roxcal_edit_account = a:account
    let b:roxcal_edit_event_id = a:event_id
    let b:roxcal_edit_calendar = a:calendar
    let start_iso = get(a:detail, 'start', '')
    let end_iso = get(a:detail, 'end', '')
    let when = s:fmt_iso_local(start_iso)
    let duration = s:fmt_duration(s:diff_seconds(start_iso, end_iso))
    let attendees = []
    for a in get(a:detail, 'attendees', [])
        let addr = get(a, 'email', '')
        if !empty(addr) && !get(a, 'self', 0)
            call add(attendees, addr)
        endif
    endfor
    let rem = get(a:detail, 'reminder_minutes', v:null)
    let rem_s = type(rem) == v:t_number ? string(rem) : ''
    let lines = [
        \ '# Edit event ' . a:event_id . ' on account ' . a:account,
        \ '# Edit any field and :w to apply. Leave a field unchanged to keep it.',
        \ '',
        \ 'Title: ' . get(a:detail, 'title', ''),
        \ 'When: ' . when,
        \ 'Duration: ' . duration,
        \ 'Attendees: ' . join(attendees, ','),
        \ 'Where: ' . get(a:detail, 'location', ''),
        \ 'Reminder: ' . rem_s,
        \ 'Description:',
        \ ]
    for line in split(get(a:detail, 'description', ''), "\n")
        call add(lines, line)
    endfor
    call setline(1, lines)
    setlocal nomodified
    autocmd BufWriteCmd <buffer> call <SID>submit_edit()
    nnoremap <buffer> <silent> <leader>cc :call <SID>submit_edit()<CR>
    nnoremap <buffer> <silent> q          :bd!<CR>
    call cursor(4, len('Title: ') + 1)
endfunction

function! s:submit_edit() abort
    let title = ''
    for line in getline(1, '$')
        if line =~ '^#'
            continue
        endif
        let m = matchlist(line, '^Title:\s*\(.*\)$')
        if !empty(m)
            let title = m[1]
            break
        endif
    endfor
    let prompt = empty(title)
        \ ? 'Apply changes to this event?'
        \ : printf('Apply changes to event "%s"?', title)
    if confirm(prompt, "&Yes\n&No", 1) != 1
        echom 'Cancelled.'
        return
    endif
    let lines = getline(1, '$')
    let fields = {'title': '', 'when': '', 'duration': '', 'attendees': '',
                  \ 'where': '', 'reminder': ''}
    let in_description = 0
    let description = []
    for line in lines
        if line =~ '^#'
            continue
        endif
        if in_description
            call add(description, line)
            continue
        endif
        let m = matchlist(line, '^\([A-Za-z]\+\):\s*\(.*\)$')
        if empty(m)
            continue
        endif
        let key = tolower(m[1])
        if key ==# 'description'
            let in_description = 1
        else
            let fields[key] = m[2]
        endif
    endfor
    let desc = join(description, "\n")
    let desc = substitute(desc, '^\s*\(.\{-}\)\s*$', '\1', '')

    let args = ['--account', b:roxcal_edit_account, 'edit', b:roxcal_edit_event_id]
    if !empty(b:roxcal_edit_calendar)
        let args += ['-c', b:roxcal_edit_calendar]
    endif
    if !empty(fields.title)
        let args += ['--title', fields.title]
    endif
    if !empty(fields.when)
        let args += ['--when', fields.when]
    endif
    if !empty(fields.duration)
        let args += ['--duration', fields.duration]
    endif
    if !empty(fields.attendees)
        let args += ['--attendees', fields.attendees]
    endif
    if !empty(fields.where)
        let args += ['--where', fields.where]
    endif
    if !empty(fields.reminder)
        let args += ['--reminder', fields.reminder]
    endif
    if !empty(desc)
        let args += ['--description', desc]
    endif

    if !s:run_action(args)
        return
    endif
    echom 'Event updated.'
    setlocal nomodified
    bdelete!
    let bufnr = bufnr('roxcal://agenda')
    if bufnr >= 0
        execute 'buffer' bufnr
        call s:reload()
    endif
endfunction

function! s:open_add(...) abort
    let acct = a:0 > 0 ? a:1 : ''
    new
    silent file roxcal://add
    setlocal buftype=acwrite bufhidden=wipe nowrap noswapfile
    setlocal filetype=roxcal-add
    let template = [
        \ 'Account: ' . acct,
        \ 'Title: ',
        \ 'When: tomorrow 10:00',
        \ 'Duration: 30m',
        \ 'Attendees: ',
        \ 'Calendar: ',
        \ 'Where: ',
        \ 'Meet: no',
        \ 'Reminder: 10',
        \ 'Description:',
        \ '',
        \ ]
    call setline(1, template)
    setlocal nomodified
    autocmd BufWriteCmd <buffer> call <SID>submit_add()
    nnoremap <buffer> <silent> <leader>cc :call <SID>submit_add()<CR>
    nnoremap <buffer> <silent> q          :bd!<CR>
    nnoremap <buffer> <silent> ?          :call <SID>show_add_help()<CR>
    call cursor(2, len('Title: ') + 1)
    startinsert!
endfunction

function! s:submit_add() abort
    " Pull the title for the confirmation prompt
    let title = ''
    for line in getline(1, '$')
        let m = matchlist(line, '^Title:\s*\(.*\)$')
        if !empty(m)
            let title = m[1]
            break
        endif
    endfor
    let prompt = empty(title)
        \ ? 'Create this event?'
        \ : printf('Create event "%s"?', title)
    if confirm(prompt, "&Yes\n&No", 1) != 1
        echom 'Cancelled.'
        return
    endif
    let lines = getline(1, '$')
    let fields = {'account': '', 'title': '', 'when': '', 'duration': '',
                  \ 'attendees': '', 'calendar': '', 'where': '', 'meet': '',
                  \ 'reminder': ''}
    let in_description = 0
    let description = []
    for line in lines
        if in_description
            call add(description, line)
            continue
        endif
        let m = matchlist(line, '^\([A-Za-z]\+\):\s*\(.*\)$')
        if empty(m)
            continue
        endif
        let key = tolower(m[1])
        if key ==# 'description'
            let in_description = 1
        else
            let fields[key] = m[2]
        endif
    endfor
    let desc = join(description, "\n")
    let desc = substitute(desc, '^\s*\(.\{-}\)\s*$', '\1', '')

    if empty(fields.title)
        echohl ErrorMsg | echom 'roxcal: Title is required' | echohl None
        return
    endif
    if empty(fields.when)
        echohl ErrorMsg | echom 'roxcal: When is required' | echohl None
        return
    endif

    let args = []
    if !empty(fields.account)
        let args += ['--account', fields.account]
    endif
    let args += ['add', '--title', fields.title, '--when', fields.when]
    if !empty(fields.duration)
        let args += ['--duration', fields.duration]
    endif
    if !empty(fields.attendees)
        let args += ['--attendees', fields.attendees]
    endif
    if !empty(fields.calendar)
        let args += ['--calendar', fields.calendar]
    endif
    if !empty(fields.where)
        let args += ['--where', fields.where]
    endif
    if !empty(desc)
        let args += ['--description', desc]
    endif
    let meet = tolower(fields.meet)
    if meet ==# 'yes' || meet ==# 'true' || meet ==# '1' || meet ==# 'y'
        let args += ['--meet']
    endif
    if !empty(fields.reminder)
        let args += ['--reminder', fields.reminder]
    endif

    let out = system(s:shellcmd(args))
    if v:shell_error
        echohl ErrorMsg | echom 'roxcal add failed: ' . out | echohl None
        return
    endif
    echom 'Event created.'
    setlocal nomodified
    bdelete!
    " Reload the agenda buffer if it is open
    let bufnr = bufnr('roxcal://agenda')
    if bufnr >= 0
        execute 'buffer' bufnr
        call s:reload()
    endif
endfunction

function! s:rsvp_complete(arg, line, pos) abort
    return filter(['accepted', 'declined', 'tentative'],
        \ 'v:val =~ "^" . a:arg')
endfunction

command! -nargs=* RoxcalAgenda call <SID>open_agenda(<f-args>)
command! -nargs=? RoxcalAdd    call <SID>open_add(<f-args>)
command! RoxcalReload          call <SID>reload()
command! -nargs=1 -complete=customlist,<SID>rsvp_complete RoxcalReply call <SID>rsvp_in_buffer(<q-args>)
