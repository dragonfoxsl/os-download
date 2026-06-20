import re

from os_download.finders.base import BaseOSFinder


class MXLinuxFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("MX Linux", timeout)
        self.sf_rss = "https://sourceforge.net/projects/mx-linux/rss?path=/Final&limit=50"
        self.sf_final = "https://sourceforge.net/projects/mx-linux/files/Final/"

    def find_download_links(self) -> dict[str, str]:
        try:
            response = self.session.get(self.sf_rss, timeout=self.timeout)
            if response.status_code == 200:
                paths = re.findall(
                    r"files/(Final/Xfce/MX-[\d.]+_Xfce_x64\.iso)/download",
                    response.text,
                )
                if paths:
                    paths.sort(
                        key=lambda path: tuple(int(part) for part in re.findall(r"\d+", path)),
                        reverse=True,
                    )
                    return {
                        "xfce-x64": (
                            "https://downloads.sourceforge.net/project/mx-linux/"
                            f"{paths[0]}"
                        )
                    }
        except Exception:
            pass

        return {"download_page": self.sf_final}
