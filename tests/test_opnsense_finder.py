from os_download.finders.opnsense import OPNsenseFinder


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def get(self, url, timeout=None):
        if url.endswith("/releases/"):
            return FakeResponse('<a href="24.7/">24.7/</a>')
        return FakeResponse('<a href="OPNsense-24.7-dvd-amd64.iso.bz2">iso</a>')


def test_opnsense_does_not_return_unverified_url():
    finder = OPNsenseFinder(timeout=1)
    finder.session = FakeSession()
    finder.verify_download_url = lambda url: False

    assert finder.find_download_links() == {}
