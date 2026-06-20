import re
from typing import Dict

from os_download.finders.base import BaseOSFinder


class OPNsenseFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("OPNsense", timeout)
        self.pkg_index = "https://pkg.opnsense.org/releases/"

    def find_download_links(self) -> Dict[str, str]:
        try:
            response = self.session.get(self.pkg_index, timeout=self.timeout)
            response.raise_for_status()
            versions = re.findall(r'href="(\d+\.\d+)/"', response.text)
            if not versions:
                return {}
            versions.sort(key=lambda version: tuple(map(int, version.split("."))))
            version_url = f"{self.pkg_index}{versions[-1]}/"

            response = self.session.get(version_url, timeout=self.timeout)
            response.raise_for_status()
            isos = re.findall(
                r'href="(OPNsense-[\d.]+-dvd-amd64\.iso(?:\.bz2)?)"',
                response.text,
                re.IGNORECASE,
            )
            if not isos:
                return {}
            isos.sort(
                key=lambda name: tuple(
                    int(part)
                    for part in re.findall(
                        r"\d+",
                        re.search(r"OPNsense-([\d.]+)-", name).group(1),
                    )
                )
            )
            url = version_url + isos[-1]
            return {"amd64": url} if self.verify_download_url(url) else {}
        except Exception:
            return {}
