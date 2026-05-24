"""Drive the vim plugin via a vim subprocess and assert on its output."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parent.parent / "plugin" / "roxcal.vim"

pytestmark = pytest.mark.skipif(shutil.which("vim") is None, reason="vim not installed")


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
        return out_file.read_text().rstrip("\n")


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
        return out_file.read_text().rstrip("\n")


def test_color_args_named():
    assert _color_args("green") == "ctermfg=green"


def test_color_args_int():
    assert _color_args(196) == "ctermfg=196"


def test_color_args_hex():
    assert _color_args("#88c070") == "guifg=#88c070"


def test_color_args_empty_string():
    assert _color_args("") == ""
