"""Decide whether a downloaded file is trustworthy: signature, then hash, then cache.

Order matters. The hash is only meaningful once the document it came from is known to have
been signed by the distribution, so the signature is checked first and a bad one is fatal
regardless of whether the bytes happen to match.
"""

import json
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import requests

from os_download.downloader.checksums import hash_file, resolve_checksum
from os_download.downloader.signatures import (
    SignatureStatus,
    verify_checksum_file,
)

logger = logging.getLogger("os_download")

MARKER_SUFFIX = ".verified"


class VerifyStatus(Enum):
    VERIFIED = "verified"  # signed by a pinned key, and the hash matches
    HASH_ONLY = "hash-only"  # hash matches, but nothing signed it
    CACHED = "cached"  # unchanged since it last verified
    NO_CHECKSUM = "no-checksum"  # the mirror publishes no hash at all
    HASH_MISMATCH = "hash-mismatch"
    SIGNATURE_INVALID = "signature-invalid"


@dataclass(frozen=True)
class VerifyReport:
    status: VerifyStatus
    detail: str

    @property
    def corrupt(self) -> bool:
        """The file is provably wrong: it must not be kept or resumed."""
        return self.status in (VerifyStatus.HASH_MISMATCH, VerifyStatus.SIGNATURE_INVALID)

    @property
    def trusted(self) -> bool:
        """Verified against a signature chain, not merely against the mirror's own hash."""
        return self.status in (VerifyStatus.VERIFIED, VerifyStatus.CACHED)


def marker_path(filepath: Path) -> Path:
    return filepath.with_name(filepath.name + MARKER_SUFFIX)


def _fingerprint(filepath: Path) -> dict[str, int]:
    stat = filepath.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def read_marker(filepath: Path) -> dict | None:
    """A record of a previous successful verification, if the file is untouched since."""
    marker = marker_path(filepath)
    if not marker.exists():
        return None
    try:
        record = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    current = _fingerprint(filepath)
    if record.get("size") != current["size"] or record.get("mtime_ns") != current["mtime_ns"]:
        return None
    return record


def write_marker(filepath: Path, digest: str, trusted: bool) -> None:
    record = {**_fingerprint(filepath), "sha256": digest, "trusted": trusted}
    try:
        marker_path(filepath).write_text(json.dumps(record), encoding="utf-8")
    except OSError as exc:
        logger.debug("MARKER WRITE FAILED  %s  -  %s", filepath.name, exc)


def clear_marker(filepath: Path) -> None:
    try:
        marker_path(filepath).unlink(missing_ok=True)
    except OSError:
        pass


def verify_download(
    session: requests.Session,
    filepath: Path,
    url: str,
    use_cache: bool = True,
) -> VerifyReport:
    if use_cache:
        cached = read_marker(filepath)
        if cached is not None:
            # Re-hashing several GB on every run costs minutes and proves nothing new.
            logger.info("VERIFY CACHED  %s", filepath.name)
            return VerifyReport(
                VerifyStatus.CACHED,
                "already verified and unchanged since"
                + ("" if cached.get("trusted") else " (hash only, unsigned)"),
            )

    source = resolve_checksum(session, filepath, url)
    if source is None:
        return VerifyReport(VerifyStatus.NO_CHECKSUM, "the mirror publishes no checksum")

    signature = verify_checksum_file(session, source.url, source.text)
    if signature.status is SignatureStatus.INVALID:
        logger.error("SIGNATURE FAIL  %s  -  %s", filepath.name, signature.detail)
        return VerifyReport(VerifyStatus.SIGNATURE_INVALID, signature.detail)

    digest = hash_file(filepath)
    if digest != source.expected:
        return VerifyReport(
            VerifyStatus.HASH_MISMATCH,
            f"expected {source.expected[:16]}…, got {digest[:16]}…",
        )

    trusted = signature.status is SignatureStatus.VALID
    write_marker(filepath, digest, trusted)

    if trusted:
        logger.info("VERIFY OK  %s  -  %s", filepath.name, signature.detail)
        return VerifyReport(VerifyStatus.VERIFIED, signature.detail)

    logger.warning("VERIFY HASH-ONLY  %s  -  %s", filepath.name, signature.detail)
    return VerifyReport(VerifyStatus.HASH_ONLY, signature.detail)
