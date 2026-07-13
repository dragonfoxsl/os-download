import re
from urllib.parse import urljoin

from os_download.finders.base import BaseOSFinder


class RockyLinuxFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("Rocky Linux", timeout)
        self.base_url = "https://download.rockylinux.org/pub/rocky/"

    def find_download_links(self) -> dict[str, str]:
        try:
            response = self.session.get(self.base_url, timeout=self.timeout)
            response.raise_for_status()
            major_versions = re.findall(r'href="(\d+)/"', response.text)
            if not major_versions:
                return {"download_page": "https://rockylinux.org/download"}

            latest_major = sorted(major_versions, key=int)[-1]
            iso_base = urljoin(self.base_url, f"{latest_major}/isos/x86_64/")
            response = self.session.get(iso_base, timeout=self.timeout)
            response.raise_for_status()

            candidates = {}
            for variant, pattern in [
                ("dvd", r'href="([^"]*x86_64[^"]*(?:dvd|DVD)[^"]*\.iso)"'),
                ("minimal", r'href="([^"]*x86_64[^"]*(?:minimal|Minimal)[^"]*\.iso)"'),
            ]:
                match = re.search(pattern, response.text)
                if match:
                    candidates[variant] = urljoin(iso_base, match.group(1))

            return {
                variant: url
                for variant, url in candidates.items()
                if self.verify_download_url(url)
            }
        except Exception as exc:
            self.log_failure(exc)
            return {"download_page": "https://rockylinux.org/download"}
