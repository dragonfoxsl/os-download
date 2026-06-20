import gzip
import threading
import time
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


def test_download_file_treats_416_resume_as_complete_when_local_size_matches_server(
    tmp_path: Path, monkeypatch
):
    manager = DownloadManager(download_dir=str(tmp_path))
    filepath = tmp_path / "image.iso"
    filepath.write_bytes(b"12345")
    post_download_calls = []

    class Response416:
        status_code = 416
        headers = {}

        def close(self):
            return None

        def raise_for_status(self):
            raise AssertionError("416 resume path should not raise for a complete file")

    class HeadResponse:
        headers = {"content-length": "5"}

    class Session:
        def __init__(self):
            self.get_calls = []
            self.head_calls = []

        def get(self, url, headers=None, stream=True, timeout=30):
            self.get_calls.append((url, headers, stream, timeout))
            return Response416()

        def head(self, url, timeout=30, allow_redirects=True):
            self.head_calls.append((url, timeout, allow_redirects))
            return HeadResponse()

    monkeypatch.setattr(manager, "session", Session())
    monkeypatch.setattr(
        manager,
        "_post_download",
        lambda *args, **kwargs: post_download_calls.append((args, kwargs)) or True,
    )

    assert manager.download_file("https://example.test/image.iso", resume=True)
    assert manager.session.get_calls == [
        (
            "https://example.test/image.iso",
            {"Range": "bytes=5-"},
            True,
            30,
        )
    ]
    assert manager.session.head_calls == [("https://example.test/image.iso", 30, True)]
    assert post_download_calls == []


def test_download_file_restarts_from_scratch_after_416_when_local_size_is_short(
    tmp_path: Path, monkeypatch
):
    manager = DownloadManager(download_dir=str(tmp_path))
    filepath = tmp_path / "image.iso"
    filepath.write_bytes(b"123")

    class Response416:
        status_code = 416
        headers = {}

        def close(self):
            return None

        def raise_for_status(self):
            raise AssertionError("restart path should replace the 416 response before raising")

    class Response200:
        status_code = 200
        headers = {"content-length": "5"}

        def close(self):
            return None

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=8192):
            yield b"abcde"

    class HeadResponse:
        headers = {"content-length": "5"}

    class Session:
        def __init__(self):
            self.get_calls = []
            self.head_calls = []
            self._responses = [Response416(), Response200()]

        def get(self, url, headers=None, stream=True, timeout=30):
            self.get_calls.append((url, headers, stream, timeout))
            return self._responses.pop(0)

        def head(self, url, timeout=30, allow_redirects=True):
            self.head_calls.append((url, timeout, allow_redirects))
            return HeadResponse()

    monkeypatch.setattr(manager, "session", Session())
    monkeypatch.setattr(manager, "_post_download", lambda *args, **kwargs: True)

    assert manager.download_file("https://example.test/image.iso", resume=True)
    assert manager.session.get_calls == [
        (
            "https://example.test/image.iso",
            {"Range": "bytes=3-"},
            True,
            30,
        ),
        (
            "https://example.test/image.iso",
            None,
            True,
            30,
        ),
    ]
    assert manager.session.head_calls == [("https://example.test/image.iso", 30, True)]
    assert filepath.read_bytes() == b"abcde"


def test_download_file_restarts_from_scratch_after_416_when_local_size_is_oversized(
    tmp_path: Path, monkeypatch
):
    manager = DownloadManager(download_dir=str(tmp_path))
    filepath = tmp_path / "image.iso"
    filepath.write_bytes(b"1234567")

    class Response416:
        status_code = 416
        headers = {}

        def close(self):
            return None

        def raise_for_status(self):
            raise AssertionError("oversized local file should restart instead of completing")

    class Response200:
        status_code = 200
        headers = {"content-length": "5"}

        def close(self):
            return None

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=8192):
            yield b"abcde"

    class HeadResponse:
        headers = {"content-length": "5"}

    class Session:
        def __init__(self):
            self.get_calls = []
            self.head_calls = []
            self._responses = [Response416(), Response200()]

        def get(self, url, headers=None, stream=True, timeout=30):
            self.get_calls.append((url, headers, stream, timeout))
            return self._responses.pop(0)

        def head(self, url, timeout=30, allow_redirects=True):
            self.head_calls.append((url, timeout, allow_redirects))
            return HeadResponse()

    monkeypatch.setattr(manager, "session", Session())
    monkeypatch.setattr(manager, "_post_download", lambda *args, **kwargs: True)

    assert manager.download_file("https://example.test/image.iso", resume=True)
    assert manager.session.get_calls == [
        (
            "https://example.test/image.iso",
            {"Range": "bytes=7-"},
            True,
            30,
        ),
        (
            "https://example.test/image.iso",
            None,
            True,
            30,
        ),
    ]
    assert manager.session.head_calls == [("https://example.test/image.iso", 30, True)]
    assert filepath.read_bytes() == b"abcde"


def test_download_from_file_honors_parallel_batch_dispatch(tmp_path: Path, monkeypatch):
    manager = DownloadManager(download_dir=str(tmp_path))
    urls = [f"https://example.test/file-{index}.iso" for index in range(3)]
    lock = threading.Lock()
    inflight = 0
    max_inflight = 0

    def fake_download_file(url: str, **kwargs) -> bool:
        nonlocal inflight, max_inflight
        with lock:
            inflight += 1
            max_inflight = max(max_inflight, inflight)
        time.sleep(0.05)
        with lock:
            inflight -= 1
        return True

    monkeypatch.setattr(manager, "_read_urls", lambda path: urls)
    monkeypatch.setattr(manager, "download_file", fake_download_file)

    assert manager.download_from_file(
        "ignored.txt",
        resume=True,
        verify=False,
        decompress=True,
        interactive=False,
        parallel=3,
    )
    assert max_inflight >= 2
