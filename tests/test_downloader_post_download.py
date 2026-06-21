import gzip
import os
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
    filepath = tmp_path / "image.iso.gz"
    filepath.write_bytes(gzip.compress(b"iso"))
    archive_size = filepath.stat().st_size
    calls = []

    class Response416:
        status_code = 416
        headers = {}

        def close(self):
            return None

        def raise_for_status(self):
            raise AssertionError("416 resume path should not raise for a complete file")

    class HeadResponse:
        headers = {"content-length": str(archive_size)}

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
        "verify_checksum",
        lambda path, url: calls.append(("verify", path.name, path.exists(), url)) or True,
    )

    def fake_decompress(path: Path, verbose: bool = True) -> Path:
        calls.append(("decompress", path.name, path.exists(), verbose))
        output = path.with_suffix("")
        output.write_bytes(b"iso")
        path.unlink()
        return output

    monkeypatch.setattr(manager, "decompress", fake_decompress)

    assert manager.download_file(
        "https://example.test/image.iso.gz",
        resume=True,
        verify=True,
        decompress=True,
    )
    assert manager.session.get_calls == [
        (
            "https://example.test/image.iso.gz",
            {"Range": f"bytes={archive_size}-"},
            True,
            30,
        )
    ]
    assert manager.session.head_calls == [("https://example.test/image.iso.gz", 30, True)]
    assert calls == [
        (
            "verify",
            "image.iso.gz",
            True,
            "https://example.test/image.iso.gz",
        ),
        ("decompress", "image.iso.gz", True, True),
    ]
    assert (tmp_path / "image.iso").read_bytes() == b"iso"


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

    def fake_download_file(
        url: str,
        filename=None,
        resume: bool = True,
        verify: bool = False,
        decompress: bool = True,
        progress=None,
        task_id=None,
        stop_event=None,
    ) -> bool:
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


def test_download_from_file_skips_recent_completed_files_by_default(tmp_path: Path, monkeypatch):
    manager = DownloadManager(download_dir=str(tmp_path))
    url = "https://example.test/recent.iso"
    filepath = tmp_path / "recent.iso"
    filepath.write_bytes(b"complete")

    monkeypatch.setattr(manager, "_read_urls", lambda path: [url])
    monkeypatch.setattr("builtins.input", lambda *args: "")
    monkeypatch.setattr(
        manager,
        "download_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("recent file should be skipped")),
    )

    assert manager.download_from_file("ignored.txt", interactive=True, parallel=1)


def test_download_from_file_can_restart_older_partial_files_from_scratch(
    tmp_path: Path, monkeypatch
):
    manager = DownloadManager(download_dir=str(tmp_path))
    url = "https://example.test/partial.iso"
    filepath = tmp_path / "partial.iso"
    filepath.write_bytes(b"partial")
    old = time.time() - (2 * 86400)
    os.utime(filepath, (old, old))

    prompts = iter(["n"])
    printed = []
    calls = []

    def fake_download_file(
        url: str,
        filename=None,
        resume: bool = True,
        verify: bool = False,
        decompress: bool = True,
        progress=None,
        task_id=None,
        stop_event=None,
    ) -> bool:
        calls.append((url, resume))
        return True

    monkeypatch.setattr("builtins.input", lambda *args: next(prompts))
    monkeypatch.setattr(
        "os_download.downloader.manager.console.print",
        lambda *args, **kwargs: printed.append("".join(str(arg) for arg in args)),
    )
    monkeypatch.setattr(manager, "_read_urls", lambda path: [url])
    monkeypatch.setattr(manager, "download_file", fake_download_file)

    assert manager.download_from_file("ignored.txt", resume=True, interactive=True, parallel=1)
    assert any(
        "Resume previous partial downloads?" in prompt and "(Y/n)" in prompt
        for prompt in printed
    )
    assert calls == [(url, False)]


def test_download_from_file_retries_failed_downloads_after_session(tmp_path: Path, monkeypatch):
    manager = DownloadManager(download_dir=str(tmp_path))
    urls = [
        "https://example.test/fail-once.iso",
        "https://example.test/ok.iso",
    ]
    prompts = iter(["y", "y"])
    attempts = {urls[0]: [False, True], urls[1]: [True]}
    calls = []

    def fake_download_file(
        url: str,
        filename=None,
        resume: bool = True,
        verify: bool = False,
        decompress: bool = True,
        progress=None,
        task_id=None,
        stop_event=None,
    ) -> bool:
        calls.append(url)
        return attempts[url].pop(0)

    monkeypatch.setattr("builtins.input", lambda *args: next(prompts))
    monkeypatch.setattr(manager, "_read_urls", lambda path: urls)
    monkeypatch.setattr(manager, "download_file", fake_download_file)

    assert manager.download_from_file("ignored.txt", interactive=True, parallel=1)
    assert calls == [urls[0], urls[1], urls[0]]


def test_download_from_file_returns_false_on_partial_failure_without_retry(
    tmp_path: Path, monkeypatch
):
    manager = DownloadManager(download_dir=str(tmp_path))
    urls = [
        "https://example.test/ok.iso",
        "https://example.test/fail.iso",
    ]
    calls = []

    def fake_download_file(
        url: str,
        filename=None,
        resume: bool = True,
        verify: bool = False,
        decompress: bool = True,
        progress=None,
        task_id=None,
        stop_event=None,
    ) -> bool:
        calls.append(url)
        return url.endswith("ok.iso")

    monkeypatch.setattr(manager, "_read_urls", lambda path: urls)
    monkeypatch.setattr(manager, "download_file", fake_download_file)

    assert not manager.download_from_file("ignored.txt", interactive=False, parallel=1)
    assert calls == urls


def test_download_from_file_returns_false_when_mido_batch_has_partial_failure(
    tmp_path: Path, monkeypatch
):
    manager = DownloadManager(download_dir=str(tmp_path))
    urls = [
        "mido://success-variant",
        "mido://fail-variant",
    ]
    calls = []
    results = {
        "success-variant": True,
        "fail-variant": False,
    }

    def fake_download_with_mido(variant: str) -> bool:
        calls.append(variant)
        return results[variant]

    monkeypatch.setattr(manager, "_read_urls", lambda path: urls)
    monkeypatch.setattr(manager, "_download_with_mido", fake_download_with_mido)

    assert not manager.download_from_file("ignored.txt", interactive=False, parallel=1)
    assert calls == ["success-variant", "fail-variant"]


def test_download_from_file_returns_false_when_mido_fails_and_regular_downloads_succeed(
    tmp_path: Path, monkeypatch
):
    manager = DownloadManager(download_dir=str(tmp_path))
    urls = [
        "mido://fail-variant",
        "https://example.test/ok.iso",
    ]
    calls = []

    def fake_download_with_mido(variant: str) -> bool:
        calls.append(("mido", variant))
        return False

    def fake_download_file(
        url: str,
        filename=None,
        resume: bool = True,
        verify: bool = False,
        decompress: bool = True,
        progress=None,
        task_id=None,
        stop_event=None,
    ) -> bool:
        calls.append(("regular", url))
        return True

    monkeypatch.setattr(manager, "_read_urls", lambda path: urls)
    monkeypatch.setattr(manager, "_download_with_mido", fake_download_with_mido)
    monkeypatch.setattr(manager, "download_file", fake_download_file)

    assert not manager.download_from_file("ignored.txt", interactive=False, parallel=1)
    assert calls == [("mido", "fail-variant"), ("regular", "https://example.test/ok.iso")]


def test_completion_summary_marks_mido_failures_as_errors(tmp_path: Path):
    manager = DownloadManager(download_dir=str(tmp_path))

    border_style, title, lines = manager._build_completion_summary(
        success=1,
        failed=[],
        interrupted=False,
        mido_failed_count=1,
        total_bytes=1024,
        elapsed=12.3,
    )

    assert border_style == "red"
    assert title == "✗  Finished with errors"
    assert any("Mido" in line for line in lines)


def test_download_from_file_uses_shared_stop_event_for_keyboard_quit(tmp_path: Path, monkeypatch):
    manager = DownloadManager(download_dir=str(tmp_path))
    url = "https://example.test/quit.iso"
    saw_stop_event = []

    def fake_keyboard_listener(quit_event, stop_event):
        quit_event.set()

    def fake_download_file(
        url: str,
        filename=None,
        resume: bool = True,
        verify: bool = False,
        decompress: bool = True,
        progress=None,
        task_id=None,
        stop_event=None,
    ) -> bool:
        assert stop_event is not None
        while not stop_event.is_set():
            time.sleep(0.01)
        saw_stop_event.append(stop_event.is_set())
        return False

    monkeypatch.setattr("os_download.downloader.manager._keyboard_listener", fake_keyboard_listener)
    monkeypatch.setattr(manager, "_read_urls", lambda path: [url])
    monkeypatch.setattr(manager, "download_file", fake_download_file)

    assert not manager.download_from_file("ignored.txt", interactive=False, parallel=1)
    assert saw_stop_event == [True]
