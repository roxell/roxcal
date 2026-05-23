"""Tests for the Nextcloud CalDAV backend."""

from unittest.mock import MagicMock, patch

import pytest

from roxcal.backends import make_backend
from roxcal.backends.nextcloud_caldav import NextcloudCalDAVBackend
from roxcal.config import Account


def _nc(**overrides):
    defaults = {
        "name": "cloud",
        "backend": "nextcloud_caldav",
        "email": "anders@example.com",
        "caldav_url": "https://cloud.example.com/remote.php/dav/",
        "caldav_password": "p",
    }
    defaults.update(overrides)
    return NextcloudCalDAVBackend(Account(**defaults))


def test_make_backend_dispatches_to_nextcloud():
    acc = Account(name="x", backend="nextcloud_caldav")
    assert isinstance(make_backend(acc), NextcloudCalDAVBackend)


def test_nextcloud_url_used_verbatim():
    backend = _nc()
    fake_client = MagicMock()
    with patch("caldav.DAVClient", return_value=fake_client) as ctor:
        backend._client()
    ctor.assert_called_once_with(
        url="https://cloud.example.com/remote.php/dav/",
        username="anders@example.com",
        password="p",
    )


def test_nextcloud_uses_caldav_username_when_set():
    backend = _nc(caldav_username="anders")
    with patch("caldav.DAVClient") as ctor:
        backend._client()
    assert ctor.call_args.kwargs["username"] == "anders"


def test_nextcloud_dies_without_password():
    backend = _nc(caldav_password="")
    with pytest.raises(SystemExit):
        backend._client()


def test_nextcloud_dies_without_url():
    backend = _nc(caldav_url="")
    with pytest.raises(SystemExit):
        backend._client()


def test_nextcloud_does_not_warn_on_attendees(capsys):
    backend = _nc()
    backend._create_notices(conferencing=False, attendees=True)
    err = capsys.readouterr().err
    assert err == ""


def test_nextcloud_warns_on_conferencing(capsys):
    backend = _nc()
    backend._create_notices(conferencing=True, attendees=False)
    err = capsys.readouterr().err
    assert "Talk" in err
