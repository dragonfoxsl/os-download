import logging

import requests

from os_download.http import get_session

ISO_EXTS = (".iso", ".iso.bz2", ".iso.gz")

logger = logging.getLogger("os_finder")


class BaseOSFinder:
    def __init__(self, name: str, timeout: int = 15):
        self.name = name
        self.timeout = timeout
        self._session: requests.Session | None = None

    @property
    def session(self) -> requests.Session:
        return self._session if self._session is not None else get_session()

    @session.setter
    def session(self, session: requests.Session) -> None:
        self._session = session

    def log_failure(self, exc: Exception, context: str = "") -> None:
        """Mirror lookups fail routinely; record why so a layout change is diagnosable."""
        logger.debug("LOOKUP_FAILED  %-14s  %s  -  %s", self.name, context, exc)

    def verify_download_url(self, url: str) -> bool:
        try:
            response = self.session.head(url, timeout=self.timeout, allow_redirects=True)
            return response.status_code == 200
        except Exception as exc:
            self.log_failure(exc, url)
            return False

    def find_download_links(self) -> dict[str, str]:
        raise NotImplementedError


def has_iso_link(links: dict[str, str]) -> bool:
    return any(
        url.lower().endswith(ISO_EXTS) or url.startswith("mido://")
        for url in links.values()
    )


def url_kind(url: str) -> tuple[str, str]:
    if url.startswith("mido://"):
        return "Mido", "blue"
    if url.lower().endswith(ISO_EXTS):
        return "ISO", "green"
    return "link", "yellow"
