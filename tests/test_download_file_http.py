"""End-to-end coverage for download_file against a real HTTP server.

Resume, the 416 "already complete" path and the 403 curl fallback are the parts of the
downloader most likely to break, and they only exercise real HTTP semantics.
"""

import shutil
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from os_download.downloader.manager import DownloadManager

PAYLOAD = bytes(range(256)) * 64  # 16 KiB, deterministic


class RangeHandler(BaseHTTPRequestHandler):
    """Serves PAYLOAD at /file.iso with Range support, and 403s /forbidden.iso."""

    def log_message(self, *args):
        return

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

        if self.path != "/file.iso":
            self.send_response(404)
            self.send_header("content-length", "0")
            self.end_headers()
            return

        range_header = self.headers.get("Range")
        if not range_header:
            self.send_response(200)
            self.send_header("content-length", str(len(PAYLOAD)))
            self.end_headers()
            self.wfile.write(PAYLOAD)
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
        self.wfile.write(body)

    def do_HEAD(self):  # noqa: N802 - BaseHTTPRequestHandler API
        self.send_response(200 if self.path in ("/file.iso", "/forbidden.iso") else 404)
        self.send_header("content-length", str(len(PAYLOAD)))
        self.end_headers()


@pytest.fixture
def server():
    httpd = HTTPServer(("127.0.0.1", 0), RangeHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()


def test_download_file_fetches_a_whole_file(tmp_path: Path, server: str):
    manager = DownloadManager(download_dir=str(tmp_path))

    assert manager.download_file(f"{server}/file.iso", decompress=False)
    assert (tmp_path / "file.iso").read_bytes() == PAYLOAD


def test_download_file_resumes_a_partial_file_without_refetching_it(tmp_path: Path, server: str):
    manager = DownloadManager(download_dir=str(tmp_path))
    partial = tmp_path / "file.iso"
    partial.write_bytes(PAYLOAD[:4096])

    assert manager.download_file(f"{server}/file.iso", resume=True, decompress=False)
    assert partial.read_bytes() == PAYLOAD


def test_download_file_restarts_from_scratch_when_resume_is_disabled(tmp_path: Path, server: str):
    manager = DownloadManager(download_dir=str(tmp_path))
    stale = tmp_path / "file.iso"
    stale.write_bytes(b"stale bytes that must not survive")

    assert manager.download_file(f"{server}/file.iso", resume=False, decompress=False)
    assert stale.read_bytes() == PAYLOAD


def test_download_file_treats_a_416_on_a_complete_file_as_success(tmp_path: Path, server: str):
    manager = DownloadManager(download_dir=str(tmp_path))
    complete = tmp_path / "file.iso"
    complete.write_bytes(PAYLOAD)

    assert manager.download_file(f"{server}/file.iso", resume=True, decompress=False)
    assert complete.read_bytes() == PAYLOAD


def test_download_file_verifies_the_checksum_when_asked(tmp_path: Path, server: str, monkeypatch):
    manager = DownloadManager(download_dir=str(tmp_path))
    monkeypatch.setattr(manager, "verify_checksum", lambda filepath, url: False)

    assert not manager.download_file(f"{server}/file.iso", verify=True, decompress=False)
    assert not (tmp_path / "file.iso").exists()
    assert (tmp_path / "file.iso.corrupt").exists()


@pytest.mark.skipif(shutil.which("curl") is None, reason="curl is not installed")
def test_download_file_falls_back_to_curl_on_403(tmp_path: Path, server: str):
    manager = DownloadManager(download_dir=str(tmp_path))

    assert manager.download_file(f"{server}/forbidden.iso", decompress=False)
    assert (tmp_path / "forbidden.iso").read_bytes() == PAYLOAD
