import hashlib
from pathlib import Path
from typing import Optional

import requests


def hash_file(filepath: Path) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest().lower()


def verify_checksum(session: requests.Session, filepath: Path, url: str) -> Optional[bool]:
    fname = filepath.name

    try:
        response = session.get(url + ".sha256", timeout=10)
        if response.status_code == 200:
            expected = response.text.strip().split()[0]
            return hash_file(filepath) == expected.lower()
    except Exception:
        pass

    directory_sums_url = url.rsplit("/", 1)[0] + "/SHA256SUMS"
    try:
        response = session.get(directory_sums_url, timeout=10)
        if response.status_code == 200:
            for line in response.text.splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2 and parts[1].lstrip("* ") == fname:
                    return hash_file(filepath) == parts[0].lower()
    except Exception:
        pass

    return None
