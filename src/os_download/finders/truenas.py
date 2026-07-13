
from os_download.finders.base import BaseOSFinder


class TrueNASFinder(BaseOSFinder):
    codenames = {
        "25.04": "Fangtooth",
        "24.10": "Electric-Eel",
        "24.04": "Dragonfish",
    }
    download_page = "https://www.truenas.com/download-truenas-scale/"

    def __init__(self, timeout: int = 15):
        super().__init__("TrueNAS Scale", timeout)
        self.github_api = "https://api.github.com/repos/truenas/truenas-scale/releases/latest"
        self.download_base = "https://download.sys.truenas.net/TrueNAS-SCALE-"

    def find_download_links(self) -> dict[str, str]:
        version = None
        try:
            response = self.session.get(self.github_api, timeout=self.timeout)
            response.raise_for_status()
            tag = response.json().get("tag_name", "")
            version = tag.replace("TrueNAS-SCALE-", "").strip() or None
        except Exception as exc:
            self.log_failure(exc)
            pass

        if not version:
            version = "25.04.1"

        major_minor = ".".join(version.split(".")[:2])
        codename = self.codenames.get(major_minor)
        if codename is None:
            return {"download_page": self.download_page}

        url = f"{self.download_base}{codename}/{version}/TrueNAS-SCALE-{version}.iso"
        return {"scale": url}
