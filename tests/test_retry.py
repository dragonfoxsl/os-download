import threading
from pathlib import Path

from os_download.downloader import manager as manager_module
from os_download.downloader.manager import DownloadManager, Outcome

URL = "https://example.test/image.iso"


def build(tmp_path: Path, monkeypatch, outcomes: list[Outcome], max_retries: int = 3):
    """A manager whose single-attempt download returns the given outcomes in order."""
    manager = DownloadManager(download_dir=str(tmp_path), max_retries=max_retries)
    attempts: list[bool] = []
    remaining = list(outcomes)

    def fake_attempt(url, filename, resume, verify, decompress, progress, task_id, stop_event):
        attempts.append(resume)
        return remaining.pop(0)

    monkeypatch.setattr(manager, "_attempt_download", fake_attempt)
    # Keep the backoff out of the test's runtime.
    monkeypatch.setattr(manager_module.time, "sleep", lambda seconds: None)
    return manager, attempts


def test_a_dropped_connection_is_retried_and_can_succeed(tmp_path: Path, monkeypatch):
    manager, attempts = build(
        tmp_path, monkeypatch, [Outcome.RETRYABLE, Outcome.RETRYABLE, Outcome.OK]
    )

    assert manager.download_file(URL, resume=False)
    assert len(attempts) == 3
    # The first attempt honours the caller's resume=False; every retry resumes what landed.
    assert attempts == [False, True, True]


def test_retries_are_bounded(tmp_path: Path, monkeypatch):
    manager, attempts = build(
        tmp_path, monkeypatch, [Outcome.RETRYABLE] * 3, max_retries=3
    )

    assert not manager.download_file(URL)
    assert len(attempts) == 3


def test_a_fatal_failure_is_not_retried(tmp_path: Path, monkeypatch):
    # A checksum mismatch or a 404 would fail identically on every attempt.
    manager, attempts = build(tmp_path, monkeypatch, [Outcome.FATAL, Outcome.OK])

    assert not manager.download_file(URL)
    assert len(attempts) == 1


def test_a_user_stop_is_not_retried(tmp_path: Path, monkeypatch):
    manager, attempts = build(tmp_path, monkeypatch, [Outcome.STOPPED, Outcome.OK])

    assert not manager.download_file(URL, stop_event=threading.Event())
    assert len(attempts) == 1


def test_a_stop_during_backoff_abandons_the_retry(tmp_path: Path, monkeypatch):
    stop_event = threading.Event()
    manager, attempts = build(tmp_path, monkeypatch, [Outcome.RETRYABLE, Outcome.OK])
    stop_event.set()

    assert not manager.download_file(URL, stop_event=stop_event)
    assert len(attempts) == 1


def test_permanent_http_statuses_are_classified_as_fatal():
    assert manager_module._is_permanent(404)
    assert manager_module._is_permanent(410)
    # Rate limiting and request timeouts do resolve on their own.
    assert not manager_module._is_permanent(429)
    assert not manager_module._is_permanent(408)
    assert not manager_module._is_permanent(503)
