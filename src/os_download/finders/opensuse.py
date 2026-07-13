from os_download.finders.base import BaseOSFinder


class OpenSUSETumbleweedFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("openSUSE Tumbleweed", timeout)
        self.iso_base = "https://download.opensuse.org/tumbleweed/iso/"

    def find_download_links(self) -> dict[str, str]:
        candidates = {
            "dvd": f"{self.iso_base}openSUSE-Tumbleweed-DVD-x86_64-Current.iso",
            "kde-live": f"{self.iso_base}openSUSE-Tumbleweed-KDE-Live-x86_64-Current.iso",
            "gnome-live": f"{self.iso_base}openSUSE-Tumbleweed-GNOME-Live-x86_64-Current.iso",
            "netinstall": f"{self.iso_base}openSUSE-Tumbleweed-NET-x86_64-Current.iso",
        }
        return {
            variant: url
            for variant, url in candidates.items()
            if self.verify_download_url(url)
        }
