from os_download.finders.truenas import TrueNASFinder


class FakeResponse:
    status_code = 200
    text = """
        <a href="https://download.sys.truenas.net/TrueNAS-SCALE-Goldeye/25.10.7/TrueNAS-SCALE-25.10.7.iso">stable</a>
        <a href="https://download.sys.truenas.net/TrueNAS-SCALE-Goldeye/25.10.6/TrueNAS-SCALE-25.10.6.iso">older</a>
        <a href="https://iso.sys.truenas.net/TrueNAS-26-BETA/26.0.0-BETA.3/TrueNAS-26.0.0-BETA.3.iso">beta</a>
    """

    def raise_for_status(self):
        return None


class FakeSession:
    def get(self, url, timeout=None):
        return FakeResponse()


def test_truenas_returns_the_newest_stable_iso_from_the_official_page(monkeypatch):
    finder = TrueNASFinder(timeout=1)
    finder.session = FakeSession()
    monkeypatch.setattr(finder, "verify_download_url", lambda url: True)

    assert finder.find_download_links() == {
        "scale": (
            "https://download.sys.truenas.net/TrueNAS-SCALE-Goldeye/25.10.7/"
            "TrueNAS-SCALE-25.10.7.iso"
        )
    }


def test_truenas_returns_download_page_when_no_stable_iso_is_published(monkeypatch):
    finder = TrueNASFinder(timeout=1)
    finder.session = FakeSession()
    FakeResponse.text = "<a href='https://example.test/TrueNAS-26.0.0-BETA.3.iso'>beta</a>"
    monkeypatch.setattr(finder, "verify_download_url", lambda url: True)

    assert finder.find_download_links() == {"download_page": finder.download_page}
