from pathlib import Path

from os_download.downloader.checksums import hash_file, verify_checksum


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


def test_verify_checksum_reads_fedora_style_bsd_checksum_named_after_the_release(tmp_path: Path):
    file_path = tmp_path / "Fedora-Workstation-42-x86_64.iso"
    file_path.write_bytes(b"fedora")
    digest = hash_file(file_path)
    session = FakeSession(
        {
            "https://example.test/iso/": FakeResponse(
                200, '<a href="Fedora-Workstation-42-1.1-x86_64-CHECKSUM">CHECKSUM</a>'
            ),
            "https://example.test/iso/Fedora-Workstation-42-1.1-x86_64-CHECKSUM": FakeResponse(
                200,
                "# Fedora-Workstation-42-x86_64.iso: 2147483648 bytes\n"
                f"SHA256 (Fedora-Workstation-42-x86_64.iso) = {digest}\n",
            ),
        }
    )

    url = "https://example.test/iso/Fedora-Workstation-42-x86_64.iso"
    assert verify_checksum(session, file_path, url) is True


def test_verify_checksum_reads_linux_mint_style_sha256sum_txt(tmp_path: Path):
    file_path = tmp_path / "linuxmint-22-cinnamon-64bit.iso"
    file_path.write_bytes(b"mint")
    digest = hash_file(file_path)
    session = FakeSession(
        {
            "https://example.test/sha256sum.txt": FakeResponse(
                200, f"{digest} *linuxmint-22-cinnamon-64bit.iso\n"
            )
        }
    )

    url = "https://example.test/linuxmint-22-cinnamon-64bit.iso"
    assert verify_checksum(session, file_path, url) is True


def test_verify_checksum_reads_a_sidecar_containing_only_a_bare_hash(tmp_path: Path):
    file_path = tmp_path / "openSUSE-Tumbleweed.iso"
    file_path.write_bytes(b"tumbleweed")
    digest = hash_file(file_path)
    session = FakeSession(
        {"https://example.test/openSUSE-Tumbleweed.iso.sha256": FakeResponse(200, f"{digest}\n")}
    )

    url = "https://example.test/openSUSE-Tumbleweed.iso"
    assert verify_checksum(session, file_path, url) is True


def test_verify_checksum_detects_a_mismatch(tmp_path: Path):
    file_path = tmp_path / "arch.iso"
    file_path.write_bytes(b"tampered")
    session = FakeSession(
        {
            "https://example.test/sha256sums.txt": FakeResponse(
                200, f"{'0' * 64}  arch.iso\n"
            )
        }
    )

    assert verify_checksum(session, file_path, "https://example.test/arch.iso") is False
