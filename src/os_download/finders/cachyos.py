import re
from typing import Dict

from os_download.finders.base import BaseOSFinder


class CachyOSFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("CachyOS", timeout)
        self.mirror_base = "https://mirror.cachyos.org/ISO/desktop/"

    def find_download_links(self) -> Dict[str, str]:
        try:
            response = self.session.get(self.mirror_base, timeout=self.timeout)
            response.raise_for_status()
            versions = re.findall(r'href="(\d{6})/"', response.text)
            if not versions:
                return {"download_page": "https://cachyos.org/download/"}

            versions.sort()
            version_url = f"{self.mirror_base}{versions[-1]}/"
            response = self.session.get(version_url, timeout=self.timeout)
            match = re.search(r'href="(cachyos-desktop-linux-[^"]+\.iso)"', response.text)
            if not match:
                return {"download_page": "https://cachyos.org/download/"}

            return {"desktop": version_url + match.group(1)}
        except Exception:
            return {"download_page": "https://cachyos.org/download/"}
