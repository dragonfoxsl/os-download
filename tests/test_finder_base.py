from os_download.finders.base import BaseOSFinder, has_iso_link, url_kind


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.closed = False

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, head_status: int, get_status: int):
        self.head_status = head_status
        self.get_status = get_status
        self.get_kwargs = None

    def head(self, url, allow_redirects=True, timeout=15):
        return FakeResponse(self.head_status)

    def get(self, url, **kwargs):
        self.get_kwargs = kwargs
        return FakeResponse(self.get_status)


def test_verify_download_url_falls_back_to_a_one_byte_range_request():
    finder = BaseOSFinder("test", timeout=3)
    session = FakeSession(head_status=405, get_status=206)
    finder.session = session

    assert finder.verify_download_url("https://example.test/image.iso")
    assert session.get_kwargs == {
        "headers": {"Range": "bytes=0-0"},
        "stream": True,
        "allow_redirects": True,
        "timeout": 3,
    }


def test_verify_download_url_rejects_failed_head_and_get_requests():
    finder = BaseOSFinder("test", timeout=3)
    finder.session = FakeSession(head_status=404, get_status=404)

    assert not finder.verify_download_url("https://example.test/missing.iso")


def test_iso_detection_uses_the_url_path():
    url = "https://example.test/image.iso?token=temporary#download"

    assert has_iso_link({"override": url})
    assert url_kind(url) == ("ISO", "green")


def test_iso_detection_rejects_malformed_urls():
    url = "https://[invalid/image.iso"

    assert not has_iso_link({"override": url})
    assert url_kind(url) == ("link", "yellow")
