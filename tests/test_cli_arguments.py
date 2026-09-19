import argparse
import sys

import pytest

from os_download.cli import downloader
from os_download.cli.common import positive_int


def test_positive_int_accepts_positive_values():
    assert positive_int("7") == 7


@pytest.mark.parametrize("value", ["0", "-1", "nope"])
def test_positive_int_rejects_invalid_values(value: str):
    with pytest.raises(argparse.ArgumentTypeError):
        positive_int(value)


def test_missing_url_file_suggests_the_installed_finder_command(tmp_path, monkeypatch):
    messages = []

    class Console:
        def print(self, message):
            messages.append(str(message))

    monkeypatch.setattr(downloader, "console", Console())
    monkeypatch.setattr(downloader, "setup_file_logger", lambda *args: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["os-download", "--file", str(tmp_path / "missing.txt")],
    )

    with pytest.raises(SystemExit) as exc:
        downloader.main()

    assert exc.value.code == 1
    assert any("Run the OS finder first: os-finder" in message for message in messages)
    assert all("uv run os-finder" not in message for message in messages)
