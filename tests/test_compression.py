import bz2
import gzip
from pathlib import Path

from os_download.downloader.compression import decompress_file


def test_decompress_file_extracts_gz_and_removes_archive(tmp_path: Path):
    archive = tmp_path / "sample.iso.gz"
    archive.write_bytes(gzip.compress(b"iso-bytes"))

    output = decompress_file(archive)

    assert output == tmp_path / "sample.iso"
    assert output.read_bytes() == b"iso-bytes"
    assert not archive.exists()


def test_decompress_file_extracts_bz2_and_removes_archive(tmp_path: Path):
    archive = tmp_path / "sample.iso.bz2"
    archive.write_bytes(bz2.compress(b"iso-bytes"))

    output = decompress_file(archive)

    assert output == tmp_path / "sample.iso"
    assert output.read_bytes() == b"iso-bytes"
    assert not archive.exists()
