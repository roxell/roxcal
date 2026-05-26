"""Shell completion files must stay in sync with the actual subcommands."""

import re
from pathlib import Path

from roxcal.cli import build_parser

COMPLETIONS = Path(__file__).resolve().parent.parent / "completions"


def _parser_subcommands() -> set[str]:
    parser = build_parser()
    sub_action = next(a for a in parser._actions if hasattr(a, "choices") and a.choices)
    return set(sub_action.choices or {})


def test_bash_completion_subcommands_match_parser():
    text = (COMPLETIONS / "roxcal.bash").read_text()
    m = re.search(r'subs="([^"]+)"', text)
    assert m, "could not find subs= list in roxcal.bash"
    assert set(m.group(1).split()) == _parser_subcommands()


def test_zsh_completion_subcommands_match_parser():
    text = (COMPLETIONS / "roxcal.zsh").read_text()
    found = set(re.findall(r"^\s*'([a-z]+):", text, re.MULTILINE))
    assert found == _parser_subcommands()


def test_fish_completion_subcommands_match_parser():
    text = (COMPLETIONS / "roxcal.fish").read_text()
    found = set(re.findall(r"-a (\w+) -d", text))
    assert found == _parser_subcommands()
