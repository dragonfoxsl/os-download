import re

from os_download.finders.base import BaseOSFinder


class ManjaroKDEFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("Manjaro KDE", timeout)
        self.products_url = "https://manjaro.org/products/download/x86"
        self.download_url = "https://manjaro.org/download/"

    def find_download_links(self) -> dict[str, str]:
        try:
            response = self.session.get(self.products_url, timeout=self.timeout)
            response.raise_for_status()
            match = re.search(
                r'href="(https://download\.manjaro\.org/kde/[^"]+\.iso)"',
                response.text,
            )
            if match:
                return {"kde": match.group(1)}
            return {"download_page": self.download_url}
        except Exception:
            return {"download_page": self.download_url}
