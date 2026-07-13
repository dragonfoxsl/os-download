import gzip
import os
import threading
import time
from pathlib import Path

from rich.console import Console
from rich.progress import Progress

from os_download.downloader.manager import MIN_COMPLETE_BYTES, DownloadManager
from os_download.downloader.ui import SessionDashboard, SessionState
from os_download.downloader.verification import VerifyReport, VerifyStatus


def stub_verifier(monkeypatch, status: VerifyStatus, calls: list | None = None) -> None:
    """Replace the real verifier, which would otherwise fetch checksums over the network."""

    def fake_verify_download(session, filepath, url, use_cache=True):
        if calls is not None:
            calls.append((filepath.name, filepath.exists()))
        return VerifyReport(status, "stubbed")

    monkeypatch.setattr("os_download.downloader.manager.verify_download", fake_verify_download)


def make_dashboard(
    urls: list[str],
    succeeded: list[str] | None = None,
    failed: list[str] | None = None,
    interrupted: bool = False,
    mido_failed: int = 0,
) -> SessionDashboard:
    state = SessionState(
        urls=urls,
        parallel=1,
        resume=True,
        verify=False,
        succeeded=list(succeeded or []),
        failed=list(failed or []),
        interrupted=interrupted,
        mido_failed=mido_failed,
    )
    return SessionDashboard(Console(), Progress(), state)


def test_post_download_verifies_archive_before_decompressing(tmp_path: Path, monkeypatch):
    manager = DownloadManager(download_dir=str(tmp_path))
    archive = tmp_path / "image.iso.gz"
    archive.write_bytes(gzip.compress(b"iso"))
    calls: list = []

    stub_verifier(monkeypatch, VerifyStatus.VERIFIED, calls)

    assert manager._post_download(
        archive,
        "https://example.test/image.iso.gz",
        verify=True,
        decompress=True,
        own_progress=False,
    )

    # The published hash covers the archive as downloaded, so it must be checked before
    # decompression replaces it.
    assert calls == [("image.iso.gz", True)]
    assert (tmp_path / "image.iso").exists()


def test_post_download_quarantines_a_file_that_fails_verification(tmp_path: Path, monkeypatch):
    manager = DownloadManager(download_dir=str(tmp_path))
    iso = tmp_path / "image.iso"
    iso.write_bytes(b"corrupt payload")

    stub_verifier(monkeypatch, VerifyStatus.HASH_MISMATCH)

    assert not manager._post_download(
        iso,
        "https://example.test/image.iso",
        verify=True,
        decompress=True,
        own_progress=False,
    )

    # Left in place, a resume would append to the corrupt bytes and never recover.
    assert not iso.exists()
    assert (tmp_path / "image.iso.corrupt").read_bytes() == b"corrupt payload"


def test_post_download_quarantines_a_file_whose_checksum_signature_is_invalid(
    tmp_path: Path, monkeypatch
):
    manager = DownloadManager(download_dir=str(tmp_path))
    iso = tmp_path / "image.iso"
    iso.write_bytes(b"payload")

    # The bytes may well match the hash: a substituted signing key means the hash itself
    # cannot be trusted, so a bad signature is fatal regardless.
    stub_verifier(monkeypatch, VerifyStatus.SIGNATURE_INVALID)

    assert not manager._post_download(
        iso, "https://example.test/image.iso", verify=True, decompress=True, own_progress=False
    )
    assert not iso.exists()
    assert (tmp_path / "image.iso.corrupt").exists()


def test_post_download_accepts_an_unsigned_checksum_by_default_but_not_under_require_signature(
    tmp_path: Path, monkeypatch
):
    iso = tmp_path / "image.iso"
    iso.write_bytes(b"payload")
    stub_verifier(monkeypatch, VerifyStatus.HASH_ONLY)

    lenient = DownloadManager(download_dir=str(tmp_path))
    assert lenient._post_download(
        iso, "https://example.test/image.iso", verify=True, decompress=False, own_progress=False
    )

    strict = DownloadManager(download_dir=str(tmp_path), require_signature=True)
    assert not strict._post_download(
        iso, "https://example.test/image.iso", verify=True, decompress=False, own_progress=False
    )
    # An unsigned file is unproven, not proven bad, so it is kept rather than quarantined.
    assert iso.exists()


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

    def fake_verify_download(session, path, url, use_cache=True):
        calls.append(("verify", path.name, path.exists(), url))
        return VerifyReport(VerifyStatus.VERIFIED, "stubbed")

    monkeypatch.setattr("os_download.downloader.manager.verify_download", fake_verify_download)

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
    filepath.write_bytes(b"x" * MIN_COMPLETE_BYTES)

    monkeypatch.setattr(manager, "_read_urls", lambda path: [url])
    monkeypatch.setattr("builtins.input", lambda *args: "")
    monkeypatch.setattr(
        manager,
        "download_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("recent file should be skipped")),
    )

    assert manager.download_from_file("ignored.txt", interactive=True, parallel=1)


def test_download_from_file_does_not_treat_tiny_file_as_a_completed_download(
    tmp_path: Path, monkeypatch
):
    manager = DownloadManager(download_dir=str(tmp_path))
    url = "https://example.test/recent.iso"
    # What a mirror's HTML error page looks like on disk: recent, non-empty, far too small.
    (tmp_path / "recent.iso").write_bytes(b"<html>404 Not Found</html>")
    calls = []

    monkeypatch.setattr(manager, "_read_urls", lambda path: [url])
    monkeypatch.setattr("builtins.input", lambda *args: "")
    monkeypatch.setattr(
        manager,
        "download_file",
        lambda url, *args, **kwargs: (calls.append(url), True)[1],
    )

    assert manager.download_from_file("ignored.txt", interactive=True, parallel=1)
    assert calls == [url]


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


def test_download_from_file_skips_failed_file_and_continues_by_default(
    tmp_path: Path, monkeypatch
):
    manager = DownloadManager(download_dir=str(tmp_path))
    urls = [
        "https://example.test/fail.iso",
        "https://example.test/next.iso",
    ]
    answers = iter(["", ""])
    prompts = []
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
        return url.endswith("next.iso")

    def fake_input(prompt=""):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(manager, "_read_urls", lambda path: urls)
    monkeypatch.setattr(manager, "download_file", fake_download_file)

    assert not manager.download_from_file("ignored.txt", interactive=True, parallel=1)
    assert any("Skip this file and continue? [dim](Y/n)[/dim]" in prompt for prompt in prompts)
    assert calls == urls


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


def test_completion_summary_marks_mido_failures_as_errors():
    dashboard = make_dashboard(
        urls=["https://example.test/ok.iso"],
        succeeded=["https://example.test/ok.iso"],
        mido_failed=1,
    )

    border_style, title, lines = dashboard.completion_summary()

    assert border_style == "red"
    assert title == "✗  Finished with errors"
    assert any("Mido" in line for line in lines)


def test_session_layout_sizes_keep_completion_panel_inside_terminal():
    urls = [f"https://example.test/file-{index}.iso" for index in range(11)]
    dashboard = make_dashboard(
        urls=urls,
        succeeded=urls[:8],
        failed=["https://example.test/fossapup64-9.5.iso"],
        interrupted=True,
        mido_failed=1,
    )
    _, _, lines = dashboard.completion_summary()

    header_size, body_size, completion_size, footer_size = dashboard.layout_sizes(
        completion_lines=lines,
        terminal_height=23,
    )

    assert header_size + body_size + completion_size + footer_size <= 23
    assert body_size < 13
    assert completion_size >= 7


def test_completion_summary_does_not_count_unstarted_files_as_downloaded():
    urls = [f"https://example.test/file-{index}.iso" for index in range(10)]
    dashboard = make_dashboard(urls=urls, succeeded=urls[:1], interrupted=True)

    _, title, lines = dashboard.completion_summary()

    assert title == "⏸  Interrupted"
    assert "[green]1[/green] downloaded" in lines[0]
    assert "9 not started" in lines[0]


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

    monkeypatch.setattr("os_download.downloader.manager.keyboard_listener", fake_keyboard_listener)
    monkeypatch.setattr(manager, "_read_urls", lambda path: [url])
    monkeypatch.setattr(manager, "download_file", fake_download_file)

    assert not manager.download_from_file("ignored.txt", interactive=False, parallel=1)
    assert saw_stop_event == [True]
