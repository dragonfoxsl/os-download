import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import requests

logger = logging.getLogger("os_download")


@dataclass(frozen=True)
class ChecksumSource:
    """The published hash for a file, and the exact document it was read from.

    The document and its URL are kept so the signature over it can be verified; a hash on
    its own says nothing about who published it.
    """

    expected: str
    url: str
    text: str

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


def _effective_url(session: requests.Session, url: str) -> str:
    """Follow redirects once, so sibling files are looked for next to the real ISO.

    Redirectors like download.fedoraproject.org hand out a different mirror per request, so
    resolving siblings against the redirector can search a mirror that never held the ISO.
    """
    try:
        response = session.head(url, timeout=15, allow_redirects=True)
    except Exception as exc:
        logger.debug("EFFECTIVE_URL_FAILED  %s  -  %s", url, exc)
        return url
    resolved = getattr(response, "url", None)
    if not resolved or not isinstance(resolved, str):
        return url
    if resolved != url:
        logger.debug("EFFECTIVE_URL  %s  ->  %s", url, resolved)
    return resolved


def resolve_checksum(
    session: requests.Session, filepath: Path, url: str
) -> ChecksumSource | None:
    """Find the published hash for a download, and the document it came from."""
    filename = filepath.name
    url = _effective_url(session, url)

    for suffix in SIDECAR_SUFFIXES:
        sidecar_url = url + suffix
        text = _fetch(session, sidecar_url)
        if text is None:
            continue
        bare = _bare_hash(text)
        if bare:
            return ChecksumSource(bare, sidecar_url, text)
        checksums = parse_checksums(text)
        if filename in checksums:
            return ChecksumSource(checksums[filename], sidecar_url, text)
        if len(checksums) == 1:
            return ChecksumSource(next(iter(checksums.values())), sidecar_url, text)

    directory_url = url.rsplit("/", 1)[0] + "/"
    for name in DIRECTORY_FILENAMES:
        checksum_url = directory_url + name
        text = _fetch(session, checksum_url)
        if text is None:
            continue
        checksums = parse_checksums(text)
        if filename in checksums:
            return ChecksumSource(checksums[filename], checksum_url, text)

    index = _fetch(session, directory_url)
    if index:
        for name in dict.fromkeys(_INDEX_LINK_RE.findall(index)):
            if name in DIRECTORY_FILENAMES:
                continue
            checksum_url = directory_url + name
            text = _fetch(session, checksum_url)
            if text is None:
                continue
            checksums = parse_checksums(text)
            if filename in checksums:
                return ChecksumSource(checksums[filename], checksum_url, text)

    logger.debug("CHECKSUM_NOT_PUBLISHED  %s", url)
    return None


def verify_checksum(session: requests.Session, filepath: Path, url: str) -> bool | None:
    """True if the file matches its published hash, False on mismatch, None if no hash was found."""
    source = resolve_checksum(session, filepath, url)
    if source is None:
        return None
    return hash_file(filepath) == source.expected
