#!/usr/bin/env python3
"""Render the README's download-dashboard screenshot from the real dashboard code.

Driving the actual SessionDashboard rather than mocking up a picture means the screenshot
cannot drift from what the tool prints:

    uv run python scripts/render_dashboard_svg.py
"""

import time
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    ProgressSample,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from os_download.downloader.ui import SessionDashboard, SessionState

OUT = Path(__file__).resolve().parent.parent / "assets" / "screenshots"

MB = 1_048_576

# A believable mid-session: several finished, one still running, one failed, the rest queued
# behind them, and the user having pressed q.
FILES = [
    ("https://releases.ubuntu.com/24.04/ubuntu-24.04.3-desktop-amd64.iso", 6114 * MB, 6114 * MB),
    ("https://releases.ubuntu.com/24.04/ubuntu-24.04.3-live-server-amd64.iso", 3037 * MB, 3037 * MB),
    ("https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/debian-13.1.0-amd64-netinst.iso", 663 * MB, 663 * MB),
    ("https://mirrors.kernel.org/fedora/releases/44/Workstation/x86_64/iso/Fedora-Workstation-Live-44-1.7.x86_64.iso", 2719 * MB, 1483 * MB),
    ("https://mirrors.edge.kernel.org/linuxmint/stable/22.3/linuxmint-22.3-cinnamon-64bit.iso", 2955 * MB, 412 * MB),
    ("https://geo.mirror.pkgbuild.com/iso/latest/archlinux-x86_64.iso", 1329 * MB, 0),
    ("https://download.rockylinux.org/pub/rocky/10/isos/x86_64/Rocky-10.0-x86_64-minimal.iso", 2048 * MB, 0),
    ("https://mirror.cachyos.org/ISO/desktop/250713/cachyos-desktop-linux-250713.iso", 2765 * MB, 0),
]

# Per-file transfer rate; 0 for the queued files, which have not started.
SPEEDS = [42 * MB, 38 * MB, 51 * MB, 27 * MB, 19 * MB, 0, 0, 0]

SUCCEEDED = [url for url, _, _ in FILES[:3]]
FAILED = [FILES[4][0]]


def build_progress(console: Console) -> Progress:
    progress = Progress(
        TextColumn("[bold cyan]{task.description:.42}"),
        BarColumn(bar_width=None),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
        expand=True,
    )

    for (url, total, completed), speed in zip(FILES, SPEEDS, strict=True):
        name = url.rsplit("/", 1)[1]
        task_id = progress.add_task(name, total=total, completed=completed)
        if speed:
            _fake_speed(progress, task_id, speed)

    return progress


def _fake_speed(progress: Progress, task_id: TaskID, bytes_per_second: float) -> None:
    """Give a task a plausible transfer rate.

    Rich derives the speed from timestamped samples of real elapsed time, so simply pushing
    bytes in as fast as the loop runs reports gigabytes per second. Write the samples that a
    download at this rate would have produced instead.
    """
    task = progress._tasks[task_id]
    now = time.monotonic()
    task._progress.clear()
    for second in range(10):
        task._progress.append(ProgressSample(now - 10 + second, bytes_per_second))


def main() -> None:
    console = Console(record=True, width=104, height=26)

    state = SessionState(
        urls=[url for url, _, _ in FILES],
        parallel=3,
        resume=True,
        verify=True,
        succeeded=list(SUCCEEDED),
        failed=list(FAILED),
        interrupted=True,
    )
    # Started a while ago, so the elapsed clock reads like a real session.
    state.started_at = time.monotonic() - (14 * 60 + 38)

    progress = build_progress(console)
    dashboard = SessionDashboard(console, progress, state)

    # The sparkline is built from a rolling history the live session accumulates; a
    # one-shot render has none, so replay a plausible one.
    downloaded = sum(completed for _, _, completed in FILES)
    now = time.monotonic()
    dashboard.speed_samples.clear()
    rates = [0.55, 0.8, 1.0, 0.85, 0.6, 0.75, 0.95, 1.0, 0.7, 0.5, 0.65, 0.9, 1.0, 0.8]
    cumulative = downloaded - sum(rates) * 120 * MB
    for index, rate in enumerate(rates):
        dashboard.speed_samples.append((now - (len(rates) - index), cumulative))
        cumulative += rate * 120 * MB

    dashboard.show_completion()

    console.print(dashboard.layout)

    target = OUT / "download-dashboard-interrupted.svg"
    console.save_svg(str(target), title="os-download")
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
