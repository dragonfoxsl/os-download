import bz2
import gzip
from pathlib import Path

import pytest

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


def test_failed_decompression_preserves_existing_output_and_archive(tmp_path: Path):
    archive = tmp_path / "sample.iso.gz"
    archive.write_bytes(gzip.compress(b"replacement")[:-4])
    output = tmp_path / "sample.iso"
    output.write_bytes(b"known-good")

    with pytest.raises(EOFError):
        decompress_file(archive)

    assert output.read_bytes() == b"known-good"
    assert archive.exists()
    assert not list(tmp_path.glob(".sample.iso.*.part"))


def test_decompression_does_not_touch_a_preexisting_part_file(tmp_path: Path):
    archive = tmp_path / "sample.iso.gz"
    archive.write_bytes(gzip.compress(b"replacement"))
    unrelated = tmp_path / "sample.iso.part"
    unrelated.write_bytes(b"leave-me-alone")

    output = decompress_file(archive)

    assert output.read_bytes() == b"replacement"
    assert unrelated.read_bytes() == b"leave-me-alone"
    assert not list(tmp_path.glob(".sample.iso.*.part"))
