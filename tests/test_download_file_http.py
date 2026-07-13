"""End-to-end coverage for download_file against a real HTTP server.

Resume, the 416 "already complete" path and the 403 curl fallback are the parts of the
downloader most likely to break, and they only exercise real HTTP semantics.
"""

import hashlib
import shutil
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from os_download.downloader.manager import DownloadManager
from os_download.downloader.verification import VerifyReport, VerifyStatus

PAYLOAD = bytes(range(256)) * 64  # 16 KiB, deterministic
SHA256SUMS = f"{hashlib.sha256(PAYLOAD).hexdigest()}  file.iso\n"


class RangeHandler(BaseHTTPRequestHandler):
    """Serves PAYLOAD at /file.iso with Range support, and 403s /forbidden.iso.

    Deliberately reproduces nginx's behaviour of ignoring Range whenever a content-coding is
    negotiated, which is what silently defeats resume if the client sends the default
    Accept-Encoding of "gzip, deflate".
    """

    served = 0  # bytes of PAYLOAD written, so a test can tell a resume from a refetch

    def log_message(self, *args):
        return

    def _write(self, body: bytes) -> None:
        RangeHandler.served += len(body)
        self.wfile.write(body)

    def _ignores_range(self) -> bool:
        encoding = self.headers.get("Accept-Encoding", "")
        return "gzip" in encoding or "deflate" in encoding

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        # Mirrors the real case the curl fallback exists for: the mirror rejects the
        # library's request but serves the same file happily to curl.
        if self.path == "/forbidden.iso":
            if "curl" not in self.headers.get("User-Agent", "").lower():
                self.send_response(403)
                self.send_header("content-length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("content-length", str(len(PAYLOAD)))
            self.end_headers()
            self.wfile.write(PAYLOAD)
            return

        if self.path == "/SHA256SUMS":
            body = SHA256SUMS.encode()
            self.send_response(200)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path != "/file.iso":
            self.send_response(404)
            self.send_header("content-length", "0")
            self.end_headers()
            return

        range_header = self.headers.get("Range")
        if not range_header or self._ignores_range():
            self.send_response(200)
            self.send_header("content-length", str(len(PAYLOAD)))
            self.end_headers()
            self._write(PAYLOAD)
            return

        start = int(range_header.split("=")[1].split("-")[0])
        if start >= len(PAYLOAD):
            self.send_response(416)
            self.send_header("content-range", f"bytes */{len(PAYLOAD)}")
            self.send_header("content-length", "0")
            self.end_headers()
            return

        body = PAYLOAD[start:]
        self.send_response(206)
        self.send_header("content-length", str(len(body)))
        self.send_header("content-range", f"bytes {start}-{len(PAYLOAD) - 1}/{len(PAYLOAD)}")
        self.end_headers()
        self._write(body)

    def do_HEAD(self):  # noqa: N802 - BaseHTTPRequestHandler API
        self.send_response(200 if self.path in ("/file.iso", "/forbidden.iso") else 404)
        self.send_header("content-length", str(len(PAYLOAD)))
        self.end_headers()


@pytest.fixture
def server():
    RangeHandler.served = 0
    httpd = HTTPServer(("127.0.0.1", 0), RangeHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()


def test_download_file_fetches_a_whole_file(tmp_path: Path, server: str):
    manager = DownloadManager(download_dir=str(tmp_path), backend="python")

    assert manager.download_file(f"{server}/file.iso", decompress=False)
    assert (tmp_path / "file.iso").read_bytes() == PAYLOAD


def test_download_file_resumes_a_partial_file_without_refetching_it(tmp_path: Path, server: str):
    manager = DownloadManager(download_dir=str(tmp_path), backend="python")
    partial = tmp_path / "file.iso"
    partial.write_bytes(PAYLOAD[:4096])

    assert manager.download_file(f"{server}/file.iso", resume=True, decompress=False)
    assert partial.read_bytes() == PAYLOAD

    # Only the missing bytes crossed the wire. requests' default Accept-Encoding of
    # "gzip, deflate" makes nginx ignore Range and serve the whole file, which turns every
    # resume into a silent full re-download; this is what catches that regression.
    assert RangeHandler.served == len(PAYLOAD) - 4096


def test_the_session_does_not_negotiate_a_content_coding(tmp_path: Path, server: str):
    manager = DownloadManager(download_dir=str(tmp_path), backend="python")

    assert manager.session.headers["Accept-Encoding"] == "identity"


def test_download_file_restarts_from_scratch_when_resume_is_disabled(tmp_path: Path, server: str):
    manager = DownloadManager(download_dir=str(tmp_path), backend="python")
    stale = tmp_path / "file.iso"
    stale.write_bytes(b"stale bytes that must not survive")

    assert manager.download_file(f"{server}/file.iso", resume=False, decompress=False)
    assert stale.read_bytes() == PAYLOAD


def test_download_file_treats_a_416_on_a_complete_file_as_success(tmp_path: Path, server: str):
    manager = DownloadManager(download_dir=str(tmp_path), backend="python")
    complete = tmp_path / "file.iso"
    complete.write_bytes(PAYLOAD)

    assert manager.download_file(f"{server}/file.iso", resume=True, decompress=False)
    assert complete.read_bytes() == PAYLOAD


def test_download_file_quarantines_a_file_that_fails_verification(
    tmp_path: Path, server: str, monkeypatch
):
    manager = DownloadManager(download_dir=str(tmp_path), backend="python")
    monkeypatch.setattr(
        "os_download.downloader.manager.verify_download",
        lambda session, filepath, url, use_cache=True: VerifyReport(
            VerifyStatus.HASH_MISMATCH, "stubbed"
        ),
    )

    assert not manager.download_file(f"{server}/file.iso", verify=True, decompress=False)
    assert not (tmp_path / "file.iso").exists()
    assert (tmp_path / "file.iso.corrupt").exists()


def test_download_file_verifies_against_a_checksum_the_server_publishes(
    tmp_path: Path, server: str
):
    manager = DownloadManager(download_dir=str(tmp_path), backend="python")

    # The server publishes SHA256SUMS covering file.iso, so this exercises the real
    # resolve-then-hash path end to end; nothing signs it, so it lands as hash-only.
    assert manager.download_file(f"{server}/file.iso", verify=True, decompress=False)
    assert (tmp_path / "file.iso").read_bytes() == PAYLOAD


def test_download_file_rejects_an_unsigned_checksum_under_require_signature(
    tmp_path: Path, server: str
):
    manager = DownloadManager(download_dir=str(tmp_path), require_signature=True, backend="python")

    assert not manager.download_file(f"{server}/file.iso", verify=True, decompress=False)


@pytest.mark.skipif(shutil.which("curl") is None, reason="curl is not installed")
def test_download_file_falls_back_to_curl_on_403(tmp_path: Path, server: str):
    manager = DownloadManager(download_dir=str(tmp_path), backend="python")

    assert manager.download_file(f"{server}/forbidden.iso", decompress=False)
    assert (tmp_path / "forbidden.iso").read_bytes() == PAYLOAD


@pytest.mark.skipif(shutil.which("aria2c") is None, reason="aria2c is not installed")
def test_aria2_backend_downloads_the_whole_file(tmp_path: Path, server: str):
    manager = DownloadManager(download_dir=str(tmp_path), backend="aria2", connections=4)

    assert manager.download_file(f"{server}/file.iso", verify=False, decompress=False)
    assert (tmp_path / "file.iso").read_bytes() == PAYLOAD


@pytest.mark.skipif(shutil.which("aria2c") is None, reason="aria2c is not installed")
def test_aria2_backend_resumes_a_partial_download(tmp_path: Path, server: str):
    manager = DownloadManager(download_dir=str(tmp_path), backend="aria2", connections=4)
    (tmp_path / "file.iso").write_bytes(PAYLOAD[:4096])

    assert manager.download_file(f"{server}/file.iso", verify=False, decompress=False)
    assert (tmp_path / "file.iso").read_bytes() == PAYLOAD
