from os_download.finders import registry
from os_download.finders.arch import ArchLinuxFinder
from os_download.finders.debian import DebianFinder
from os_download.finders.fedora import FedoraFinder
from os_download.finders.linuxmint import LinuxMintFinder
from os_download.finders.opensuse import OpenSUSETumbleweedFinder
from os_download.finders.rocky import RockyLinuxFinder


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, responses: dict[str, str]):
        self.responses = responses

    def get(self, url, timeout=None):
        return FakeResponse(self.responses[url])


def test_fedora_returns_latest_workstation_and_server_isos():
    finder = FedoraFinder(timeout=1)
    finder.session = FakeSession(
        {
            "https://download.fedoraproject.org/pub/fedora/linux/releases/": (
                '<a href="41/">41/</a><a href="42/">42/</a>'
            ),
            "https://download.fedoraproject.org/pub/fedora/linux/releases/42/Workstation/x86_64/iso/": (
                '<a href="Fedora-Workstation-Live-x86_64-42-1.1.iso">iso</a>'
            ),
            "https://download.fedoraproject.org/pub/fedora/linux/releases/42/Server/x86_64/iso/": (
                '<a href="Fedora-Server-dvd-x86_64-42-1.1.iso">iso</a>'
            ),
        }
    )
    finder.verify_download_url = lambda url: True

    assert finder.find_download_links() == {
        "workstation": (
            "https://download.fedoraproject.org/pub/fedora/linux/releases/"
            "42/Workstation/x86_64/iso/Fedora-Workstation-Live-x86_64-42-1.1.iso"
        ),
        "server": (
            "https://download.fedoraproject.org/pub/fedora/linux/releases/"
            "42/Server/x86_64/iso/Fedora-Server-dvd-x86_64-42-1.1.iso"
        ),
    }


def test_debian_returns_scraped_isos_without_rechecking_the_same_urls():
    finder = DebianFinder(timeout=1)
    finder.session = FakeSession(
        {
            "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/": (
                '<a href="debian-13.1.0-amd64-netinst.iso">netinst</a>'
            ),
            "https://cdimage.debian.org/debian-cd/current/amd64/iso-dvd/": (
                '<a href="debian-13.1.0-amd64-DVD-1.iso">dvd</a>'
            ),
        }
    )
    def fail_verify(url):
        raise AssertionError("scraped URLs should not be fetched twice")

    finder.verify_download_url = fail_verify

    assert finder.find_download_links() == {
        "netinst": (
            "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/"
            "debian-13.1.0-amd64-netinst.iso"
        ),
        "dvd": (
            "https://cdimage.debian.org/debian-cd/current/amd64/iso-dvd/"
            "debian-13.1.0-amd64-DVD-1.iso"
        ),
    }


def test_opensuse_tumbleweed_returns_current_iso_variants():
    finder = OpenSUSETumbleweedFinder(timeout=1)
    finder.verify_download_url = lambda url: True

    assert finder.find_download_links() == {
        "dvd": "https://download.opensuse.org/tumbleweed/iso/openSUSE-Tumbleweed-DVD-x86_64-Current.iso",
        "kde-live": "https://download.opensuse.org/tumbleweed/iso/openSUSE-Tumbleweed-KDE-Live-x86_64-Current.iso",
        "gnome-live": "https://download.opensuse.org/tumbleweed/iso/openSUSE-Tumbleweed-GNOME-Live-x86_64-Current.iso",
        "netinstall": "https://download.opensuse.org/tumbleweed/iso/openSUSE-Tumbleweed-NET-x86_64-Current.iso",
    }


def test_arch_returns_latest_iso_alias():
    finder = ArchLinuxFinder(timeout=1)
    finder.verify_download_url = lambda url: True

    assert finder.find_download_links() == {
        "installer": "https://geo.mirror.pkgbuild.com/iso/latest/archlinux-x86_64.iso"
    }


def test_linux_mint_returns_latest_cinnamon_iso():
    finder = LinuxMintFinder(timeout=1)
    finder.session = FakeSession(
        {
            "https://mirrors.edge.kernel.org/linuxmint/stable/": (
                '<a href="22.1/">22.1/</a><a href="22.3/">22.3/</a>'
            ),
            "https://mirrors.edge.kernel.org/linuxmint/stable/22.3/": (
                '<a href="linuxmint-22.3-cinnamon-64bit.iso">iso</a>'
            ),
        }
    )
    finder.verify_download_url = lambda url: True

    assert finder.find_download_links() == {
        "cinnamon": (
            "https://mirrors.edge.kernel.org/linuxmint/stable/22.3/"
            "linuxmint-22.3-cinnamon-64bit.iso"
        )
    }


def test_rocky_returns_latest_major_dvd_and_minimal_isos():
    finder = RockyLinuxFinder(timeout=1)
    finder.session = FakeSession(
        {
            "https://download.rockylinux.org/pub/rocky/": (
                '<a href="9/">9/</a><a href="10/">10/</a>'
            ),
            "https://download.rockylinux.org/pub/rocky/10/isos/x86_64/": (
                '<a href="Rocky-10.2-x86_64-dvd.iso">dvd</a>'
                '<a href="Rocky-10.2-x86_64-minimal.iso">minimal</a>'
            ),
        }
    )
    finder.verify_download_url = lambda url: True

    assert finder.find_download_links() == {
        "dvd": "https://download.rockylinux.org/pub/rocky/10/isos/x86_64/Rocky-10.2-x86_64-dvd.iso",
        "minimal": (
            "https://download.rockylinux.org/pub/rocky/10/isos/x86_64/"
            "Rocky-10.2-x86_64-minimal.iso"
        ),
    }


def test_registry_includes_new_os_choices():
    finder = registry.MultiOSDownloadFinder(timeout=1)

    for os_name in ["fedora", "opensuse", "arch", "linuxmint", "rocky"]:
        assert os_name in registry.OS_CHOICES
        assert os_name in finder.finders
