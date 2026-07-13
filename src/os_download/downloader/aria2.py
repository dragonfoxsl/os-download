"""Segmented downloads via aria2c.

A single HTTP connection rarely saturates a link against a distant mirror, which is why the
distributions publish torrents. aria2c splits the file across several connections and is the
cheapest way to get most of that back.

Resume is aria2's own: it keeps a .aria2 control file recording which segments landed. That
control file is why a failed aria2 download must never be handed to the byte-appending
resume path in manager.py - a partially written segmented file has holes, and appending to
it from its current length would silently produce a corrupt image.
"""

import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path

from rich.progress import Progress, TaskID

from os_download.http import USER_AGENT

logger = logging.getLogger("os_download")

CONTROL_SUFFIX = ".aria2"


def aria2_available() -> bool:
    return shutil.which("aria2c") is not None


def has_control_file(filepath: Path) -> bool:
    """True when aria2 left a resumable, possibly sparse, partial download behind."""
    return filepath.with_name(filepath.name + CONTROL_SUFFIX).exists()


def download_with_aria2(
    url: str,
    filepath: Path,
    connections: int,
    progress: Progress | None,
    task_id: TaskID | None,
    stop_event: threading.Event | None,
) -> bool:
    if not aria2_available():
        return False

    cmd = [
        "aria2c",
        f"--max-connection-per-server={connections}",
        f"--split={connections}",
        "--min-split-size=1M",
        "--continue=true",
        # Preallocation would jump the file to full size immediately, and progress here is
        # measured by watching the file grow.
        "--file-allocation=none",
        "--auto-file-renaming=false",
        "--allow-overwrite=true",
        "--summary-interval=0",
        "--console-log-level=warn",
        f"--user-agent={USER_AGENT}",
        "--dir",
        str(filepath.parent),
        "--out",
        filepath.name,
        url,
    ]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as exc:
        logger.error("ARIA2_SPAWN_ERROR  %s  -  %s", url, exc)
        return False

    logger.info("ARIA2 START  %s  (%d connections)", url, connections)
    last_size = filepath.stat().st_size if filepath.exists() else 0

    while proc.poll() is None:
        if stop_event and stop_event.is_set():
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            logger.info("ARIA2 STOPPED  %s  (partial, resumable)", filepath.name)
            return False
        last_size = _advance(progress, task_id, filepath, last_size)
        time.sleep(0.2)

    _advance(progress, task_id, filepath, last_size)

    if proc.returncode != 0:
        stderr = proc.stderr.read().decode(errors="replace").strip() if proc.stderr else ""
        logger.error("ARIA2 FAILED  %s  rc=%d  %s", url, proc.returncode, stderr)
        return False

    logger.info("ARIA2 DONE  %s", filepath.name)
    return True


def _advance(
    progress: Progress | None, task_id: TaskID | None, filepath: Path, last_size: int
) -> int:
    if progress is None or task_id is None or not filepath.exists():
        return last_size
    try:
        current = filepath.stat().st_size
    except OSError:
        return last_size
    if current > last_size:
        progress.update(task_id, advance=current - last_size)
    return max(current, last_size)
