"""Drive the vim plugin via a vim subprocess and assert on its output."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parent.parent / "plugin" / "roxcal.vim"

pytestmark = pytest.mark.skipif(shutil.which("vim") is None, reason="vim not installed")


def _run_vim(script: str, script_file: Path, out_file: Path) -> str:
    """Run one drive script in vim and return what it wrote to out_file.

    The helpers below differ only in the script and what they return.
    """
    script_file.write_text(script)
    result = subprocess.run(
        ["vim", "-Es", "-u", "NONE", "-i", "NONE", "-S", str(script_file)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if not out_file.exists():
        raise RuntimeError(
            f"vim failed (rc={result.returncode}): "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
    return out_file.read_text()


def _fmt_event(event: dict, compact: bool) -> str:
    """Format one event via the plugin's s:fmt_event and return the line."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        event_file = tmp_path / "event.json"
        out_file = tmp_path / "out.txt"
        script_file = tmp_path / "drive.vim"
        event_file.write_text(json.dumps(event))
        compact_arg = "1" if compact else "0"
        script = f"""
            source {PLUGIN}
            let s:ev = json_decode(join(readfile('{event_file}'), "\\n"))
            let s:line = RoxcalFmtEvent(s:ev, {compact_arg})
            call writefile([s:line], '{out_file}')
            qa!
        """
        return _run_vim(script, script_file, out_file).rstrip("\n")


_EVENT = {
    "start": "2026-05-26T09:00:00+02:00",
    "title": "Standup",
    "account": "ms",
    "calendar_name": "Work",
    "response": "accepted",
}


def test_non_compact_shows_account_and_calendar():
    line = _fmt_event(_EVENT, compact=False)
    assert "[+]" in line
    assert "[ms]" in line
    assert "[Work]" in line
    assert "Standup" in line


def test_compact_hides_account_and_calendar():
    line = _fmt_event(_EVENT, compact=True)
    assert "[+]" in line
    assert "Standup" in line
    assert "[ms]" not in line
    assert "[Work]" not in line


def test_compact_keeps_start_time():
    line = _fmt_event(_EVENT, compact=True)
    assert "2026-05-26T09:00" in line


def test_compact_keeps_location():
    ev = dict(_EVENT, location="Online")
    line = _fmt_event(ev, compact=True)
    assert "@ Online" in line


def _color_args(value) -> str:
    """Ask the plugin's RoxcalColorArgs() what highlight args it would
    emit for one config value."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        value_file = tmp_path / "v.json"
        out_file = tmp_path / "out.txt"
        script_file = tmp_path / "drive.vim"
        value_file.write_text(json.dumps(value))
        script = f"""
            source {PLUGIN}
            let s:v = json_decode(join(readfile('{value_file}'), "\\n"))
            let s:r = RoxcalColorArgs(s:v)
            call writefile([s:r], '{out_file}')
            qa!
        """
        return _run_vim(script, script_file, out_file).rstrip("\n")


def test_color_args_named():
    assert _color_args("green") == "ctermfg=green"


def test_color_args_int():
    assert _color_args(196) == "ctermfg=196"


def test_color_args_hex():
    assert _color_args("#88c070") == "guifg=#88c070"


def test_color_args_empty_string():
    assert _color_args("") == ""


def _build_lines(events, clusters=None, compact: bool = False) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ev_file = tmp_path / "events.json"
        cl_file = tmp_path / "clusters.json"
        out_file = tmp_path / "out.json"
        script_file = tmp_path / "drive.vim"
        ev_file.write_text(json.dumps(events))
        if clusters is None:
            clusters_expr = "v:null"
        else:
            cl_file.write_text(json.dumps(clusters))
            clusters_expr = f"json_decode(join(readfile('{cl_file}'), \"\\n\"))"
        compact_arg = "1" if compact else "0"
        script = f"""
            source {PLUGIN}
            let s:events = json_decode(join(readfile('{ev_file}'), "\\n"))
            let s:r = RoxcalBuildLines(s:events, {clusters_expr}, {compact_arg})
            call writefile([json_encode(s:r)], '{out_file}')
            qa!
        """
        return json.loads(_run_vim(script, script_file, out_file))


def test_build_lines_inserts_day_separator():
    events = [
        {"start": "2026-05-26T09:00:00+02:00", "title": "A", "account": "x"},
        {"start": "2026-05-27T09:00:00+02:00", "title": "B", "account": "x"},
    ]
    r = _build_lines(events)
    sep_lines = [int(k) for k in r["separator_lines"].keys()]
    assert len(sep_lines) == 2
    # Each separator is the line above its events.
    for line_no in sep_lines:
        assert r["lines"][line_no - 1].startswith("2026-05-")
        assert "===" in r["lines"][line_no - 1]


def test_build_lines_groups_same_day():
    events = [
        {"start": "2026-05-26T09:00:00+02:00", "title": "A", "account": "x"},
        {"start": "2026-05-26T14:00:00+02:00", "title": "B", "account": "x"},
    ]
    r = _build_lines(events)
    assert len(r["separator_lines"]) == 1


def test_build_lines_emits_fold_range_per_day():
    events = [
        {"start": "2026-05-26T09:00:00+02:00", "title": "A", "account": "x"},
        {"start": "2026-05-26T14:00:00+02:00", "title": "B", "account": "x"},
        {"start": "2026-05-27T09:00:00+02:00", "title": "C", "account": "x"},
    ]
    r = _build_lines(events)
    # Two days with at least one event each -> two fold ranges, each
    # open by default (no past events).
    assert len(r["fold_ranges"]) == 2
    for s, e, open_default in r["fold_ranges"]:
        assert open_default == 1


def test_build_lines_nests_past_days_in_outer_fold():
    events = [
        {
            "start": "2024-01-01T09:00:00+02:00",
            "title": "Past1",
            "account": "x",
            "is_past": 1,
        },
        {
            "start": "2024-01-02T09:00:00+02:00",
            "title": "Past2",
            "account": "x",
            "is_past": 1,
        },
        {
            "start": "2026-12-01T09:00:00+02:00",
            "title": "Future",
            "account": "x",
        },
    ]
    r = _build_lines(events)
    # Three day groups -> 2 past inner folds + 1 outer wrapper + 1 future = 4.
    assert len(r["fold_ranges"]) == 4
    # Inner past folds and the outer wrapper are closed by default;
    # the future day is open.
    open_flags = [f[2] for f in r["fold_ranges"]]
    assert open_flags == [0, 0, 0, 1]
    # The outer wrapper spans both past days (third entry in fold_ranges).
    outer = r["fold_ranges"][2]
    assert outer[0] == r["fold_ranges"][0][0]
    assert outer[1] == r["fold_ranges"][1][1]


def test_build_lines_marks_past_lines():
    events = [
        {
            "start": "2026-05-26T09:00:00+02:00",
            "title": "Past",
            "account": "x",
            "is_past": 1,
        },
        {
            "start": "2026-05-26T14:00:00+02:00",
            "title": "Future",
            "account": "x",
        },
    ]
    r = _build_lines(events)
    # The past line should be flagged; future not.
    past_line = r["past_lines"][0]
    assert "Past" in r["lines"][past_line - 1]
    assert len(r["past_lines"]) == 1


def test_build_lines_cluster_path():
    clusters = [
        {
            "overlap_start": "2026-05-26T10:30:00+02:00",
            "overlap_end": "2026-05-26T11:00:00+02:00",
            "events": [
                {
                    "start": "2026-05-26T10:00:00+02:00",
                    "title": "A",
                    "account": "x",
                },
                {
                    "start": "2026-05-26T10:30:00+02:00",
                    "title": "B",
                    "account": "x",
                },
            ],
        }
    ]
    # events list for the flat fallback is just the flattened cluster events.
    flat = [e for c in clusters for e in c["events"]]
    r = _build_lines(flat, clusters=clusters)
    assert any("Overlap" in line for line in r["lines"])
    assert len(r["fold_ranges"]) == 1
    # Cluster folds are open by default.
    assert r["fold_ranges"][0][2] == 1


def _render_and_probe(events, drive_extra: str) -> str:
    """Run s:render in a buffer, then execute drive_extra to probe state.
    drive_extra must writefile([...], '{OUT}') the result. Returns the
    text written.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ev_file = tmp_path / "events.json"
        out_file = tmp_path / "out.txt"
        script_file = tmp_path / "drive.vim"
        ev_file.write_text(json.dumps(events))
        script = f"""
            source {PLUGIN}
            enew
            silent file roxcal://agenda
            setlocal buftype=nofile bufhidden=hide nowrap noswapfile
            let s:events = json_decode(join(readfile('{ev_file}'), "\\n"))
            call RoxcalRender(s:events, v:null)
            {drive_extra.replace('{OUT}', str(out_file))}
            qa!
        """
        return _run_vim(script, script_file, out_file).rstrip("\n")


def test_render_preserves_cursor_line():
    events = [
        {"start": "2026-05-26T09:00:00+02:00", "title": "A", "account": "x"},
        {"start": "2026-05-26T10:00:00+02:00", "title": "B", "account": "x"},
        {"start": "2026-05-26T11:00:00+02:00", "title": "C", "account": "x"},
    ]
    drive = """
        call cursor(3, 1)
        call RoxcalRender(s:events, v:null)
        call writefile([string(line('.'))], '{OUT}')
    """
    assert _render_and_probe(events, drive) == "3"


def test_render_clamps_cursor_when_buffer_shrinks():
    events = [
        {"start": "2026-05-26T09:00:00+02:00", "title": "A", "account": "x"},
        {"start": "2026-05-26T10:00:00+02:00", "title": "B", "account": "x"},
        {"start": "2026-05-26T11:00:00+02:00", "title": "C", "account": "x"},
    ]
    drive = """
        call cursor(line('$'), 1)
        let s:few = [s:events[0]]
        call RoxcalRender(s:few, v:null)
        call writefile([string(line('.'))], '{OUT}')
    """
    out = _render_and_probe(events, drive)
    assert int(out) >= 1
    assert int(out) <= 2


def _short_error(text: str) -> str:
    """Ask the plugin's RoxcalShortError() what it would show for this
    stderr text."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        in_file = tmp_path / "err.json"
        out_file = tmp_path / "out.txt"
        script_file = tmp_path / "drive.vim"
        in_file.write_text(json.dumps(text))
        script = f"""
            source {PLUGIN}
            let s:txt = json_decode(join(readfile('{in_file}'), "\\n"))
            call writefile([RoxcalShortError(s:txt)], '{out_file}')
            qa!
        """
        return _run_vim(script, script_file, out_file).rstrip("\n")


_TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "/x/urllib3/connection.py", line 231, in _new_conn\n'
    "    sock = self._resolver.create_connection(\n"
    "OSError: [Errno 113] No route to host\n"
    "\n"
    "The above exception was the direct cause of the following exception:\n"
    "\n"
    "Traceback (most recent call last):\n"
    '  File "/x/niquests/adapters.py", line 958, in send\n'
    "    raise ConnectionError(e, request=request)\n"
    "niquests.exceptions.ConnectionError: no route to host\n"
)


def test_short_error_keeps_only_the_last_line():
    """A python traceback must not flood the message area."""
    out = _short_error(_TRACEBACK)
    assert out == "niquests.exceptions.ConnectionError: no route to host"
    assert "Traceback" not in out
    assert "\n" not in out


def test_short_error_ignores_trailing_blank_lines():
    assert _short_error("roxcal: cannot reach the server\n\n\n") == (
        "roxcal: cannot reach the server"
    )


def test_short_error_passes_single_line_through():
    assert _short_error("roxcal: unknown account 'x'") == "roxcal: unknown account 'x'"


def test_short_error_handles_empty_output():
    assert _short_error("") == "roxcal failed with no output"


def test_short_error_does_not_touch_the_global():
    """It formats, nothing else. s:report_failure owns the global."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        out_file = tmp_path / "out.txt"
        script_file = tmp_path / "drive.vim"
        script_file.write_text(f"""
            source {PLUGIN}
            call RoxcalShortError("boom")
            call writefile([exists('g:roxcal_last_error') ? 'set' : 'unset'], '{out_file}')
            qa!
            """)
        subprocess.run(
            ["vim", "-Es", "-u", "NONE", "-i", "NONE", "-S", str(script_file)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert out_file.read_text().strip() == "unset"
