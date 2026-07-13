import re
from urllib.parse import urljoin

from os_download.finders.base import BaseOSFinder


class LinuxMintFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("Linux Mint", timeout)
        self.base_url = "https://mirrors.edge.kernel.org/linuxmint/stable/"

    def find_download_links(self) -> dict[str, str]:
        try:
            response = self.session.get(self.base_url, timeout=self.timeout)
            response.raise_for_status()
            versions = re.findall(r'href="(\d+(?:\.\d+)*)/"', response.text)
            if not versions:
                return {"download_page": "https://linuxmint.com/download.php"}

            latest = sorted(
                versions,
                key=lambda version: tuple(int(part) for part in version.split(".")),
            )[-1]
            version_url = urljoin(self.base_url, f"{latest}/")
            response = self.session.get(version_url, timeout=self.timeout)
            response.raise_for_status()
            match = re.search(
                r'href="(linuxmint-[^"]*-cinnamon-64bit\.iso)"',
                response.text,
                re.IGNORECASE,
            )
            if not match:
                return {"download_page": "https://linuxmint.com/download.php"}

            url = urljoin(version_url, match.group(1))
            if self.verify_download_url(url):
                return {"cinnamon": url}
        except Exception as exc:
            self.log_failure(exc)
            pass
        return {"download_page": "https://linuxmint.com/download.php"}
