import io
from pathlib import Path

from os_download.downloader import aria2, curl
from os_download.downloader import manager as manager_module
from os_download.downloader.aria2 import CONTROL_SUFFIX
from os_download.downloader.manager import DownloadManager
from os_download.http import USER_AGENT


class FinishedProcess:
    returncode = 0
    stderr = io.BytesIO()

    def poll(self):
        return 0


def test_auto_backend_uses_aria2_when_it_is_installed(tmp_path: Path, monkeypatch):
    manager = DownloadManager(download_dir=str(tmp_path), backend="auto")
    monkeypatch.setattr(manager_module, "aria2_available", lambda: True)

    assert manager._use_aria2(tmp_path / "image.iso")


def test_auto_backend_falls_back_when_aria2_is_missing(tmp_path: Path, monkeypatch):
    manager = DownloadManager(download_dir=str(tmp_path), backend="auto")
    monkeypatch.setattr(manager_module, "aria2_available", lambda: False)

    assert not manager._use_aria2(tmp_path / "image.iso")


def test_aria2_stops_parsing_options_before_the_url(tmp_path: Path, monkeypatch):
    captured = {}
    monkeypatch.setattr(aria2, "aria2_available", lambda: True)

    def popen(command, **kwargs):
        captured["command"] = command
        return FinishedProcess()

    monkeypatch.setattr(aria2.subprocess, "Popen", popen)

    assert aria2.download_with_aria2(
        "--enable-rpc=true", tmp_path / "image.iso", 2, None, None, None
    )
    assert captured["command"][-2:] == ["--", "--enable-rpc=true"]


def test_curl_uses_the_common_identity_and_stops_options_before_url(tmp_path: Path, monkeypatch):
    captured = {}

    class Head:
        stdout = "content-length: 12\n"

    def popen(command, **kwargs):
        captured["command"] = command
        return FinishedProcess()

    monkeypatch.setattr(curl.shutil, "which", lambda name: "/usr/bin/curl")
    monkeypatch.setattr(curl.subprocess, "run", lambda *args, **kwargs: Head())
    monkeypatch.setattr(curl.subprocess, "Popen", popen)

    assert curl.download_with_curl("--config=bad", tmp_path / "image.iso", 0, None, None, None)
    assert ["--user-agent", USER_AGENT] == captured["command"][1:3]
    assert captured["command"][-2:] == ["--", "--config=bad"]


def test_curl_head_size_is_not_inflated_when_resuming(tmp_path: Path, monkeypatch):
    updates = []

    class Head:
        stdout = "content-length: 12\n"

    class Progress:
        def update(self, task_id, **kwargs):
            updates.append(kwargs)

    monkeypatch.setattr(curl.shutil, "which", lambda name: "/usr/bin/curl")
    monkeypatch.setattr(curl.subprocess, "run", lambda *args, **kwargs: Head())
    monkeypatch.setattr(curl.subprocess, "Popen", lambda *args, **kwargs: FinishedProcess())

    assert curl.download_with_curl(
        "https://example.test/image.iso", tmp_path / "image.iso", 4, Progress(), 1, None
    )
    assert updates[0] == {"total": 12, "completed": 4}


def test_python_backend_still_finishes_a_partial_aria2_download_with_aria2(
    tmp_path: Path, monkeypatch
):
    # A segmented partial can contain holes. Appending to it from its current length would
    # produce a corrupt image, so aria2 has to be the one to finish it.
    manager = DownloadManager(download_dir=str(tmp_path), backend="python")
    partial = tmp_path / "image.iso"
    partial.write_bytes(b"segmented")
    (tmp_path / ("image.iso" + CONTROL_SUFFIX)).write_bytes(b"control")

    monkeypatch.setattr(manager_module, "aria2_available", lambda: True)

    assert manager._use_aria2(partial)


def test_a_url_aria2_cannot_fetch_falls_back_to_the_built_in_backend(tmp_path: Path, monkeypatch):
    # Some mirrors reject aria2 outright. Retrying it three times and giving up would fail a
    # file the plain client (and its curl-on-403 fallback) can fetch perfectly well.
    manager = DownloadManager(download_dir=str(tmp_path), backend="aria2")
    monkeypatch.setattr(manager_module, "aria2_available", lambda: True)
    monkeypatch.setattr(
        manager_module,
        "download_with_aria2",
        lambda url, filepath, connections, progress, task_id, stop_event: False,
    )

    class Response:
        status_code = 200
        headers = {"content-length": "4"}

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            yield b"good"

    class Session:
        def get(self, url, headers=None, stream=True, timeout=30):
            return Response()

    manager.session = Session()

    assert manager.download_file("https://example.test/image.iso", verify=False, decompress=False)
    assert (tmp_path / "image.iso").read_bytes() == b"good"


def test_aria2_keeps_its_own_partial_rather_than_falling_back(tmp_path: Path, monkeypatch):
    # With a control file present the partial is segmented and may have holes, so the
    # built-in backend must not touch it: only aria2 can finish it.
    manager = DownloadManager(download_dir=str(tmp_path), backend="aria2")
    partial = tmp_path / "image.iso"
    partial.write_bytes(b"segmented")
    (tmp_path / ("image.iso" + CONTROL_SUFFIX)).write_bytes(b"control")

    monkeypatch.setattr(manager_module, "aria2_available", lambda: True)
    monkeypatch.setattr(
        manager_module,
        "download_with_aria2",
        lambda url, filepath, connections, progress, task_id, stop_event: False,
    )

    class Session:
        def get(self, *args, **kwargs):
            raise AssertionError("the built-in backend must not touch a segmented partial")

    manager.session = Session()
    monkeypatch.setattr(manager_module.time, "sleep", lambda seconds: None)

    assert not manager.download_file("https://example.test/image.iso", verify=False)
    assert partial.read_bytes() == b"segmented"


def test_a_segmented_partial_is_discarded_rather_than_resumed_when_aria2_is_gone(
    tmp_path: Path, monkeypatch
):
    manager = DownloadManager(download_dir=str(tmp_path), backend="python")
    partial = tmp_path / "image.iso"
    partial.write_bytes(b"segmented with holes")
    control = tmp_path / ("image.iso" + CONTROL_SUFFIX)
    control.write_bytes(b"control")

    monkeypatch.setattr(manager_module, "aria2_available", lambda: False)

    resumed = {}

    class Response:
        status_code = 200
        headers = {"content-length": "4"}

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            yield b"good"

    class Session:
        def get(self, url, headers=None, stream=True, timeout=30):
            resumed["headers"] = headers
            return Response()

    manager.session = Session()

    assert manager.download_file("https://example.test/image.iso", verify=False, decompress=False)

    # No Range header: the file was restarted, not appended to.
    assert not resumed["headers"]
    assert partial.read_bytes() == b"good"
    assert not control.exists()
