import os
import platform
from pathlib import Path
from urllib.parse import urlparse


def default_download_dir() -> Path:
    system = platform.system()
    home = Path.home()
    if system in ("Windows", "Darwin"):
        base = home / "Downloads"
    else:
        xdg = os.environ.get("XDG_DOWNLOAD_DIR")
        base = Path(xdg) if xdg else home / "Downloads"
    return base / "os-isos"


def filename_from_url(url: str) -> str:
    filename = os.path.basename(urlparse(url).path)
    if not filename or "." not in filename:
        filename = f"download_{url[-8:]}.bin"
    return filename
