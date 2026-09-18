from os_download.finders.fedora import FedoraFinder


class FakeResponse:
    def __init__(self, url: str, text: str):
        self.url = url
        self.text = text

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, response: FakeResponse):
        self.response = response

    def get(self, url, timeout):
        return self.response


def test_latest_release_uses_the_mirror_that_served_the_redirected_listing():
    finder = FedoraFinder()
    finder.base_urls = ["https://redirect.example/releases/"]
    finder.session = FakeSession(
        FakeResponse("https://mirror.example/fedora/releases/", '<a href="44/">44</a>')
    )

    assert finder._latest_release_bases() == ["https://mirror.example/fedora/releases/44/"]


def test_variant_url_is_resolved_against_the_mirror_response():
    finder = FedoraFinder()
    finder.session = FakeSession(
        FakeResponse(
            "https://mirror.example/fedora/releases/44/Workstation/x86_64/iso/",
            '<a href="Fedora-Workstation-Live-44-1.7.x86_64.iso">ISO</a>',
        )
    )

    assert finder._find_variant(
        "https://redirect.example/releases/44/",
        "Workstation/x86_64/iso/",
        r'href="([^"]+\.iso)"',
    ) == (
        "https://mirror.example/fedora/releases/44/Workstation/x86_64/iso/"
        "Fedora-Workstation-Live-44-1.7.x86_64.iso"
    )


def test_finder_tries_the_next_release_mirror_when_the_first_has_no_isos(monkeypatch):
    finder = FedoraFinder()
    monkeypatch.setattr(finder, "_latest_release_bases", lambda: ["bad/", "good/"])
    monkeypatch.setattr(
        finder,
        "_find_variant",
        lambda release, directory, pattern: None if release == "bad/" else f"{release}{directory}x.iso",
    )
    monkeypatch.setattr(finder, "verify_download_url", lambda url: True)

    links = finder.find_download_links()

    assert set(links) == {"workstation", "server"}
    assert all(url.startswith("good/") for url in links.values())
