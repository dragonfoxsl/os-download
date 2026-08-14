import re
from urllib.parse import urljoin

from os_download.finders.base import BaseOSFinder


class FedoraFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("Fedora", timeout)
        self.base_urls = [
            "https://download.fedoraproject.org/pub/fedora/linux/releases/",
            "https://mirrors.kernel.org/fedora/releases/",
            "https://mirrors.edge.kernel.org/fedora/releases/",
        ]

    def _latest_release_base(self) -> str | None:
        for base_url in self.base_urls:
            try:
                response = self.session.get(base_url, timeout=self.timeout)
                response.raise_for_status()
                versions = re.findall(r'href="(\d+)/"', response.text)
                if versions:
                    latest = sorted(versions, key=int)[-1]
                    return urljoin(base_url, f"{latest}/")
            except Exception as exc:
                self.log_failure(exc)
        return None

    def _find_variant(self, release_base: str, directory: str, pattern: str) -> str | None:
        iso_base = urljoin(release_base, directory)
        try:
            response = self.session.get(iso_base, timeout=self.timeout)
            response.raise_for_status()
            match = re.search(pattern, response.text, re.IGNORECASE)
            if match:
                return urljoin(iso_base, match.group(1))
        except Exception as exc:
            self.log_failure(exc)
        return None

    def find_download_links(self) -> dict[str, str]:
        release_base = self._latest_release_base()
        if not release_base:
            return {"download_page": "https://fedoraproject.org/workstation/download"}

        candidates = {
            "workstation": self._find_variant(
                release_base,
                "Workstation/x86_64/iso/",
                r'href="([^"]*Fedora-Workstation[^"]*x86_64[^"]*\.iso)"',
            ),
            "server": self._find_variant(
                release_base,
                "Server/x86_64/iso/",
                r'href="([^"]*Fedora-Server[^"]*(?:dvd|netinst)[^"]*x86_64[^"]*\.iso)"',
            ),
        }

        return {
            variant: url
            for variant, url in candidates.items()
            if url and self.verify_download_url(url)
        }
