import gzip
from pathlib import Path

from os_download.downloader.manager import DownloadManager


def test_post_download_verifies_archive_before_decompressing(tmp_path: Path, monkeypatch):
    manager = DownloadManager(download_dir=str(tmp_path))
    archive = tmp_path / "image.iso.gz"
    archive.write_bytes(gzip.compress(b"iso"))
    calls = []

    def fake_verify(filepath: Path, url: str):
        calls.append(("verify", filepath.name, archive.exists()))
        return True

    monkeypatch.setattr(manager, "verify_checksum", fake_verify)

    assert manager._post_download(
        archive,
        "https://example.test/image.iso.gz",
        verify=True,
        decompress=True,
        own_progress=False,
    )

    assert calls == [("verify", "image.iso.gz", True)]
    assert (tmp_path / "image.iso").exists()
