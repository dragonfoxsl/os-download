import re
from typing import Dict

from os_download.finders.base import BaseOSFinder


class PfSenseFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("pfSense CE", timeout)
        self.cdn_url = "https://atxfiles.netgate.com/mirror/downloads/"

    def find_download_links(self) -> Dict[str, str]:
        try:
            response = self.session.get(self.cdn_url, timeout=self.timeout)
            response.raise_for_status()
            isos = re.findall(r'href="(pfSense-CE-([\d.]+)-RELEASE-amd64\.iso\.gz)"', response.text)
            if not isos:
                return {"download_page": "https://www.pfsense.org/download/"}
            isos.sort(key=lambda match: tuple(map(int, match[1].split("."))))
            filename = isos[-1][0]
            url = self.cdn_url + filename
            return {"amd64": url}
        except Exception:
            return {"download_page": "https://www.pfsense.org/download/"}
