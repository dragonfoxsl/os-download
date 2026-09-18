import logging
from pathlib import Path

from os_download.logging import setup_file_logger


def test_file_logging_degrades_gracefully_when_the_path_is_unwritable(monkeypatch, capsys):
    def deny(*args, **kwargs):
        raise PermissionError

    monkeypatch.setattr(Path, "mkdir", deny)

    setup_file_logger(logging.getLogger("test-unwritable-log"), "/readonly/app.log")

    assert "File logging disabled" in capsys.readouterr().err
