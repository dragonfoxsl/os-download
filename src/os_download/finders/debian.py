import re

from os_download.finders.base import BaseOSFinder


class DebianFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("Debian", timeout)

    def find_download_links(self) -> dict[str, str]:
        links = {}

        try:
            response = self.session.get(
                "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/",
                timeout=self.timeout,
            )
            if response.status_code == 200:
                match = re.search(r'href="(debian[^"]*netinst\.iso)"', response.text)
                if match:
                    links["netinst"] = (
                        "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/"
                        f"{match.group(1)}"
                    )
        except Exception as exc:
            self.log_failure(exc)

        try:
            response = self.session.get(
                "https://cdimage.debian.org/debian-cd/current/amd64/iso-dvd/",
                timeout=self.timeout,
            )
            if response.status_code == 200:
                match = re.search(r'href="(debian[^"]*DVD-1\.iso)"', response.text)
                if match:
                    links["dvd"] = (
                        "https://cdimage.debian.org/debian-cd/current/amd64/iso-dvd/"
                        f"{match.group(1)}"
                    )
        except Exception as exc:
            self.log_failure(exc)

        return links
