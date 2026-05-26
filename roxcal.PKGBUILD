pkgname=roxcal
pkgver=0.1.0
pkgrel=1
pkgdesc='Unified CLI for Google, Microsoft and CalDAV calendars'
url='https://gitlab.com/aroxell/roxcal'
license=('MIT')
arch=('any')
depends=('python' 'python-google-auth' 'python-google-auth-oauthlib'
         'python-google-api-python-client' 'python-msal' 'python-requests'
         'python-caldav' 'python-icalendar' 'python-dateutil')
makedepends=('git' 'python-build' 'python-flit' 'python-installer' 'python-wheel')
checkdepends=('python-pytest' 'python-pytest-mock')
source=("$pkgname-$pkgver.tar.gz")
sha256sums=('SKIP')

build() {
  cd "$pkgname-$pkgver"
  python -m build --wheel --no-isolation
}

check() {
  cd "$pkgname-$pkgver"
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD" pytest
}

package() {
  cd "$pkgname-$pkgver"
  python -m installer --destdir="$pkgdir" dist/*.whl
  install -Dvm644 README.md -t "$pkgdir/usr/share/doc/$pkgname"
  install -Dvm644 plugin/roxcal.vim -t "$pkgdir/usr/share/vim/vimfiles/plugin"
  install -Dvm644 syntax/roxcal.vim -t "$pkgdir/usr/share/vim/vimfiles/syntax"
  install -Dvm644 completions/roxcal.bash "$pkgdir/usr/share/bash-completion/completions/roxcal"
  install -Dvm644 completions/roxcal.zsh "$pkgdir/usr/share/zsh/site-functions/_roxcal"
  install -Dvm644 completions/roxcal.fish "$pkgdir/usr/share/fish/vendor_completions.d/roxcal.fish"
}
