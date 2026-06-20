from typing import Dict, Tuple

from os_download.http import build_session

ISO_EXTS = (".iso", ".iso.bz2", ".iso.gz")
_SESSION = build_session()


class BaseOSFinder:
    def __init__(self, name: str, timeout: int = 15):
        self.name = name
        self.timeout = timeout
        self.session = _SESSION

    def verify_download_url(self, url: str) -> bool:
        try:
            response = self.session.head(url, timeout=self.timeout, allow_redirects=True)
            return response.status_code == 200
        except Exception:
            return False

    def find_download_links(self) -> Dict[str, str]:
        raise NotImplementedError


def has_iso_link(links: Dict[str, str]) -> bool:
    return any(
        url.lower().endswith(ISO_EXTS) or url.startswith("mido://")
        for url in links.values()
    )


def url_kind(url: str) -> Tuple[str, str]:
    if url.startswith("mido://"):
        return "Mido", "blue"
    if url.lower().endswith(ISO_EXTS):
        return "ISO", "green"
    return "link", "yellow"
