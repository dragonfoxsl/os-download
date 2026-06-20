from os_download.finders import registry


class FakeFinder:
    def __init__(self):
        self.name = "Fake OS"
        self.session = object()

    def find_download_links(self):
        return {"amd64": "https://example.com/fake.iso"}


def test_find_all_links_quiet_skips_progress(monkeypatch):
    finder = registry.MultiOSDownloadFinder(timeout=1)
    finder.finders = {"fake": FakeFinder()}

    def fail_progress(*args, **kwargs):
        raise AssertionError("Progress should not be used in quiet mode")

    monkeypatch.setattr(registry, "Progress", fail_progress)

    assert finder.find_all_links(["fake"], interactive=False, quiet=True) == {
        "fake": {"amd64": "https://example.com/fake.iso"}
    }
