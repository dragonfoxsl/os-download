import subprocess
from pathlib import Path

from os_download.downloader import mido


def test_download_with_mido_suppresses_tool_output_and_warns_on_failure(
    tmp_path: Path, monkeypatch
):
    script = tmp_path / "Mido.sh"
    printed = []
    run_kwargs = {}

    def fake_run(cmd, cwd=None, **kwargs):
        run_kwargs.update(kwargs)
        return subprocess.CompletedProcess(
            cmd,
            22,
            stdout="curl progress output",
            stderr="curl: (22) The requested URL returned error: 404",
        )

    monkeypatch.setattr(mido, "ensure_mido", lambda: script)
    monkeypatch.setattr(mido.subprocess, "run", fake_run)
    monkeypatch.setattr(
        mido.console,
        "print",
        lambda *args, **kwargs: printed.append("".join(str(arg) for arg in args)),
    )

    assert not mido.download_with_mido("win11x64", tmp_path)
    assert run_kwargs["capture_output"] is True
    assert run_kwargs["text"] is True
    assert any("Mido failed for win11x64" in message for message in printed)
    assert not any("curl" in message.lower() for message in printed)
