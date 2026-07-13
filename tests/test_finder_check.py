from os_download.cli.finder import _run_check
from os_download.finders.registry import MultiOSDownloadFinder


class FakeFinder:
    def __init__(self, name: str, links: dict[str, str]):
        self.name = name
        self.links = links
        self.session = object()

    def find_download_links(self) -> dict[str, str]:
        return self.links


def build_finder(finders: dict[str, FakeFinder]) -> MultiOSDownloadFinder:
    finder = MultiOSDownloadFinder(timeout=1)
    finder.finders = finders
    return finder


def test_check_passes_when_every_finder_resolves_an_iso():
    finder = build_finder(
        {
            "ubuntu": FakeFinder("Ubuntu", {"desktop": "https://example.test/ubuntu.iso"}),
            "windows11": FakeFinder("Windows 11", {"x64": "mido://win11x64"}),
        }
    )

    assert _run_check(finder, ["ubuntu", "windows11"]) == 0


def test_check_fails_when_a_finder_only_resolves_a_download_page():
    # What mirror drift actually looks like: the finder still returns something,
    # but it has fallen back to the human download page instead of an ISO.
    finder = build_finder(
        {
            "ubuntu": FakeFinder("Ubuntu", {"desktop": "https://example.test/ubuntu.iso"}),
            "rocky": FakeFinder("Rocky Linux", {"download_page": "https://rockylinux.org/download"}),
        }
    )

    assert _run_check(finder, ["ubuntu", "rocky"]) == 1


def test_check_fails_when_a_finder_resolves_nothing():
    finder = build_finder({"arch": FakeFinder("Arch Linux", {})})

    assert _run_check(finder, ["arch"]) == 1
