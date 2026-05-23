"""Cover roxcal/__main__.py (the `python -m roxcal` entry point)."""

import runpy
from unittest.mock import patch


def test_main_module_invokes_cli_main():
    with patch("roxcal.cli.main") as fake_main:
        runpy.run_module("roxcal", run_name="__main__")
    fake_main.assert_called_once()
