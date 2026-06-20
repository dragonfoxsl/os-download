
from os_download.finders.base import BaseOSFinder


class Windows11Finder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("Windows 11", timeout)

    def find_download_links(self) -> dict[str, str]:
        return {"win11x64": "mido://win11x64"}
