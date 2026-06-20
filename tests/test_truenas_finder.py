from os_download.finders.truenas import TrueNASFinder


class FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"tag_name": "TrueNAS-SCALE-99.01.0"}


class FakeSession:
    def get(self, url, timeout=None):
        return FakeResponse()


def test_truenas_unknown_codename_returns_download_page():
    finder = TrueNASFinder(timeout=1)
    finder.session = FakeSession()

    assert finder.find_download_links() == {
        "download_page": "https://www.truenas.com/download-truenas-scale/"
    }
