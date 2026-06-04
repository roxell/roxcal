"""Tests for backend dispatch. The backend classes themselves talk to
external APIs, so unit-testing their methods requires mocks; that's left
for later. Here we cover the dispatcher and the base class contract."""

import pytest

from roxcal.backends import Backend, make_backend
from roxcal.backends.google_caldav import GoogleCalDAVBackend
from roxcal.backends.google_oauth import GoogleOAuthBackend
from roxcal.backends.microsoft_graph import MicrosoftGraphBackend
from roxcal.backends.nextcloud_caldav import NextcloudCalDAVBackend
from roxcal.config import Account


def test_make_backend_google_oauth():
    acc = Account(name="x", backend="google_oauth", email="a@b.com")
    b = make_backend(acc)
    assert isinstance(b, GoogleOAuthBackend)
    assert b.account is acc


def test_make_backend_google_caldav():
    acc = Account(name="x", backend="google_caldav", email="a@b.com")
    b = make_backend(acc)
    assert isinstance(b, GoogleCalDAVBackend)


def test_make_backend_microsoft_graph():
    acc = Account(name="x", backend="microsoft_graph", email="a@b.com")
    b = make_backend(acc)
    assert isinstance(b, MicrosoftGraphBackend)


def test_make_backend_unknown_exits():
    acc = Account(name="x", backend="not_a_backend", email="a@b.com")
    with pytest.raises(SystemExit):
        make_backend(acc)


def test_base_class_methods_raise_not_implemented():
    acc = Account(name="x", backend="google_oauth")
    b = Backend(acc)
    with pytest.raises(NotImplementedError):
        b.init()
    with pytest.raises(NotImplementedError):
        b.list_calendars()
    with pytest.raises(NotImplementedError):
        list(b.list_events(start=None, end=None))
    with pytest.raises(NotImplementedError):
        b.create_event(title="", start=None, end=None)
    with pytest.raises(NotImplementedError):
        b.rsvp("evt", "accepted")
    with pytest.raises(NotImplementedError):
        b.get_event("evt")
    with pytest.raises(NotImplementedError):
        b.delete_event("evt")
    with pytest.raises(NotImplementedError):
        b.update_event("evt")


def test_caldav_client_works_with_username_only(monkeypatch):
    acc = Account(
        name="cloud",
        backend="nextcloud_caldav",
        caldav_url="https://nc.example.com/remote.php/dav/",
        caldav_username="bob",
        caldav_password="pw",
    )
    b = NextcloudCalDAVBackend(acc)
    captured = {}

    class _StubClient:
        def __init__(self, *, url, username, password):
            captured["url"] = url
            captured["username"] = username
            captured["password"] = password

    monkeypatch.setattr("caldav.DAVClient", _StubClient)
    b._client()
    assert captured["username"] == "bob"
    assert captured["password"] == "pw"


def test_caldav_client_dies_without_password():
    acc = Account(
        name="cloud",
        backend="nextcloud_caldav",
        caldav_url="https://nc.example.com/remote.php/dav/",
        caldav_username="bob",
        email="",
    )
    b = NextcloudCalDAVBackend(acc)
    with pytest.raises(SystemExit):
        b._client()


def test_caldav_client_dies_without_username_or_email():
    acc = Account(
        name="cloud",
        backend="nextcloud_caldav",
        caldav_url="https://nc.example.com/remote.php/dav/",
        caldav_password="pw",
    )
    b = NextcloudCalDAVBackend(acc)
    with pytest.raises(SystemExit):
        b._client()


def test_google_caldav_resolve_url_requires_email():
    acc = Account(
        name="g",
        backend="google_caldav",
        caldav_url="https://apidata.googleusercontent.com/caldav/v2",
    )
    b = GoogleCalDAVBackend(acc)
    with pytest.raises(SystemExit):
        b._resolve_url(acc.caldav_url)


def test_quick_add_default_dies():
    acc = Account(name="x", backend="microsoft_graph")
    b = Backend(acc)
    with pytest.raises(SystemExit):
        b.quick_add("anything")


def test_select_calendars_no_filter_returns_all():
    acc = Account(name="x", backend="google_oauth")
    b = Backend(acc)
    result = b._select_calendars({"a": "A", "b": "B"}, None, False)
    assert result == {"a": "A", "b": "B"}


def test_select_calendars_explicit_request_wins():
    acc = Account(name="x", backend="google_oauth", calendars=["b"])
    b = Backend(acc)
    result = b._select_calendars({"a": "A", "b": "B", "c": "C"}, ["a"], False)
    assert result == {"a": "A"}


def test_select_calendars_falls_back_to_account_calendars():
    acc = Account(name="x", backend="google_oauth", calendars=["b"])
    b = Backend(acc)
    result = b._select_calendars({"a": "A", "b": "B"}, None, False)
    assert result == {"b": "B"}


def test_select_calendars_all_calendars_overrides_account_filter():
    acc = Account(name="x", backend="google_oauth", calendars=["b"])
    b = Backend(acc)
    result = b._select_calendars({"a": "A", "b": "B"}, None, True)
    assert result == {"a": "A", "b": "B"}


def test_select_calendars_drops_inaccessible_entries():
    acc = Account(name="x", backend="google_oauth")
    b = Backend(acc)
    result = b._select_calendars({"a": "A"}, ["a", "missing"], False)
    assert result == {"a": "A"}


class _StubBackend(Backend):
    def __init__(self, events):
        super().__init__(Account(name="x", backend="google_oauth"))
        self._events = events

    def list_events(self, start, end, calendars=None, all_calendars=False):
        yield from self._events


def test_search_default_matches_title_case_insensitive():
    b = _StubBackend(
        [
            {"title": "Standup with Maria", "location": "", "start": "x"},
            {"title": "Lunch", "location": "", "start": "y"},
        ]
    )
    found = list(b.search("standup", None, None))
    assert [e["title"] for e in found] == ["Standup with Maria"]


def test_search_default_matches_location():
    b = _StubBackend(
        [
            {"title": "Standup", "location": "Room 5"},
            {"title": "Lunch", "location": "Cafeteria"},
        ]
    )
    found = list(b.search("room", None, None))
    assert [e["title"] for e in found] == ["Standup"]


def test_search_default_skips_when_no_match():
    b = _StubBackend([{"title": "Standup", "location": "Room 5"}])
    assert list(b.search("nothere", None, None)) == []


def test_search_default_handles_missing_fields():
    b = _StubBackend([{"start": "x"}, {"title": "ok"}])
    assert list(b.search("ok", None, None)) == [{"title": "ok"}]
