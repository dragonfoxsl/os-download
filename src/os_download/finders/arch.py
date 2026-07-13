from os_download.finders.base import BaseOSFinder


class ArchLinuxFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("Arch Linux", timeout)
        self.iso_url = "https://geo.mirror.pkgbuild.com/iso/latest/archlinux-x86_64.iso"

    def find_download_links(self) -> dict[str, str]:
        if self.verify_download_url(self.iso_url):
            return {"installer": self.iso_url}
        return {"download_page": "https://archlinux.org/download/"}
