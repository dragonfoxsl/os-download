import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path

from rich.progress import Progress, TaskID

logger = logging.getLogger("os_download")


def download_with_curl(
    url,
    filepath,
    resume_pos,
    progress: Progress | None,
    task_id: TaskID | None,
    stop_event: threading.Event | None,
) -> bool:
    if shutil.which("curl") is None:
        logger.error("CURL_UNAVAILABLE  %s", url)
        return False

    total_size: int | None = None
    try:
        head = subprocess.run(["curl", "-sIL", url], capture_output=True, text=True, timeout=20)
        for line in reversed(head.stdout.splitlines()):
            if line.lower().startswith("content-length:"):
                total_size = int(line.split(":", 1)[1].strip())
                break
    except Exception:
        pass

    if progress is not None and task_id is not None:
        actual_total = (resume_pos + total_size) if total_size else None
        progress.update(task_id, total=actual_total, completed=resume_pos)

    cmd = ["curl", "-L", "-s", "-S"]
    if resume_pos > 0:
        cmd.extend(["-C", "-"])
    cmd.extend(["-o", str(filepath), url])

    try:
        proc = subprocess.Popen(cmd, stderr=subprocess.PIPE)
    except Exception as exc:
        logger.error("CURL_SPAWN_ERROR  %s  -  %s", url, exc)
        return False

    last_size = resume_pos
    path = Path(filepath)
    while proc.poll() is None:
        if stop_event and stop_event.is_set():
            proc.terminate()
            proc.wait(timeout=3)
            return False
        if progress is not None and task_id is not None and path.exists():
            try:
                current_size = path.stat().st_size
                if current_size > last_size:
                    progress.update(task_id, advance=current_size - last_size)
                    last_size = current_size
            except OSError:
                pass
        time.sleep(0.2)

    if progress is not None and task_id is not None and path.exists():
        try:
            final_size = path.stat().st_size
            if final_size > last_size:
                progress.update(task_id, advance=final_size - last_size)
        except OSError:
            pass

    if proc.returncode != 0:
        stderr = proc.stderr.read().decode(errors="replace").strip() if proc.stderr else ""
        logger.error("CURL_FAILED  %s  rc=%d  %s", url, proc.returncode, stderr)
        return False
    return True
