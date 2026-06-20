from pathlib import Path

from os_download.downloader.checksums import verify_checksum


class FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.urls = []

    def get(self, url, timeout=None):
        self.urls.append(url)
        return self.responses.get(url, FakeResponse(404))


def test_verify_checksum_matches_sidecar(tmp_path: Path):
    file_path = tmp_path / "image.iso.gz"
    file_path.write_bytes(b"archive")
    session = FakeSession(
        {
            "https://example.test/image.iso.gz.sha256": FakeResponse(
                200,
                "0eb3e36bfb24dcd9bb1d1bece1531216b59539a8fde17ee80224af0653c92aa3  image.iso.gz",
            )
        }
    )

    assert verify_checksum(session, file_path, "https://example.test/image.iso.gz") is True


def test_verify_checksum_matches_sha256sums(tmp_path: Path):
    file_path = tmp_path / "ubuntu.iso"
    file_path.write_bytes(b"ubuntu")
    session = FakeSession(
        {
            "https://example.test/ubuntu.iso.sha256": FakeResponse(404),
            "https://example.test/SHA256SUMS": FakeResponse(
                200,
                "7804a56a5c7636cc05814736f44139e32920810d3bd51aa099a5df932e754ce9 *ubuntu.iso\n",
            ),
        }
    )

    assert verify_checksum(session, file_path, "https://example.test/ubuntu.iso") is True


def test_verify_checksum_returns_none_when_no_checksum_exists(tmp_path: Path):
    file_path = tmp_path / "unknown.iso"
    file_path.write_bytes(b"data")
    session = FakeSession({})

    assert verify_checksum(session, file_path, "https://example.test/unknown.iso") is None
