from pathlib import Path

from os_download.downloader import signatures
from os_download.downloader.signatures import (
    SignatureStatus,
    SigningKeys,
    keys_for_url,
    verify_checksum_file,
)

UBUNTU_FPR = "843938DF228D22F7B3742BC0D94AA3F0EFE21092"


def test_distro_is_identified_from_the_whole_url_not_the_host():
    # One mirror host serves many distros, so the hostname alone cannot identify one.
    assert keys_for_url("https://mirrors.edge.kernel.org/linuxmint/stable/22/x.iso").name == (
        "Linux Mint"
    )
    assert keys_for_url("https://mirrors.kernel.org/fedora/releases/44/x.iso").name == "Fedora"
    assert keys_for_url("https://releases.ubuntu.com/24.04/SHA256SUMS").name == "Ubuntu"


def test_a_distro_with_no_pinned_key_is_reported_as_unavailable_not_valid():
    result = verify_checksum_file(None, "https://example.test/unknown-distro/SHA256SUMS", "text")

    assert result.status is SignatureStatus.UNAVAILABLE
    assert not result.ok


def test_a_good_signature_from_an_unpinned_key_is_rejected(tmp_path: Path, monkeypatch):
    """A valid signature by the wrong key is what a substituted signing key looks like."""
    monkeypatch.setattr(signatures.shutil, "which", lambda name: "/usr/bin/gpg")
    monkeypatch.setattr(
        signatures,
        "SIGNING_KEYS",
        {"ubuntu": SigningKeys("Ubuntu", fingerprints=(UBUNTU_FPR,))},
    )
    monkeypatch.setattr(signatures, "_find_detached_signature", lambda session, url: b"sig")
    monkeypatch.setattr(signatures, "_ensure_keyring", lambda keys, session, keyring_dir: True)

    attacker_fpr = "1111111111111111111111111111111111111111"

    class GoodSignatureFromWrongKey:
        returncode = 0
        stdout = f"[GNUPG:] GOODSIG x\n[GNUPG:] VALIDSIG {attacker_fpr} 2026-01-01\n"
        stderr = ""

    monkeypatch.setattr(signatures, "_gpg", lambda *a, **kw: GoodSignatureFromWrongKey())

    result = verify_checksum_file(
        None, "https://releases.ubuntu.com/24.04/SHA256SUMS", "text", keyring_dir=tmp_path
    )

    assert result.status is SignatureStatus.INVALID
    assert result.signer == attacker_fpr
    assert "not a pinned" in result.detail


def test_a_signature_from_the_pinned_key_is_accepted(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(signatures.shutil, "which", lambda name: "/usr/bin/gpg")
    monkeypatch.setattr(
        signatures,
        "SIGNING_KEYS",
        {"ubuntu": SigningKeys("Ubuntu", fingerprints=(UBUNTU_FPR,))},
    )
    monkeypatch.setattr(signatures, "_find_detached_signature", lambda session, url: b"sig")
    monkeypatch.setattr(signatures, "_ensure_keyring", lambda keys, session, keyring_dir: True)

    class GoodSignature:
        returncode = 0
        stdout = f"[GNUPG:] GOODSIG x\n[GNUPG:] VALIDSIG {UBUNTU_FPR} 2026-01-01\n"
        stderr = ""

    monkeypatch.setattr(signatures, "_gpg", lambda *a, **kw: GoodSignature())

    result = verify_checksum_file(
        None, "https://releases.ubuntu.com/24.04/SHA256SUMS", "text", keyring_dir=tmp_path
    )

    assert result.status is SignatureStatus.VALID
    assert result.ok
