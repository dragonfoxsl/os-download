"""OpenPGP verification of the checksum files a mirror serves.

A checksum fetched from the same mirror as the ISO proves the download was not truncated,
nothing more: whoever can serve a bad ISO can serve a matching hash. The distributions sign
their checksum files, so the signature is what makes verification mean anything.

Trust comes from one of two places, never from the mirror:

* a pinned signing-key fingerprint, imported by fingerprint from a keyserver, or
* a keyring published over HTTPS by the distribution itself, for keys that rotate per
  release (Fedora issues a new key every release, so pinning one would break each upgrade).

Anything else - no signature published, gpg missing, keys unobtainable - is reported as
UNAVAILABLE and leaves the caller with a hash-only check, unless --require-signature.
"""

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import requests

logger = logging.getLogger("os_download")

KEYRING_DIR = Path.home() / ".local" / "share" / "os-download" / "gnupg"
KEYSERVERS = ("hkps://keyserver.ubuntu.com", "hkps://keys.openpgp.org")

DETACHED_SUFFIXES = (".gpg", ".sign", ".asc", ".sig")
CLEARSIGN_MARKER = "-----BEGIN PGP SIGNED MESSAGE-----"


@dataclass(frozen=True)
class SigningKeys:
    name: str
    # Fingerprints are pinned in-tree and reviewed; a mirror can never introduce a key.
    fingerprints: tuple[str, ...] = ()
    # For distros whose signing key rotates per release, fetched over HTTPS from the
    # distro's own domain rather than from whichever mirror served the ISO.
    keyring_url: str | None = None


# Fingerprints below were read from the signatures the distributions currently publish and
# cross-checked against their documented signing keys. Changing one is a security decision:
# it must be corroborated against the distribution's own published key, not just against
# whatever a mirror happens to serve today.
SIGNING_KEYS: dict[str, SigningKeys] = {
    "ubuntu": SigningKeys(
        "Ubuntu", fingerprints=("843938DF228D22F7B3742BC0D94AA3F0EFE21092",)
    ),
    "debian": SigningKeys(
        "Debian", fingerprints=("DF9B9C49EAA9298432589D76DA87E80D6294BE9B",)
    ),
    "linuxmint": SigningKeys(
        "Linux Mint", fingerprints=("27DEB15644C6B3CF3BD7D291300F846BA25BAE09",)
    ),
    "fedora": SigningKeys("Fedora", keyring_url="https://fedoraproject.org/fedora.gpg"),
}

# Mirrors serve many distros from one host (mirrors.kernel.org/fedora, .../linuxmint), so the
# distro is identified by the whole URL, not the hostname.
_URL_MARKERS = (
    ("linuxmint", "linuxmint"),
    ("/fedora", "fedora"),
    ("fedoraproject", "fedora"),
    ("ubuntu", "ubuntu"),
    ("debian", "debian"),
)


class SignatureStatus(Enum):
    VALID = "valid"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class SignatureResult:
    status: SignatureStatus
    detail: str
    signer: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is SignatureStatus.VALID


def keys_for_url(url: str) -> SigningKeys | None:
    lowered = url.lower()
    for marker, distro in _URL_MARKERS:
        if marker in lowered:
            return SIGNING_KEYS.get(distro)
    return None


def _gpg(*args: str, keyring_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "gpg",
            "--homedir",
            str(keyring_dir),
            "--batch",
            "--no-tty",
            "--status-fd",
            "1",
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )


def _ensure_keyring(keys: SigningKeys, session: requests.Session, keyring_dir: Path) -> bool:
    keyring_dir.mkdir(parents=True, exist_ok=True)
    keyring_dir.chmod(0o700)

    if keys.keyring_url:
        try:
            response = session.get(keys.keyring_url, timeout=30)
            response.raise_for_status()
        except Exception as exc:
            logger.warning("KEYRING FETCH FAILED  %s  -  %s", keys.keyring_url, exc)
            return False
        with tempfile.NamedTemporaryFile(suffix=".gpg") as handle:
            handle.write(response.content)
            handle.flush()
            result = _gpg("--import", handle.name, keyring_dir=keyring_dir)
        if result.returncode != 0:
            logger.warning("KEYRING IMPORT FAILED  %s  -  %s", keys.name, result.stderr.strip())
            return False
        return True

    imported = False
    for fingerprint in keys.fingerprints:
        if _has_key(fingerprint, keyring_dir):
            imported = True
            continue
        for keyserver in KEYSERVERS:
            result = _gpg(
                "--keyserver", keyserver, "--recv-keys", fingerprint, keyring_dir=keyring_dir
            )
            if result.returncode == 0 and _has_key(fingerprint, keyring_dir):
                imported = True
                break
            logger.debug(
                "RECV_KEYS FAILED  %s  from %s  -  %s",
                fingerprint,
                keyserver,
                result.stderr.strip(),
            )
    return imported


def _has_key(fingerprint: str, keyring_dir: Path) -> bool:
    result = _gpg("--list-keys", fingerprint, keyring_dir=keyring_dir)
    return result.returncode == 0


def _valid_signer(status_output: str) -> str | None:
    """Return the signing key's fingerprint from gpg's machine-readable status output."""
    for line in status_output.splitlines():
        if line.startswith("[GNUPG:] VALIDSIG "):
            parts = line.split()
            if len(parts) > 2:
                return parts[2].upper()
    return None


def _find_detached_signature(session: requests.Session, checksum_url: str) -> bytes | None:
    for suffix in DETACHED_SUFFIXES:
        try:
            response = session.get(checksum_url + suffix, timeout=15)
        except Exception as exc:
            logger.debug("SIG FETCH ERROR  %s%s  -  %s", checksum_url, suffix, exc)
            continue
        if response.status_code == 200 and response.content:
            logger.debug("SIG FOUND  %s%s", checksum_url, suffix)
            return response.content
    return None


def verify_checksum_file(
    session: requests.Session,
    checksum_url: str,
    checksum_text: str,
    keyring_dir: Path = KEYRING_DIR,
) -> SignatureResult:
    """Verify the signature over the checksum file that a hash was read from."""
    keys = keys_for_url(checksum_url)
    if keys is None:
        return SignatureResult(
            SignatureStatus.UNAVAILABLE, "no signing key is pinned for this distribution"
        )

    if shutil.which("gpg") is None:
        return SignatureResult(SignatureStatus.UNAVAILABLE, "gpg is not installed")

    clearsigned = CLEARSIGN_MARKER in checksum_text
    detached = None if clearsigned else _find_detached_signature(session, checksum_url)
    if not clearsigned and detached is None:
        return SignatureResult(
            SignatureStatus.UNAVAILABLE, "the mirror publishes no signature for the checksum file"
        )

    if not _ensure_keyring(keys, session, keyring_dir):
        return SignatureResult(
            SignatureStatus.UNAVAILABLE, f"could not obtain {keys.name} signing keys"
        )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        if clearsigned:
            signed = tmp_path / "checksums.asc"
            signed.write_text(checksum_text, encoding="utf-8")
            result = _gpg("--verify", str(signed), keyring_dir=keyring_dir)
        else:
            data = tmp_path / "checksums"
            signature = tmp_path / "checksums.sig"
            data.write_text(checksum_text, encoding="utf-8")
            signature.write_bytes(detached or b"")
            result = _gpg("--verify", str(signature), str(data), keyring_dir=keyring_dir)

    signer = _valid_signer(result.stdout)
    if result.returncode != 0 or signer is None:
        return SignatureResult(
            SignatureStatus.INVALID,
            "the signature on the checksum file is not valid",
            signer,
        )

    if keys.fingerprints and signer not in {f.upper() for f in keys.fingerprints}:
        # A good signature from the wrong key is exactly what a substituted key looks like.
        return SignatureResult(
            SignatureStatus.INVALID,
            f"signed by {signer}, which is not a pinned {keys.name} signing key",
            signer,
        )

    return SignatureResult(SignatureStatus.VALID, f"signed by {keys.name} key {signer}", signer)
