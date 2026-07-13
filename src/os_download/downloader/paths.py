import hashlib
import os
import platform
import re
from pathlib import Path
from urllib.parse import urlparse

_UNSAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9._-]")


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
    filename = _UNSAFE_CHARS_RE.sub("_", os.path.basename(urlparse(url).path)).lstrip(".")
    if not filename or "." not in filename:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
        filename = f"download_{digest}.bin"
    return filename
