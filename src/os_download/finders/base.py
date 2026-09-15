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
        head_status = None
        get_status = None
        try:
            response = self.session.head(url, allow_redirects=True, timeout=self.timeout)
            head_status = response.status_code
            getattr(response, "close", lambda: None)()
            if head_status == 200:
                return True

            response = self.session.get(
                url,
                headers={"Range": "bytes=0-0"},
                stream=True,
                allow_redirects=True,
                timeout=self.timeout,
            )
            get_status = response.status_code
            getattr(response, "close", lambda: None)()
            if get_status in (200, 206):
                return True
        except Exception as exc:
            logger.debug("URL verification failed for %s: %s", url, exc)
            return False

        logger.warning(
            "URL UNREACHABLE  %s  HEAD=%s GET=%s",
            url,
            head_status,
            get_status,
        )
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
