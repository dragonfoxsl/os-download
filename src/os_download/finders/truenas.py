import re

from os_download.finders.base import BaseOSFinder


class TrueNASFinder(BaseOSFinder):
    download_page = "https://www.truenas.com/download-truenas-community-edition/"
    _iso_pattern = re.compile(
        r'https://(?:download|iso)\.sys\.truenas\.net/[^"\'<>\s]+'
        r"TrueNAS-SCALE-(\d+(?:\.\d+){2})\.iso",
        re.IGNORECASE,
    )

    def __init__(self, timeout: int = 15):
        super().__init__("TrueNAS SCALE", timeout)

    @staticmethod
    def _version_key(match: re.Match[str]) -> tuple[int, ...]:
        return tuple(int(part) for part in match.group(1).split("."))

    def find_download_links(self) -> dict[str, str]:
        try:
            response = self.session.get(self.download_page, timeout=self.timeout)
            response.raise_for_status()
            matches = list(self._iso_pattern.finditer(response.text))
            for match in sorted(matches, key=self._version_key, reverse=True):
                url = match.group(0)
                if self.verify_download_url(url):
                    return {"scale": url}
        except Exception as exc:
            self.log_failure(exc, self.download_page)

        return {"download_page": self.download_page}
