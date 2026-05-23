Name:      roxcal
Version:   0.1.0
Release:   0%{?dist}
Summary:   Unified CLI for Google, Microsoft and CalDAV calendars
License:   MIT
URL:       https://gitlab.com/aroxell/roxcal
Source0:   %{pypi_source}


BuildRequires: git
BuildRequires: make
BuildRequires: python3-devel
BuildRequires: python3-flit
BuildRequires: python3-pip
BuildRequires: python3-pytest
BuildRequires: python3-pytest-cov
BuildRequires: python3-pytest-mock

BuildArch: noarch

Requires: python3 >= 3.10
Requires: python3-google-auth
Requires: python3-google-auth-oauthlib
Requires: python3-google-api-client
Requires: python3-msal
Requires: python3-requests
Requires: python3-caldav
Requires: python3-icalendar
Requires: python3-dateutil

%global debug_package %{nil}

%description
A single command line tool for reading and writing calendars across
Google Calendar (REST API and CalDAV) and Microsoft Outlook (Microsoft
Graph). Includes a vim plugin for interactive use.

%prep
%setup -q

%build
export FLIT_NO_NETWORK=1
make run

%check
python3 -m pytest test/

%install
mkdir -p %{buildroot}/usr/share/%{name}/
cp -r run %{dist} %{buildroot}/usr/share/%{name}/
mkdir -p %{buildroot}/usr/bin
ln -sf ../share/%{name}/run %{buildroot}/usr/bin/%{name}

%files
/usr/share/%{name}
%{_bindir}/%{name}

%doc README.md

%changelog

* Wed May 27 2026 Anders Roxell <anders.roxell@linaro.org> - 0.1.0-1
- Initial release.
