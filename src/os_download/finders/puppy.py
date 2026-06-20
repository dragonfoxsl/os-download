import re
from typing import Dict, Optional, Tuple
from urllib.parse import urljoin

from os_download.finders.base import BaseOSFinder


class PuppyLinuxFinder(BaseOSFinder):
    SF_PROJECTS = [
        ("fossapup64", "fossapup"),
        ("bionicpup64", "bionicpup"),
    ]
    VARIANT_DIRS = ["puppy-trixie", "puppy-bookwormpup", "puppy-fossa", "puppy-bionic"]

    def __init__(self, timeout: int = 15):
        super().__init__("Puppy Linux", timeout)
        self.distro_url = "http://distro.ibiblio.org/puppylinux/"
        self.download_url = "http://puppylinux-woof-ce.github.io/woof-CE/index.html#downloads"

    def _try_sourceforge(self) -> Optional[Tuple[str, str]]:
        for project, variant in self.SF_PROJECTS:
            try:
                response = self.session.get(
                    f"https://sourceforge.net/projects/{project}/files/",
                    timeout=self.timeout,
                )
                if response.status_code != 200:
                    continue
                subdirs = re.findall(r'title="([\d.]+)"', response.text)
                if subdirs:
                    subdirs.sort(
                        key=lambda version: tuple(int(part) for part in re.findall(r"\d+", version) or ["0"])
                    )
                    latest = subdirs[-1]
                    response = self.session.get(
                        f"https://sourceforge.net/projects/{project}/files/{latest}/",
                        timeout=self.timeout,
                    )
                    if response.status_code == 200:
                        isos = re.findall(r'title="([\w.-]+\.iso)"', response.text, re.IGNORECASE)
                        if isos:
                            iso = next((item for item in isos if "64" in item), isos[0])
                            url = f"https://downloads.sourceforge.net/project/{project}/{latest}/{iso}"
                            return variant, url
                isos = re.findall(r'title="([\w.-]+\.iso)"', response.text, re.IGNORECASE)
                if isos:
                    iso = next((item for item in isos if "64" in item), isos[0])
                    url = f"https://downloads.sourceforge.net/project/{project}/{iso}"
                    return variant, url
            except Exception:
                continue
        return None

    def find_download_links(self) -> Dict[str, str]:
        sourceforge_result = self._try_sourceforge()
        if sourceforge_result:
            variant, url = sourceforge_result
            return {variant: url}

        for dirname in self.VARIANT_DIRS:
            dir_url = f"{self.distro_url}{dirname}/"
            try:
                response = self.session.get(dir_url, timeout=self.timeout)
                if response.status_code != 200:
                    continue
                isos = re.findall(r'href="([^"]*\.iso)"', response.text, re.IGNORECASE)
                if not isos:
                    continue
                iso = next((item for item in isos if "64" in item), isos[0])
                url = urljoin(dir_url, iso)
                return {dirname.replace("puppy-", ""): url}
            except Exception:
                continue

        return {"download_page": self.download_url}
