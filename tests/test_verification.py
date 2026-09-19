import os
from pathlib import Path

from os_download.downloader import verification
from os_download.downloader.checksums import ChecksumSource
from os_download.downloader.signatures import SignatureResult, SignatureStatus
from os_download.downloader.verification import VerifyStatus, marker_path, verify_download

URL = "https://example.test/image.iso"


def stub_network(monkeypatch, payload: bytes, signature: SignatureStatus) -> list[str]:
    """Publish a correct hash for payload, signed (or not) as requested."""
    import hashlib

    hashed = []
    digest = hashlib.sha256(payload).hexdigest()

    def fake_resolve(session, filepath, url, **kwargs):
        hashed.append(filepath.name)
        return ChecksumSource(digest, URL + ".sha256", f"{digest}  {filepath.name}\n")

    monkeypatch.setattr(verification, "resolve_checksum", fake_resolve)
    monkeypatch.setattr(
        verification,
        "verify_checksum_file",
        lambda session, url, text: SignatureResult(signature, "stubbed"),
    )
    return hashed


def test_verified_file_is_not_rehashed_on_the_next_run(tmp_path: Path, monkeypatch):
    iso = tmp_path / "image.iso"
    iso.write_bytes(b"payload")
    resolved = stub_network(monkeypatch, b"payload", SignatureStatus.VALID)

    first = verify_download(None, iso, URL)
    assert first.status is VerifyStatus.VERIFIED
    assert marker_path(iso).exists()

    # Re-hashing a multi-GB ISO on every run costs minutes and proves nothing new.
    second = verify_download(None, iso, URL)
    assert second.status is VerifyStatus.CACHED
    assert resolved == ["image.iso"]


def test_verified_cache_is_bound_to_the_source_url(tmp_path: Path, monkeypatch):
    iso = tmp_path / "image.iso"
    iso.write_bytes(b"payload")
    resolved = stub_network(monkeypatch, b"payload", SignatureStatus.VALID)

    assert verify_download(None, iso, URL).status is VerifyStatus.VERIFIED
    assert verify_download(None, iso, URL + "?mirror=other").status is VerifyStatus.VERIFIED
    assert resolved == ["image.iso", "image.iso"]


def test_redirecting_mirror_changes_do_not_invalidate_the_requested_source(tmp_path: Path, monkeypatch):
    iso = tmp_path / "image.iso"
    iso.write_bytes(b"payload")
    resolved = stub_network(monkeypatch, b"payload", SignatureStatus.VALID)
    mirrors = iter(("https://mirror-one.test/image.iso", "https://mirror-two.test/image.iso"))
    monkeypatch.setattr(verification, "effective_url", lambda session, url: next(mirrors))

    assert verify_download(None, iso, URL).status is VerifyStatus.VERIFIED
    assert verify_download(None, iso, URL).status is VerifyStatus.CACHED
    assert resolved == ["image.iso"]


def test_cache_is_invalidated_when_the_file_changes(tmp_path: Path, monkeypatch):
    iso = tmp_path / "image.iso"
    iso.write_bytes(b"payload")
    stub_network(monkeypatch, b"payload", SignatureStatus.VALID)

    assert verify_download(None, iso, URL).status is VerifyStatus.VERIFIED

    iso.write_bytes(b"tampered")
    os.utime(iso, (0, 0))

    assert verify_download(None, iso, URL).status is VerifyStatus.HASH_MISMATCH


def test_an_unsigned_checksum_verifies_the_hash_but_is_not_trusted(tmp_path: Path, monkeypatch):
    iso = tmp_path / "image.iso"
    iso.write_bytes(b"payload")
    stub_network(monkeypatch, b"payload", SignatureStatus.UNAVAILABLE)

    report = verify_download(None, iso, URL)

    assert report.status is VerifyStatus.HASH_ONLY
    assert not report.trusted
    assert not report.corrupt

    # An unsigned result must not become trusted merely because it was cached.
    second = verify_download(None, iso, URL)
    assert second.status is VerifyStatus.HASH_ONLY
    assert not second.trusted


def test_an_invalid_signature_is_fatal_even_when_the_hash_matches(tmp_path: Path, monkeypatch):
    iso = tmp_path / "image.iso"
    iso.write_bytes(b"payload")
    stub_network(monkeypatch, b"payload", SignatureStatus.INVALID)

    report = verify_download(None, iso, URL)

    assert report.status is VerifyStatus.SIGNATURE_INVALID
    assert report.corrupt


def test_marker_write_replaces_a_symlink_without_following_it(tmp_path: Path):
    iso = tmp_path / "image.iso"
    iso.write_bytes(b"payload")
    target = tmp_path / "sensitive.txt"
    target.write_text("keep", encoding="utf-8")
    marker = marker_path(iso)
    marker.symlink_to(target)

    verification.write_marker(iso, "abc123", trusted=True, source_url=URL)

    assert target.read_text(encoding="utf-8") == "keep"
    assert marker.is_file()
    assert not marker.is_symlink()
