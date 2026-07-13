import hashlib
import logging
import re
from pathlib import Path

import requests

logger = logging.getLogger("os_download")

# Sidecar files sit next to the ISO and hold the hash for that one file.
SIDECAR_SUFFIXES = (".sha256", ".sha256sum", ".SHA256")

# Directory-wide files hold hashes for every image in the directory.
DIRECTORY_FILENAMES = (
    "SHA256SUMS",  # Ubuntu, Debian
    "SHA256SUMS.txt",
    "sha256sum.txt",  # Linux Mint
    "sha256sums.txt",  # Arch Linux
    "CHECKSUM",  # Rocky
)

# Fedora names the file after the release (Fedora-Workstation-42-x86_64-CHECKSUM), so the
# directory index is scraped for anything checksum-shaped once the known names are exhausted.
_INDEX_LINK_RE = re.compile(r'href="([^"?/]*(?:CHECKSUM|SHA256SUMS?)[^"?/]*)"', re.IGNORECASE)

_GNU_LINE_RE = re.compile(r"^(?P<hash>[0-9a-fA-F]{64})\s+[* ]?(?P<name>.+?)\s*$")
_BSD_LINE_RE = re.compile(
    r"^SHA256\s*\((?P<name>[^)]+)\)\s*=\s*(?P<hash>[0-9a-fA-F]{64})\s*$", re.IGNORECASE
)
_BARE_HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def hash_file(filepath: Path) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest().lower()


def parse_checksums(text: str) -> dict[str, str]:
    """Map filename -> sha256 from GNU (`hash  name`) or BSD (`SHA256 (name) = hash`) lines."""
    checksums: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _BSD_LINE_RE.match(line) or _GNU_LINE_RE.match(line)
        if match:
            checksums[match.group("name").strip()] = match.group("hash").lower()
    return checksums


def _bare_hash(text: str) -> str | None:
    stripped = text.strip()
    return stripped.lower() if _BARE_HASH_RE.match(stripped) else None


def _fetch(session: requests.Session, url: str) -> str | None:
    try:
        response = session.get(url, timeout=10)
    except Exception as exc:
        logger.debug("CHECKSUM_FETCH_ERROR  %s  -  %s", url, exc)
        return None
    if response.status_code != 200:
        return None
    return response.text


def _expected_hash(session: requests.Session, filepath: Path, url: str) -> str | None:
    filename = filepath.name

    for suffix in SIDECAR_SUFFIXES:
        text = _fetch(session, url + suffix)
        if text is None:
            continue
        bare = _bare_hash(text)
        if bare:
            return bare
        checksums = parse_checksums(text)
        if filename in checksums:
            return checksums[filename]
        if len(checksums) == 1:
            return next(iter(checksums.values()))

    directory_url = url.rsplit("/", 1)[0] + "/"
    for name in DIRECTORY_FILENAMES:
        text = _fetch(session, directory_url + name)
        if text is None:
            continue
        checksums = parse_checksums(text)
        if filename in checksums:
            return checksums[filename]

    index = _fetch(session, directory_url)
    if index:
        for name in dict.fromkeys(_INDEX_LINK_RE.findall(index)):
            if name in DIRECTORY_FILENAMES:
                continue
            text = _fetch(session, directory_url + name)
            if text is None:
                continue
            checksums = parse_checksums(text)
            if filename in checksums:
                return checksums[filename]

    return None


def verify_checksum(session: requests.Session, filepath: Path, url: str) -> bool | None:
    """True if the file matches its published hash, False on mismatch, None if no hash was found."""
    expected = _expected_hash(session, filepath, url)
    if expected is None:
        logger.debug("CHECKSUM_NOT_PUBLISHED  %s", url)
        return None
    return hash_file(filepath) == expected
