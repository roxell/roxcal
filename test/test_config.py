"""Tests for the config dataclasses and load/bootstrap logic."""

import pytest

from roxcal import config as cfg_mod
from roxcal.config import Account, Config, bootstrap_config, load_config


def _redirect_config(monkeypatch, tmp_path):
    cdir = tmp_path / "roxcal"
    monkeypatch.setattr(cfg_mod, "CONFIG_DIR", cdir)
    monkeypatch.setattr(cfg_mod, "CONFIG_FILE", cdir / "config.toml")
    return cdir


def test_account_defaults():
    acc = Account(name="x", backend="google_oauth")
    assert acc.email == ""
    assert acc.client_id == ""
    assert acc.tenant == "common"
    assert acc.calendars == []


def test_config_defaults():
    c = Config(default_account="x")
    assert c.accounts == {}


def test_bootstrap_writes_config(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    bootstrap_config()
    assert (cdir / "config.toml").exists()
    body = (cdir / "config.toml").read_text()
    assert "default_account" in body
    assert "google_shared" in body


def test_load_config_bootstraps_when_missing(tmp_path, monkeypatch, capsys):
    _redirect_config(monkeypatch, tmp_path)
    config = load_config()
    capsys.readouterr()  # drain bootstrap message
    assert isinstance(config, Config)
    assert "roxell" in config.accounts
    assert "linaro" in config.accounts


def test_load_config_reads_custom(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "work"

[accounts.work]
backend = "google_oauth"
email = "test@example.com"
client_id = "id"
client_secret = "secret"
calendars = ["a@x.com", "b@x.com"]
""")
    config = load_config()
    assert config.default_account == "work"
    acc = config.accounts["work"]
    assert acc.email == "test@example.com"
    assert acc.client_id == "id"
    assert acc.calendars == ["a@x.com", "b@x.com"]


def test_load_config_shared_client_fallback(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "work"

[google_shared]
client_id = "shared-id"
client_secret = "shared-secret"

[accounts.work]
backend = "google_oauth"
email = "test@example.com"
""")
    config = load_config()
    acc = config.accounts["work"]
    assert acc.client_id == "shared-id"
    assert acc.client_secret == "shared-secret"


def test_load_config_per_account_overrides_shared(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "work"

[google_shared]
client_id = "shared-id"

[accounts.work]
backend = "google_oauth"
email = "test@example.com"
client_id = "own-id"
""")
    config = load_config()
    assert config.accounts["work"].client_id == "own-id"


def test_load_config_caldav_account(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "linaro"

[accounts.linaro]
backend = "google_caldav"
email = "anders@linaro.org"
caldav_password = "xxxx yyyy zzzz wwww"
""")
    config = load_config()
    acc = config.accounts["linaro"]
    assert acc.backend == "google_caldav"
    assert acc.caldav_password == "xxxx yyyy zzzz wwww"


def test_load_config_microsoft_account(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "ms"

[accounts.ms]
backend = "microsoft_graph"
email = "you@outlook.com"
client_id = "azure-app-id"
tenant = "my-tenant"
""")
    config = load_config()
    acc = config.accounts["ms"]
    assert acc.backend == "microsoft_graph"
    assert acc.tenant == "my-tenant"
    assert acc.client_id == "azure-app-id"


def test_load_config_unknown_backend_exits(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
[accounts.foo]
backend = "no_such_backend"
""")
    with pytest.raises(SystemExit):
        load_config()


def test_load_config_default_account_unknown_exits(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "nope"

[accounts.foo]
backend = "google_oauth"
""")
    with pytest.raises(SystemExit):
        load_config()


def test_load_config_color_defaults_to_auto(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "x"

[accounts.x]
backend = "google_oauth"
""")
    assert load_config().color == "auto"


def test_load_config_color_explicit(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "x"
color = "always"

[accounts.x]
backend = "google_oauth"
""")
    assert load_config().color == "always"


def test_load_config_color_invalid_exits(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "x"
color = "rainbow"

[accounts.x]
backend = "google_oauth"
""")
    with pytest.raises(SystemExit):
        load_config()


def test_colors_defaults_match_default_scheme(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "x"

[accounts.x]
backend = "google_oauth"
""")
    config = load_config()
    assert config.colors["accepted"] == "\033[32m"
    assert config.colors["declined"] == "\033[31m"
    assert config.colors["tentative"] == "\033[33m"
    assert config.colors["needsAction"] == "\033[36m"
    assert config.colors["organizer"] == "\033[35m"
    assert config.colors["past"] == "\033[90m"


def test_colors_past_override(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "x"

[accounts.x]
backend = "google_oauth"

[colors]
past = "#888888"
""")
    config = load_config()
    assert config.colors["past"] == "\033[38;2;136;136;136m"


def test_colors_named_override(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "x"

[accounts.x]
backend = "google_oauth"

[colors]
accepted = "bright_green"
needs_action = "blue"
""")
    config = load_config()
    assert config.colors["accepted"] == "\033[92m"
    assert config.colors["needsAction"] == "\033[34m"
    # Untouched keys keep the default.
    assert config.colors["declined"] == "\033[31m"


def test_colors_int_palette(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "x"

[accounts.x]
backend = "google_oauth"

[colors]
declined = 196
""")
    assert load_config().colors["declined"] == "\033[38;5;196m"


def test_colors_hex_truecolor(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "x"

[accounts.x]
backend = "google_oauth"

[colors]
tentative = "#d8c068"
""")
    assert load_config().colors["tentative"] == "\033[38;2;216;192;104m"


def test_colors_unknown_key_exits(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "x"

[accounts.x]
backend = "google_oauth"

[colors]
nope = "green"
""")
    with pytest.raises(SystemExit):
        load_config()


def test_colors_unknown_name_exits(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "x"

[accounts.x]
backend = "google_oauth"

[colors]
accepted = "puce"
""")
    with pytest.raises(SystemExit):
        load_config()


def test_colors_int_out_of_range_exits(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "x"

[accounts.x]
backend = "google_oauth"

[colors]
accepted = 300
""")
    with pytest.raises(SystemExit):
        load_config()


def test_colors_bad_hex_exits(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "x"

[accounts.x]
backend = "google_oauth"

[colors]
accepted = "#xyz"
""")
    with pytest.raises(SystemExit):
        load_config()


def test_colors_short_hex_exits(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "x"

[accounts.x]
backend = "google_oauth"

[colors]
accepted = "#abc"
""")
    with pytest.raises(SystemExit):
        load_config()


def test_colors_overrides_recorded_verbatim(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "x"

[accounts.x]
backend = "google_oauth"

[colors]
accepted = "bright_green"
declined = 196
tentative = "#d8c068"
""")
    overrides = load_config().color_overrides
    assert overrides == {
        "accepted": "bright_green",
        "declined": 196,
        "tentative": "#d8c068",
    }


def test_colors_overrides_empty_when_table_absent(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "x"

[accounts.x]
backend = "google_oauth"
""")
    assert load_config().color_overrides == {}


def test_colors_bool_rejected(tmp_path, monkeypatch):
    cdir = _redirect_config(monkeypatch, tmp_path)
    cdir.mkdir()
    (cdir / "config.toml").write_text("""
default_account = "x"

[accounts.x]
backend = "google_oauth"

[colors]
accepted = true
""")
    with pytest.raises(SystemExit):
        load_config()
