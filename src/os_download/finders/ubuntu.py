import re
from typing import Dict, Optional, Tuple
from urllib.parse import urljoin

from os_download.finders.base import BaseOSFinder


class UbuntuFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("Ubuntu", timeout)
        self.base_url = "http://releases.ubuntu.com/"
        self.api_url = "https://api.launchpad.net/1.0/ubuntu/series"

    def _get_versions(self) -> Tuple[Optional[str], Optional[str]]:
        try:
            response = self.session.get(self.api_url, timeout=self.timeout)
            response.raise_for_status()
            entries = response.json().get("entries", [])
            supported = [entry for entry in entries if entry.get("supported") and entry.get("version")]
            supported.sort(key=lambda entry: tuple(map(int, entry["version"].split("."))))

            if supported:
                latest = supported[-1]["version"]
                lts_entries = [entry for entry in supported if "LTS" in entry.get("displayname", "")]
                lts = lts_entries[-1]["version"] if lts_entries else latest
                return latest, lts
        except Exception:
            pass

        try:
            response = self.session.get(self.base_url, timeout=self.timeout)
            response.raise_for_status()
            versions = re.findall(r'href="(\d+\.\d+)/"', response.text)
            if versions:
                versions.sort(key=lambda version: tuple(map(int, version.split("."))))
                latest = versions[-1]
                lts_candidates = [
                    version
                    for version in versions
                    if int(version.split(".")[0]) % 2 == 0 and int(version.split(".")[1]) == 4
                ]
                lts = lts_candidates[-1] if lts_candidates else latest
                return latest, lts
        except Exception:
            pass

        return None, None

    def _links_for_version(self, version: str) -> Dict[str, str]:
        base_url = f"{self.base_url}{version}/"
        links = {
            "desktop": f"{base_url}ubuntu-{version}-desktop-amd64.iso",
            "server": f"{base_url}ubuntu-{version}-live-server-amd64.iso",
        }
        try:
            response = self.session.get(base_url, timeout=self.timeout)
            if response.status_code == 200:
                for key, pattern in [
                    ("desktop", r'href="([^"]*ubuntu[^"]*desktop[^"]*\.iso)"'),
                    ("server", r'href="([^"]*ubuntu[^"]*live-server[^"]*\.iso)"'),
                ]:
                    match = re.search(pattern, response.text, re.IGNORECASE)
                    if match:
                        links[key] = urljoin(base_url, match.group(1))
        except Exception:
            pass
        return links

    def find_download_links(self) -> Dict[str, str]:
        latest_version, lts_version = self._get_versions()
        if not lts_version and not latest_version:
            return {}

        result = {}
        same = latest_version == lts_version

        if lts_version:
            prefix = "" if same else "lts-"
            for variant, url in self._links_for_version(lts_version).items():
                if self.verify_download_url(url):
                    result[f"{prefix}{variant}"] = url

        if latest_version and not same:
            for variant, url in self._links_for_version(latest_version).items():
                if self.verify_download_url(url):
                    result[f"latest-{variant}"] = url

        return result
